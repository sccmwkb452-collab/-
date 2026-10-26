"""Listings Manager.

PlayerOK has no API (manual adapter), so «publish» means: the listing passed
all checks, the owner confirmed the preview, and the operator copies the
prepared title, description, price and image to PlayerOK and records the lot
number. The system never claims a listing is online until that happens.

Protection from double publication: at most one live (ready / published /
paused) listing per product and marketplace (partial unique index), and a
lot number can be attached to one listing only.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import LISTING_STATUS_LABELS, ListingStatus, Severity
from ..database.models import Listing, ListingImage, ListingRevision, Product
from ..integrations.marketplace.playerok_manual import get_marketplace
from ..shared.errors import Blocked, Conflict, DomainError, NotFound
from ..shared.money import fmt_money, money
from ..shared.timeutil import utcnow
from . import app_settings, listing_text
from .audit import Actor, audit
from .catalog import compliance_problem
from .notifications import btn, esc, notify
from .pricing import STATUS_LABELS
from .repricing import reprice_product

LIVE = (ListingStatus.READY, ListingStatus.PUBLISHED, ListingStatus.PAUSED)


def snapshot(listing: Listing) -> dict[str, Any]:
    return {
        "title": listing.title,
        "description": listing.description,
        "price": str(listing.price),
        "quantity": listing.quantity,
        "status": listing.status.value,
        "external_id": listing.external_id,
    }


async def _revision(session: AsyncSession, listing: Listing, action: str, actor: Actor) -> None:
    session.add(
        ListingRevision(listing_id=listing.id, version=listing.version, action=action, snapshot=snapshot(listing), actor=actor.label)
    )


async def get_listing(session: AsyncSession, listing_id: int, *, lock: bool = False) -> Listing:
    query = select(Listing).where(Listing.id == listing_id)
    if lock:
        query = query.with_for_update(of=Listing)
    listing = (await session.execute(query)).unique().scalar_one_or_none()
    if listing is None:
        raise NotFound("Объявление не найдено")
    return listing


async def create(
    session: AsyncSession, product: Product, actor: Actor, *, price_strategy: str = "recommended", auto: bool = False
) -> Listing:
    problem = compliance_problem(product)
    if problem:
        raise Blocked(f"Объявление не создано: {problem}")
    result = await reprice_product(session, product, actor=actor, notify_owner=False)
    if not result.can_sell:
        raise Blocked(f"Объявление не создано: {STATUS_LABELS.get(result.status, result.status)}. {' '.join(result.notes)}")
    price = {"recommended": result.recommended_price, "target": result.target_price, "min": result.min_price}.get(
        price_strategy
    ) or result.recommended_price
    assert price is not None
    existing = (
        (await session.execute(select(Listing).where(Listing.product_id == product.id, Listing.status != ListingStatus.ARCHIVED).limit(1)))
        .unique()
        .scalar_one_or_none()
    )
    if existing is not None:
        raise Conflict(
            f"У товара уже есть объявление #{existing.id} ({LISTING_STATUS_LABELS[existing.status]}). Отредактируйте его или перенесите в архив."
        )
    listing = Listing(
        product_id=product.id,
        title=listing_text.title_for(product),
        description=listing_text.description_for(product),
        price=money(price),
        quantity=1,
        status=ListingStatus.DRAFT,
        template_code=product.category.listing_template,
        auto_created=auto,
    )
    listing.product = product
    session.add(listing)
    await session.flush()
    await _revision(session, listing, "create", actor)
    await audit(
        session, actor, "listing.create", entity_type="listing", entity_id=listing.id, details={"product": product.sku, "price": str(price)}
    )
    return listing


async def update(session: AsyncSession, listing: Listing, data: dict[str, Any], actor: Actor) -> Listing:
    if listing.status is ListingStatus.ARCHIVED:
        raise Conflict("Объявление в архиве")
    changed = []
    for key in ("title", "description", "marketplace_category"):
        if key in data and data[key] is not None and str(data[key]).strip() != getattr(listing, key):
            setattr(listing, key, str(data[key]).strip())
            changed.append(key)
    if "quantity" in data:
        listing.quantity = max(1, int(data["quantity"]))
        changed.append("quantity")
    if "relist_on_complete" in data:
        listing.relist_on_complete = bool(data["relist_on_complete"])
        changed.append("relist_on_complete")
    if "price" in data and data["price"] not in (None, ""):
        price = money(data["price"])
        result = await reprice_product(session, listing.product, actor=actor, notify_owner=False)
        if not result.can_sell:
            raise Blocked(f"Цена не изменена: {STATUS_LABELS.get(result.status, result.status)}")
        if result.min_price is not None and price < result.min_price:
            raise Blocked(f"Цена {fmt_money(price)} ниже минимальной {fmt_money(result.min_price)}")
        listing.price = price
        changed.append("price")
    if not changed:
        return listing
    problems = listing_text.check_text(listing.title, listing.description)
    if problems:
        raise DomainError("; ".join(problems))
    listing.version += 1
    if listing.status is ListingStatus.BLOCKED:
        listing.status = ListingStatus.DRAFT
        listing.status_reason = ""
    await _revision(session, listing, "update:" + ",".join(changed), actor)
    await audit(session, actor, "listing.update", entity_type="listing", entity_id=listing.id, details={"changed": changed})
    if listing.status is ListingStatus.PUBLISHED and "price" in changed and not get_marketplace().supports("update_listings"):
        await notify(
            session,
            "listing",
            f"Обновите цену на PlayerOK: {listing.title[:60]}",
            f"Новая цена: <b>{fmt_money(listing.price)}</b>. Лот: {esc(listing.external_id or '—')}",
            buttons=[[btn("📋 Скопировать цену", copy=str(listing.price))]],
            entity_type="listing",
            entity_id=listing.id,
        )
    return listing


async def prepare(session: AsyncSession, listing: Listing, actor: Actor) -> Listing:
    """Checks before publication: compliance, profitability, text. DRAFT → READY or BLOCKED."""
    if listing.status not in (ListingStatus.DRAFT, ListingStatus.BLOCKED, ListingStatus.ERROR, ListingStatus.PAUSED):
        raise Conflict(f"Объявление уже {LISTING_STATUS_LABELS[listing.status].lower()}")
    product = listing.product
    reasons: list[str] = []
    problem = compliance_problem(product)
    if problem:
        reasons.append(problem)
    result = await reprice_product(session, product, actor=actor, notify_owner=False)
    if not result.can_sell:
        reasons.append(f"{STATUS_LABELS.get(result.status, result.status)}. {' '.join(result.notes)}")
    elif result.min_price is not None and listing.price < result.min_price:
        reasons.append(f"Цена {fmt_money(listing.price)} ниже минимальной {fmt_money(result.min_price)}")
    reasons += listing_text.check_text(listing.title, listing.description)
    if reasons:
        listing.status = ListingStatus.BLOCKED
        listing.status_reason = "\n".join(reasons)[:2000]
        await session.flush()
    else:
        try:
            async with session.begin_nested():
                listing.status = ListingStatus.READY
                listing.status_reason = ""
                await session.flush()
        except IntegrityError as exc:
            raise Conflict("У товара уже есть активное объявление") from exc
    await _revision(session, listing, "prepare", actor)
    return listing


async def confirm_preview(session: AsyncSession, listing: Listing, actor: Actor) -> Listing:
    if listing.status is not ListingStatus.READY:
        raise Conflict("Подтвердить можно только объявление, готовое к публикации")
    listing.preview_confirmed_at = utcnow()
    await _revision(session, listing, "preview_confirmed", actor)
    await audit(session, actor, "listing.preview_confirmed", entity_type="listing", entity_id=listing.id)
    return listing


def export_payload(listing: Listing, image_url: str | None = None) -> dict[str, Any]:
    return {
        "title": listing.title,
        "description": listing.description,
        "price": str(listing.price),
        "quantity": listing.quantity,
        "category": listing.marketplace_category or listing.product.category.name,
        "image": image_url,
    }


async def publish(session: AsyncSession, listing: Listing, actor: Actor) -> dict[str, Any]:
    """Publish through the marketplace if it supports it; otherwise return the
    prepared data and instructions for manual publication."""
    if listing.status is not ListingStatus.READY:
        raise Conflict("Опубликовать можно только объявление со статусом «Готово к публикации»")
    if listing.preview_confirmed_at is None:
        raise Blocked("Сначала проверьте предпросмотр и подтвердите его")
    market = get_marketplace()
    live = await app_settings.is_live(session)
    if market.supports("publish_listings"):
        if not live:
            await _revision(session, listing, "publish_test", actor)
            return {
                "mode": "test",
                "message": "Тестовый режим: объявление не отправлено на площадку. Данные для проверки ниже.",
                "data": export_payload(listing),
            }
        external_id = await market.publish_listing(export_payload(listing))
        return await mark_published(session, listing, external_id, None, actor)
    note = "" if live else " Тестовый режим: система сама ничего не публикует."
    return {
        "mode": "manual",
        "message": market.reason("publish_listings") + note,
        "data": export_payload(listing),
        "steps": [
            "Откройте PlayerOK → «Продать» и выберите категорию",
            "Вставьте название и описание кнопками «Скопировать»",
            f"Укажите цену {fmt_money(listing.price)} и загрузите изображение",
            "После публикации пришлите номер или ссылку лота — система отметит объявление опубликованным",
        ],
    }


async def mark_published(session: AsyncSession, listing: Listing, external_id: str, url: str | None, actor: Actor) -> dict[str, Any]:
    if listing.status is not ListingStatus.READY:
        raise Conflict("Объявление не готово к публикации")
    if listing.preview_confirmed_at is None:
        raise Blocked("Сначала подтвердите предпросмотр")
    external_id = external_id.strip()[:120]
    if not external_id:
        raise DomainError("Укажите номер или ссылку лота PlayerOK")
    if url and not url.startswith("https://"):
        raise DomainError("Ссылка на лот должна начинаться с https://")
    taken = (
        await session.execute(
            select(Listing.id).where(
                Listing.marketplace == listing.marketplace, Listing.external_id == external_id, Listing.id != listing.id
            )
        )
    ).scalar_one_or_none()
    if taken:
        raise Conflict(f"Лот {external_id} уже привязан к объявлению #{taken}")
    listing.external_id = external_id
    listing.external_url = url
    listing.status = ListingStatus.PUBLISHED
    listing.status_reason = ""
    listing.published_at = utcnow()
    product = listing.product
    product.current_price = listing.price
    await _revision(session, listing, "published", actor)
    await audit(session, actor, "listing.published", entity_type="listing", entity_id=listing.id, details={"external_id": external_id})
    return {"mode": "published", "message": f"Объявление отмечено опубликованным: лот {external_id}"}


async def set_state(session: AsyncSession, listing: Listing, action: str, actor: Actor, reason: str = "") -> Listing:
    transitions = {
        "pause": ({ListingStatus.PUBLISHED, ListingStatus.READY}, ListingStatus.PAUSED),
        "resume": ({ListingStatus.PAUSED}, None),
        "archive": ({s for s in ListingStatus if s is not ListingStatus.ARCHIVED}, ListingStatus.ARCHIVED),
    }
    if action not in transitions:
        raise DomainError("Неизвестное действие")
    allowed, target = transitions[action]
    if listing.status not in allowed:
        raise Conflict(f"Действие недоступно для статуса «{LISTING_STATUS_LABELS[listing.status]}»")
    if action == "resume":
        listing.status = ListingStatus.DRAFT
        await prepare(session, listing, actor)
        if listing.status is ListingStatus.READY and listing.external_id and listing.published_at:
            listing.status = ListingStatus.PUBLISHED
    else:
        listing.status = target  # type: ignore[assignment]
        listing.status_reason = reason[:2000]
    await _revision(session, listing, action, actor)
    await audit(session, actor, f"listing.{action}", entity_type="listing", entity_id=listing.id, details={"reason": reason})
    if action in ("pause", "archive") and listing.external_id and not get_marketplace().supports("update_listings"):
        await notify(
            session,
            "listing",
            f"Снимите лот с продажи на PlayerOK: {listing.title[:60]}",
            f"Объявление {'приостановлено' if action == 'pause' else 'перенесено в архив'} в системе. Лот {esc(listing.external_id)} нужно скрыть вручную.",
            severity=Severity.WARNING,
            entity_type="listing",
            entity_id=listing.id,
        )
    return listing


async def bulk(
    session: AsyncSession, ids: list[int], action: str, actor: Actor, *, confirm: bool = False, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Mass actions. The first mass publication requires an explicit confirmation
    after the preview of every listing."""
    if not ids:
        raise DomainError("Не выбрано ни одного объявления")
    if len(ids) > 200:
        raise DomainError("Не больше 200 объявлений за раз")
    if action == "publish":
        confirmed_before = await app_settings.get_setting(session, "listings.bulk_confirmed")
        if not confirm:
            previews = []
            for listing_id in ids:
                listing = await get_listing(session, listing_id)
                previews.append({"id": listing.id, **export_payload(listing), "status": listing.status.value})
            return {"needs_confirmation": True, "first_time": not confirmed_before, "previews": previews}
        if not confirmed_before:
            await app_settings.set_setting(session, "listings.bulk_confirmed", True, actor)
    results: dict[str, Any] = {"ok": [], "errors": {}}
    for listing_id in ids:
        try:
            async with session.begin_nested():
                listing = await get_listing(session, listing_id, lock=True)
                if action == "prepare":
                    await prepare(session, listing, actor)
                elif action == "publish":
                    if listing.status is ListingStatus.DRAFT:
                        await prepare(session, listing, actor)
                    if listing.status is ListingStatus.READY and listing.preview_confirmed_at is None:
                        await confirm_preview(session, listing, actor)
                    await publish(session, listing, actor)
                elif action in ("pause", "resume", "archive"):
                    await set_state(session, listing, action, actor)
                elif action == "price_change_pct":
                    pct_value = Decimal(str((data or {}).get("percent", "0")))
                    await update(session, listing, {"price": money(listing.price * (Decimal(100) + pct_value) / Decimal(100))}, actor)
                elif action == "set_quantity":
                    await update(session, listing, {"quantity": (data or {}).get("quantity", 1)}, actor)
                else:
                    raise DomainError("Неизвестное массовое действие")
            results["ok"].append(listing_id)
        except (DomainError, Conflict, Blocked, NotFound) as exc:
            results["errors"][str(listing_id)] = exc.message
    await audit(session, actor, f"listing.bulk_{action}", details={"count": len(ids), "errors": len(results["errors"])})
    return results


async def after_sale(session: AsyncSession, listing: Listing, actor: Actor) -> None:
    """Relist after a completed sale (auto_listing.relist): keep it live if the price still holds."""
    result = await reprice_product(session, listing.product, actor=actor)
    if listing.status is ListingStatus.PUBLISHED and result.can_sell:
        return
    if listing.status is ListingStatus.PUBLISHED:
        listing.status = ListingStatus.BLOCKED
        listing.status_reason = "После продажи цена больше не проходит проверку прибыли"


async def images(session: AsyncSession, listing_id: int) -> list[ListingImage]:
    return list(
        (
            await session.execute(select(ListingImage).where(ListingImage.listing_id == listing_id).order_by(ListingImage.id.desc()))
        ).scalars()
    )


async def history(session: AsyncSession, listing_id: int) -> list[ListingRevision]:
    return list(
        (
            await session.execute(
                select(ListingRevision).where(ListingRevision.listing_id == listing_id).order_by(ListingRevision.id.desc()).limit(50)
            )
        ).scalars()
    )


async def search(
    session: AsyncSession, *, status: str | None = None, query: str = "", page: int = 1, per_page: int = 10
) -> tuple[list[Listing], int]:
    stmt = select(Listing)
    if status:
        stmt = stmt.where(Listing.status == ListingStatus(status))
    else:
        stmt = stmt.where(Listing.status != ListingStatus.ARCHIVED)
    if query:
        stmt = stmt.where(Listing.title.ilike(f"%{query.strip()}%"))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(Listing.id.desc()).offset((page - 1) * per_page).limit(per_page))).unique().scalars().all()
    return list(rows), total


def export_csv(listings: list[Listing]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["id", "status", "title", "price", "quantity", "category", "external_id", "description"])
    for listing in listings:
        writer.writerow(
            [
                listing.id,
                listing.status.value,
                _safe(listing.title),
                listing.price,
                listing.quantity,
                _safe(listing.product.category.name),
                _safe(listing.external_id or ""),
                _safe(listing.description),
            ]
        )
    return "﻿" + buffer.getvalue()


def _safe(value: str) -> str:
    """CSV formula injection guard."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


async def auto_listing_run(session: AsyncSession) -> dict[str, Any]:
    """«Автовыставление лотов»: prepare listings for profitable approved products.
    Without a publishing API the listings stay READY and the owner gets them for review."""
    from .audit import SYSTEM, automation_log
    from .autosettings import is_active

    active, cfg = await is_active(session, "auto_listing")
    if not active:
        return {"skipped": "disabled"}
    from ..database.enums import ComplianceStatus, LogResult, ProductStatus
    from ..database.models import ProductCategory, Supplier, SupplierProduct

    live_count = (await session.execute(select(func.count()).where(Listing.status.in_(LIVE)))).scalar_one()
    room = int(cfg["max_listings"]) - live_count
    if room <= 0:
        await automation_log(session, "auto_listing", "run", LogResult.SKIPPED, f"Достигнут максимум объявлений: {cfg['max_listings']}")
        return {"created": 0, "reason": "max_listings"}
    has_live = select(Listing.product_id).where(Listing.status != ListingStatus.ARCHIVED)
    stmt = (
        select(Product)
        .join(ProductCategory, ProductCategory.id == Product.category_id)
        .where(
            Product.status == ProductStatus.ACTIVE,
            ProductCategory.compliance_status == ComplianceStatus.APPROVED,
            Product.id.not_in(has_live),
        )
    )
    if cfg.get("categories"):
        stmt = stmt.where(ProductCategory.group.in_(cfg["categories"]))
    if cfg.get("sources"):
        stmt = (
            stmt.join(SupplierProduct, SupplierProduct.id == Product.preferred_supplier_product_id)
            .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
            .where(Supplier.code.in_(cfg["sources"]))
        )
    created: list[Listing] = []
    for product in (await session.execute(stmt.limit(room * 3))).unique().scalars():
        if len(created) >= room:
            break
        try:
            async with session.begin_nested():
                listing = await create(session, product, SYSTEM, price_strategy=cfg["price_strategy"], auto=True)
                if cfg.get("stop_on_low_margin") and (product.expected_profit or 0) < Decimal(str(cfg["min_profit_rub"])):
                    raise Blocked(f"Ожидаемая прибыль {fmt_money(product.expected_profit)} ниже {cfg['min_profit_rub']} ₽")
                listing.relist_on_complete = bool(cfg.get("relist"))
                await prepare(session, listing, SYSTEM)
            created.append(listing)
        except (Blocked, Conflict, DomainError) as exc:
            await automation_log(session, "auto_listing", "skip", LogResult.BLOCKED, f"{product.name}: {exc.message}")
    if created:
        lines = "\n".join(f"• {esc(x.title)} — {fmt_money(x.price)}" for x in created[:15])
        await notify(
            session,
            "listing",
            f"Автовыставление: готово {len(created)} объявл.",
            f"{lines}\n\nПроверьте предпросмотр и опубликуйте на PlayerOK (публикация через API недоступна).",
            buttons=[[btn("📝 Объявления", "lst:list:ready:1")]],
        )
        await automation_log(session, "auto_listing", "run", LogResult.SUGGESTED, f"Подготовлено объявлений: {len(created)}")
    return {"created": len(created)}


async def raise_reminder(session: AsyncSession) -> dict[str, Any]:
    """«Автоподнятие лотов» without an API: a reminder with the lots to raise."""
    from ..database.enums import LogResult
    from ..database.models import AutomationLog
    from ..shared.timeutil import local_day_bounds, local_today
    from .audit import automation_log
    from .autosettings import is_active

    active, cfg = await is_active(session, "auto_raise")
    if not active:
        return {"skipped": "disabled"}
    start, _ = local_day_bounds(local_today())
    done_today = (
        await session.execute(
            select(func.count()).where(
                AutomationLog.feature == "auto_raise", AutomationLog.created_at >= start, AutomationLog.action == "remind"
            )
        )
    ).scalar_one()
    if done_today >= int(cfg["max_operations_per_day"]):
        return {"skipped": "limit"}
    stmt = select(Listing).where(Listing.status == ListingStatus.PUBLISHED)
    ids = [int(x) for x in cfg.get("listing_ids") or [] if str(x).isdigit()]
    if ids:
        stmt = stmt.where(Listing.id.in_(ids))
    rows = (await session.execute(stmt.limit(30))).unique().scalars().all()
    if cfg.get("categories"):
        rows = [r for r in rows if r.product.category.group in cfg["categories"]]
    if not rows:
        return {"skipped": "no_listings"}
    lines = "\n".join(f"• {esc(r.title)} (лот {esc(r.external_id or '—')})" for r in rows[:20])
    await notify(
        session,
        "listing",
        "Пора поднять лоты на PlayerOK",
        f"{lines}\n\nПоднятие через API недоступно — поднимите вручную.",
        dedupe_key=f"raise:{utcnow():%Y%m%d%H%M}",
    )
    for r in rows:
        r.last_bumped_at = utcnow()
    await automation_log(session, "auto_raise", "remind", LogResult.SUGGESTED, f"Напоминание: {len(rows)} лот(ов)")
    return {"listings": len(rows)}
