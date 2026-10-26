"""📝 Объявления and 🖼 Генератор изображений."""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InputMediaPhoto, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.enums import LISTING_STATUS_LABELS, ListingStatus, ProductStatus
from ...database.models import Listing
from ...imaging import templates as image_templates
from ...services import app_settings, catalog, listings
from ...services.audit import Actor
from ...shared.errors import DomainError
from ...shared.timeutil import fmt_dt
from ..core import ask, make_router, on_input, require, show
from ..ui import SEP, b, confirm, empty, esc, kb, money, nav, pager, short

router = make_router("listings")
PER_PAGE = 8
FILTERS = [
    ("all", "📋 Все"),
    ("draft", "📝 Черновики"),
    ("ready", "🟦 Готовы"),
    ("published", "🟢 Опубликованы"),
    ("blocked", "🛑 Заблокированы"),
    ("paused", "⏸ Пауза"),
]


@router.callback_query(F.data == "lst:home")
async def home(cb: CallbackQuery, session: AsyncSession) -> None:
    counts = dict((await session.execute(select(Listing.status, func.count()).group_by(Listing.status))).all())
    first_bulk = not await app_settings.get_setting(session, "listings.bulk_confirmed")
    lines = ["📝 <b>Объявления</b>", "<i>PlayerOK без API: система готовит объявления, публикуете вы и указываете номер лота.</i>", SEP]
    lines += [f"{LISTING_STATUS_LABELS[s]}: <b>{c}</b>" for s, c in counts.items()] or [empty("Объявлений пока нет")]
    if first_bulk:
        lines.append("\n🛡 Перед первой массовой публикацией потребуется предпросмотр и подтверждение.")
    rows = [[b(label, f"lst:list:{code}:1") for code, label in FILTERS[i : i + 2]] for i in range(0, len(FILTERS), 2)]
    await show(
        cb,
        "\n".join(lines),
        kb(
            *rows,
            [b("➕ Из товара", "lst:new:1", style="primary"), b("🗂 Подготовить черновики", "lst:bulkprep")],
            [b("📤 Экспорт CSV", "lst:export")],
            nav(),
        ),
    )


@router.callback_query(F.data.startswith("lst:list:"))
async def listing_list(cb: CallbackQuery, session: AsyncSession) -> None:
    _, _, status, page = cb.data.split(":")
    page_n = int(page)
    rows, total = await listings.search(session, status=None if status == "all" else status, page=page_n, per_page=PER_PAGE)
    text = f"📝 <b>{dict(FILTERS).get(status, status)}</b> · {total}\n{SEP}" + ("" if rows else "\n" + empty("Пусто"))
    buttons = [
        [b(f"{LISTING_STATUS_LABELS[x.status].split()[0]} {short(x.title, 30)} · {money(x.price)}", f"lst:open:{x.id}")] for x in rows
    ]
    await show(cb, text, kb(*buttons, pager(f"lst:list:{status}", page_n, total, PER_PAGE), nav("lst:home")))


async def listing_card(session: AsyncSession, listing_id: int) -> tuple[str, object]:
    x = await listings.get_listing(session, listing_id)
    p = x.product
    lines = [
        f"📝 <b>{esc(x.title)}</b>",
        f"{LISTING_STATUS_LABELS[x.status]} · версия {x.version}{' · 🤖 авто' if x.auto_created else ''}",
        SEP,
        f"💰 Цена: <b>{money(x.price)}</b> (мин. {money(p.min_price)}, рекоменд. {money(p.recommended_price)})",
        f"📦 Количество: {x.quantity} · товар: {esc(short(p.name, 40))}",
        f"🔗 Лот PlayerOK: {esc(x.external_id or '—')}" + (f" · {esc(x.external_url)}" if x.external_url else ""),
        f"👁 Предпросмотр: {'подтверждён ' + fmt_dt(x.preview_confirmed_at) if x.preview_confirmed_at else 'не подтверждён'}",
        f"🕒 Опубликовано: {fmt_dt(x.published_at)}",
    ]
    if x.status_reason:
        lines.append(f"\n⚠️ <i>{esc(short(x.status_reason, 500))}</i>")
    lines.append(f"\n{esc(short(x.description, 500))}")
    rows = []
    lid = x.id
    if x.status in (ListingStatus.DRAFT, ListingStatus.BLOCKED, ListingStatus.ERROR):
        rows.append([b("✅ Проверить и подготовить", f"lst:prep:{lid}", style="primary")])
    if x.status is ListingStatus.READY:
        rows.append([b("👁 Предпросмотр", f"lst:preview:{lid}", style="primary")])
        if x.preview_confirmed_at:
            rows.append([b("🚀 Опубликовать", f"lst:pub:{lid}", style="success")])
    if x.status is ListingStatus.PUBLISHED:
        rows.append([b("⏸ Приостановить", f"lst:pause:{lid}"), b("✏️ Цена", f"lst:price:{lid}")])
    if x.status is ListingStatus.PAUSED:
        rows.append([b("▶️ Возобновить", f"lst:resume:{lid}", style="success")])
    rows.append([b("✏️ Название", f"lst:title:{lid}"), b("✏️ Описание", f"lst:desc:{lid}")])
    rows.append([b("🖼 Изображение", f"lst:img:{lid}"), b("🕓 История", f"lst:hist:{lid}")])
    if x.status is not ListingStatus.ARCHIVED:
        rows.append([b("🗄 В архив", f"lst:arch:{lid}")])
    rows.append(nav("lst:home"))
    return "\n".join(lines), kb(*rows)


@router.callback_query(F.data.startswith("lst:open:"))
async def open_listing(cb: CallbackQuery, session: AsyncSession) -> None:
    text, markup = await listing_card(session, int(cb.data.split(":")[2]))
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("lst:new:"))
async def new_listing(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "listings.manage")
    page = int(cb.data.split(":")[2])
    rows, total = await catalog.search_products(session, status=ProductStatus.ACTIVE.value, page=page, per_page=PER_PAGE)
    text = "➕ <b>Объявление из товара</b>\nВыберите активный товар:" + ("" if rows else "\n\n" + empty("Нет активных товаров"))
    buttons = [[b(f"{short(p.name, 34)} · {money(p.recommended_price)}", f"prd:publish:{p.id}")] for p in rows]
    await show(cb, text, kb(*buttons, pager("lst:new", page, total, PER_PAGE), nav("lst:home")))


@router.callback_query(F.data.startswith("lst:prep:"))
async def prepare(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "listings.manage")
    lid = int(cb.data.split(":")[2])
    listing = await listings.get_listing(session, lid, lock=True)
    await listings.prepare(session, listing, actor)
    await cb.answer(LISTING_STATUS_LABELS[listing.status])
    text, markup = await listing_card(session, lid)
    await show(cb, text, markup)


async def _ensure_image(session: AsyncSession, listing: Listing) -> bytes:
    images = [i for i in await listings.images(session, listing.id) if i.listing_version == listing.version]
    image = (
        images[0]
        if images
        else await image_templates.generate_for_product(
            session, listing.product, listing_id=listing.id, listing_version=listing.version, price=listing.price
        )
    )
    return image_templates.image_path(image).read_bytes()


@router.callback_query(F.data.startswith("lst:preview:"))
async def preview(cb: CallbackQuery, session: AsyncSession) -> None:
    lid = int(cb.data.split(":")[2])
    listing = await listings.get_listing(session, lid)
    data = await _ensure_image(session, listing)
    await cb.message.answer_photo(
        BufferedInputFile(data, filename=f"listing-{lid}.png"), caption=f"<b>{esc(listing.title)}</b>\n💰 {money(listing.price)}"
    )
    await cb.message.answer(
        f"👁 <b>Предпросмотр описания</b>\n{SEP}\n{esc(listing.description)}",
        reply_markup=kb(
            [b("📋 Название", copy=listing.title), b("📋 Цена", copy=str(listing.price))],
            [b("✅ Подтвердить предпросмотр", f"lst:confirm:{lid}", style="success")],
            nav(f"lst:open:{lid}"),
        ),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("lst:confirm:"))
async def confirm_preview(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "listings.publish")
    lid = int(cb.data.split(":")[2])
    listing = await listings.get_listing(session, lid, lock=True)
    await listings.confirm_preview(session, listing, actor)
    text, markup = await listing_card(session, lid)
    await show(cb, "✅ Предпросмотр подтверждён\n\n" + text, markup)


@router.callback_query(F.data.startswith("lst:pub:"))
async def publish(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "listings.publish")
    lid = int(cb.data.split(":")[2])
    listing = await listings.get_listing(session, lid, lock=True)
    result = await listings.publish(session, listing, actor)
    if result["mode"] == "published":
        text, markup = await listing_card(session, lid)
        await show(cb, "🟢 " + esc(result["message"]) + "\n\n" + text, markup)
        return
    data = result["data"]
    steps = "\n".join(f"{i}. {esc(s)}" for i, s in enumerate(result.get("steps", []), 1))
    text = f"🚀 <b>Публикация на PlayerOK</b>\n{SEP}\n<i>{esc(result['message'])}</i>\n\n{steps}\n\n<b>Описание</b> (нажмите, чтобы скопировать):\n<code>{esc(data['description'])}</code>"
    await show(
        cb,
        text[:4000],
        kb(
            [b("📋 Название", copy=data["title"]), b("📋 Цена", copy=data["price"])],
            [b("🖼 Изображение", f"lst:img:{lid}"), b("🔗 Указать номер лота", f"lst:ext:{lid}", style="primary")],
            nav(f"lst:open:{lid}"),
        ),
    )


@router.callback_query(F.data.startswith("lst:ext:"))
async def ask_external(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "listings.publish")
    lid = int(cb.data.split(":")[2])
    await ask(
        cb,
        state,
        "lst_ext",
        "Номер лота или ссылка на объявление PlayerOK (https://playerok.com/products/…)",
        back=f"lst:open:{lid}",
        listing_id=lid,
    )


@on_input("lst_ext")
async def external_input(message: Message, ctx: dict) -> None:
    text = message.text.strip()
    url = text if text.startswith("https://") else None
    external = text.rstrip("/").rsplit("/", 1)[-1] if url else text
    listing = await listings.get_listing(ctx["session"], ctx["listing_id"], lock=True)
    result = await listings.mark_published(ctx["session"], listing, external, url, ctx["actor"])
    await ctx["state"].clear()
    card, markup = await listing_card(ctx["session"], listing.id)
    await message.answer(f"🟢 {esc(result['message'])}\n\n{card}", reply_markup=markup)


@router.callback_query(F.data.regexp(r"^lst:(pause|resume):\d+$"))
async def pause_resume(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "listings.manage")
    _, action, lid = cb.data.split(":")
    listing = await listings.get_listing(session, int(lid), lock=True)
    await listings.set_state(session, listing, action, actor)
    text, markup = await listing_card(session, int(lid))
    await show(cb, text, markup)


@router.callback_query(F.data.regexp(r"^lst:arch:\d+(:y)?$"))
async def archive(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "listings.manage")
    parts = cb.data.split(":")
    lid = int(parts[2])
    if len(parts) == 3:
        text, markup = confirm(
            "Перенести объявление в архив? Если лот опубликован на PlayerOK, снимите его вручную.",
            f"lst:arch:{lid}:y",
            f"lst:open:{lid}",
            danger=True,
        )
        await show(cb, text, markup)
        return
    listing = await listings.get_listing(session, lid, lock=True)
    await listings.set_state(session, listing, "archive", actor)
    text, markup = await listing_card(session, lid)
    await show(cb, text, markup)


EDIT_FIELDS = {
    "price": ("Новая цена, ₽", "pricing.manage"),
    "title": ("Новое название (5–100 символов)", "listings.manage"),
    "desc": ("Новое описание", "listings.manage"),
}


@router.callback_query(F.data.regexp(r"^lst:(price|title|desc):\d+$"))
async def ask_edit(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    _, field, lid = cb.data.split(":")
    prompt, permission = EDIT_FIELDS[field]
    require(actor, permission)
    await ask(cb, state, "lst_edit", prompt, back=f"lst:open:{lid}", listing_id=int(lid), field=field)


@on_input("lst_edit")
async def edit_input(message: Message, ctx: dict) -> None:
    field = {"desc": "description"}.get(ctx["field"], ctx["field"])
    value = message.text.strip()
    if field == "price":
        from .products import parse_money

        value = parse_money(value)
    listing = await listings.get_listing(ctx["session"], ctx["listing_id"], lock=True)
    await listings.update(ctx["session"], listing, {field: value}, ctx["actor"])
    await ctx["state"].clear()
    card, markup = await listing_card(ctx["session"], listing.id)
    await message.answer("✅ Сохранено (новая версия)\n\n" + card, reply_markup=markup)


@router.callback_query(F.data.startswith("lst:img:"))
async def listing_image(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "listings.manage")
    lid = int(cb.data.split(":")[2])
    listing = await listings.get_listing(session, lid)
    data = await _ensure_image(session, listing)
    await cb.message.answer_document(
        BufferedInputFile(data, filename=f"playerok-listing-{lid}-v{listing.version}.png"),
        caption="🖼 Изображение для объявления (оригинал PNG)",
    )
    await cb.answer()


@router.callback_query(F.data.startswith("lst:hist:"))
async def history(cb: CallbackQuery, session: AsyncSession) -> None:
    lid = int(cb.data.split(":")[2])
    rows = await listings.history(session, lid)
    lines = ["🕓 <b>История изменений</b>", SEP] + [
        f"v{h.version} · {fmt_dt(h.created_at)} · {esc(h.action)} · {esc(h.actor)} · {money(h.snapshot.get('price'))}" for h in rows[:20]
    ]
    await show(cb, "\n".join(lines), kb(nav(f"lst:open:{lid}")))


@router.callback_query(F.data.regexp(r"^lst:bulkprep(:y)?$"))
async def bulk_prepare(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "listings.manage")
    drafts, total = await listings.search(session, status="draft", per_page=200)
    if not cb.data.endswith(":y"):
        text, markup = confirm(
            f"Проверить и подготовить черновики: {total} шт.? Публикации не будет — только проверка прибыли, текста и правил.",
            "lst:bulkprep:y",
            "lst:home",
        )
        await show(cb, text, markup)
        return
    result = await listings.bulk(session, [x.id for x in drafts], "prepare", actor)
    await show(
        cb,
        f"🗂 Подготовлено: {len(result['ok'])} · ошибок: {len(result['errors'])}",
        kb([b("🟦 Готовые", "lst:list:ready:1")], nav("lst:home")),
    )


@router.callback_query(F.data == "lst:export")
async def export(cb: CallbackQuery, session: AsyncSession) -> None:
    rows, _ = await listings.search(session, per_page=1000)
    await cb.message.answer_document(
        BufferedInputFile(listings.export_csv(rows).encode("utf-8"), filename="listings.csv"), caption="📤 Объявления (CSV)"
    )
    await cb.answer()


# --- 🖼 Генератор изображений ---------------------------------------------------------


@router.callback_query(F.data == "img:home")
async def images_home(cb: CallbackQuery, session: AsyncSession) -> None:
    await image_templates.sync_registry(session)
    templates = await image_templates.list_templates(session)
    lines = ["🖼 <b>Генератор изображений</b>", SEP]
    for t in templates:
        state = "🟢" if t.active else "🟡 нужна разметка полей"
        lines.append(f"{state} <b>{esc(t.name)}</b> ({'ваш шаблон' if t.kind == 'user' else 'демо'}) · {t.width}×{t.height}")
    if not any(t.kind == "user" for t in templates):
        lines.append(
            "\n<i>Ваших шаблонов пока нет. Положите файлы в backend/assets/templates/originals — оригиналы не изменяются. Демо-шаблоны не содержат логотипов брендов.</i>"
        )
    await show(
        cb,
        "\n".join(lines),
        kb([b("🖼 Для товара", "img:p:1", style="primary"), b("📦 Пакетно (активные)", "img:batch")], nav()),
    )


@router.callback_query(F.data.startswith("img:p:"))
async def pick_product(cb: CallbackQuery, session: AsyncSession) -> None:
    page = int(cb.data.split(":")[2])
    rows, total = await catalog.search_products(session, page=page, per_page=PER_PAGE)
    buttons = [[b(short(p.name, 40), f"img:t:{p.id}")] for p in rows]
    await show(
        cb,
        "🖼 Выберите товар:" + ("" if rows else "\n" + empty("Товаров нет")),
        kb(*buttons, pager("img:p", page, total, PER_PAGE), nav("img:home")),
    )


@router.callback_query(F.data.startswith("img:t:"))
async def pick_template(cb: CallbackQuery, session: AsyncSession) -> None:
    pid = int(cb.data.split(":")[2])
    templates = [t for t in await image_templates.list_templates(session) if t.active]
    buttons = [[b(f"{'⭐ ' if t.kind == 'user' else ''}{t.name}", f"img:g:{pid}:{t.code}")] for t in templates]
    await show(cb, "Выберите шаблон:", kb([b("🤖 Автовыбор по категории", f"img:g:{pid}:auto")], *buttons, nav("img:p:1")))


@router.callback_query(F.data.startswith("img:g:"))
async def generate(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "listings.manage")
    _, _, pid, code = cb.data.split(":", 3)
    product = await catalog.get_product(session, int(pid))
    image = await image_templates.generate_for_product(
        session, product, template_code=None if code == "auto" else code, price=product.recommended_price, preview=True
    )
    data = image_templates.image_path(image).read_bytes()
    await cb.message.answer_photo(
        BufferedInputFile(data, filename="preview.png"), caption=f"🖼 {esc(product.name)} · шаблон {esc(image.template_code)}"
    )
    await cb.answer()


@router.callback_query(F.data.regexp(r"^img:batch(:y)?$"))
async def batch(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "listings.manage")
    rows, total = await catalog.search_products(session, status=ProductStatus.ACTIVE.value, per_page=20)
    if not cb.data.endswith(":y"):
        text, markup = confirm(f"Сгенерировать изображения для активных товаров ({min(total, 20)} шт.)?", "img:batch:y", "img:home")
        await show(cb, text, markup)
        return
    if not rows:
        raise DomainError("Нет активных товаров")
    media, errors = [], 0
    for product in rows:
        try:
            image = await image_templates.generate_for_product(session, product, price=product.recommended_price, preview=True)
            media.append(
                InputMediaPhoto(
                    media=BufferedInputFile(image_templates.image_path(image).read_bytes(), filename=f"{product.id}.png"),
                    caption=product.name[:100],
                )
            )
        except DomainError:
            errors += 1
    for i in range(0, len(media), 10):
        await cb.message.answer_media_group(media[i : i + 10])
    await cb.message.answer(f"🖼 Готово: {len(media)} · ошибок: {errors}", reply_markup=kb(nav("img:home")))
    await cb.answer()
