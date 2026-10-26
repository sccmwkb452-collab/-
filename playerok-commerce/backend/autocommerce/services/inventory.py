"""Digital codes: encrypted storage, reservation and issue.

Protection against selling one code twice:

* each code is stored once — ``code_hash`` (keyed HMAC) is UNIQUE, so the
  same key cannot be imported twice even with different spacing/case;
* reservation takes rows with ``FOR UPDATE SKIP LOCKED`` and status
  ``available`` only, so two orders never receive the same row;
* a code moves available → reserved → issued and is bound to one order item;
  a CHECK constraint forbids a used code without an order item;
* the plain code is decrypted only on an explicit «Показать код» (audited).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import CodeStatus
from ..database.models import DigitalCode, Inventory, OrderItem, Product
from ..shared import crypto
from ..shared.errors import Conflict, DomainError, Forbidden, NotFound
from ..shared.masking import mask_code
from ..shared.timeutil import utcnow
from .audit import Actor, audit


def normalize(code: str) -> str:
    return " ".join(code.strip().split())


def code_fingerprint(code: str) -> str:
    return crypto.fingerprint(normalize(code).upper(), "code")


@dataclass
class ImportResult:
    added: int
    duplicates: int
    rejected: int
    ids: list[int]


async def add_codes(
    session: AsyncSession,
    product: Product,
    codes: list[str],
    actor: Actor,
    *,
    unit_cost: Decimal | None = None,
    source: str = "manual",
    is_test: bool = False,
    supplier_order_id: int | None = None,
    reserve_for: OrderItem | None = None,
) -> ImportResult:
    added, duplicates, rejected, ids = 0, 0, 0, []
    now = utcnow()
    for raw in codes:
        code = normalize(raw)
        if len(code) < 4 or len(code) > 500:
            rejected += 1
            continue
        values = dict(
            product_id=product.id,
            code_enc=crypto.encrypt(code),
            code_hash=code_fingerprint(code),
            code_mask=mask_code(code),
            unit_cost=unit_cost,
            source=source,
            is_test=is_test,
            supplier_order_id=supplier_order_id,
            status=CodeStatus.AVAILABLE,
        )
        if reserve_for is not None:
            values.update(status=CodeStatus.RESERVED, order_item_id=reserve_for.id, reserved_at=now)
        stmt = insert(DigitalCode).values(**values).on_conflict_do_nothing(index_elements=[DigitalCode.code_hash]).returning(DigitalCode.id)
        new_id = (await session.execute(stmt)).scalar_one_or_none()
        if new_id is None:
            duplicates += 1
        else:
            added += 1
            ids.append(new_id)
    await refresh_counters(session, product.id)
    await audit(
        session,
        actor,
        "codes.import",
        entity_type="product",
        entity_id=product.id,
        details={"added": added, "duplicates": duplicates, "rejected": rejected, "source": source},
    )
    return ImportResult(added, duplicates, rejected, ids)


async def refresh_counters(session: AsyncSession, product_id: int) -> None:
    await session.flush()
    rows = dict(
        (
            await session.execute(
                select(DigitalCode.status, func.count()).where(DigitalCode.product_id == product_id).group_by(DigitalCode.status)
            )
        ).all()
    )
    inv = await session.get(Inventory, product_id)
    if inv is None:
        inv = Inventory(product_id=product_id)
        session.add(inv)
    inv.quantity_available = rows.get(CodeStatus.AVAILABLE, 0)
    inv.quantity_reserved = rows.get(CodeStatus.RESERVED, 0)


async def reserve(session: AsyncSession, item: OrderItem, quantity: int, *, is_test: bool) -> list[DigitalCode]:
    """Reserve up to ``quantity`` codes for an order item (fewer when stock is short)."""
    already = (
        await session.execute(
            select(func.count()).where(
                DigitalCode.order_item_id == item.id, DigitalCode.status.in_([CodeStatus.RESERVED, CodeStatus.ISSUED])
            )
        )
    ).scalar_one()
    need = quantity - already
    if need <= 0:
        return []
    rows = (
        (
            await session.execute(
                select(DigitalCode)
                .where(
                    DigitalCode.product_id == item.product_id,
                    DigitalCode.status == CodeStatus.AVAILABLE,
                    DigitalCode.is_test.is_(is_test),
                    (DigitalCode.expires_at.is_(None)) | (DigitalCode.expires_at > utcnow()),
                )
                .order_by(DigitalCode.id)
                .limit(need)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    now = utcnow()
    for code in rows:
        code.status = CodeStatus.RESERVED
        code.order_item_id = item.id
        code.reserved_at = now
    await refresh_counters(session, item.product_id)
    return list(rows)


async def assigned(session: AsyncSession, item_id: int) -> list[DigitalCode]:
    return list(
        (
            await session.execute(
                select(DigitalCode)
                .where(DigitalCode.order_item_id == item_id, DigitalCode.status.in_([CodeStatus.RESERVED, CodeStatus.ISSUED]))
                .order_by(DigitalCode.id)
            )
        ).scalars()
    )


async def release(session: AsyncSession, item: OrderItem) -> int:
    """Return reserved (not issued) codes to stock."""
    result = await session.execute(
        update(DigitalCode)
        .where(DigitalCode.order_item_id == item.id, DigitalCode.status == CodeStatus.RESERVED)
        .values(status=CodeStatus.AVAILABLE, order_item_id=None, reserved_at=None)
    )
    await refresh_counters(session, item.product_id)
    return result.rowcount or 0


async def issue(session: AsyncSession, item: OrderItem) -> int:
    """Mark the item's reserved codes as issued. Issued codes never return to stock."""
    codes = (
        (
            await session.execute(
                select(DigitalCode).where(DigitalCode.order_item_id == item.id, DigitalCode.status == CodeStatus.RESERVED).with_for_update()
            )
        )
        .scalars()
        .all()
    )
    now = utcnow()
    for code in codes:
        code.status = CodeStatus.ISSUED
        code.issued_at = now
    await refresh_counters(session, item.product_id)
    return len(codes)


async def void_issued(session: AsyncSession, item: OrderItem) -> int:
    """After a refund an issued code is compromised: it is voided, not resold."""
    result = await session.execute(
        update(DigitalCode)
        .where(DigitalCode.order_item_id == item.id, DigitalCode.status == CodeStatus.ISSUED)
        .values(status=CodeStatus.VOID)
    )
    return result.rowcount or 0


async def reveal(session: AsyncSession, code_id: int, actor: Actor) -> tuple[DigitalCode, str]:
    if not actor.can("orders.reveal_codes"):
        raise Forbidden("Недостаточно прав для просмотра кодов")
    code = await session.get(DigitalCode, code_id, with_for_update=True)
    if code is None:
        raise NotFound("Код не найден")
    if code.order_item_id is None or code.status not in (CodeStatus.RESERVED, CodeStatus.ISSUED):
        raise Conflict("Показать можно только код, закреплённый за заказом")
    code.revealed_count += 1
    await audit(session, actor, "code.reveal", entity_type="digital_code", entity_id=code.id, details={"order_item_id": code.order_item_id})
    return code, crypto.decrypt(code.code_enc)


async def void_code(session: AsyncSession, code_id: int, actor: Actor, reason: str) -> DigitalCode:
    code = await session.get(DigitalCode, code_id, with_for_update=True)
    if code is None:
        raise NotFound("Код не найден")
    if code.status is CodeStatus.ISSUED:
        raise DomainError("Выданный код нельзя списать вручную — оформите возврат по заказу")
    # a voided reserved code no longer covers its order item: the item gets a new code on the next pipeline run
    code.status = CodeStatus.VOID
    code.order_item_id = None
    code.reserved_at = None
    await refresh_counters(session, code.product_id)
    await audit(session, actor, "code.void", entity_type="digital_code", entity_id=code.id, details={"reason": reason})
    return code


async def stock(session: AsyncSession, product_id: int) -> dict[str, int]:
    rows = dict(
        (
            await session.execute(
                select(DigitalCode.status, func.count())
                .where(DigitalCode.product_id == product_id, DigitalCode.is_test.is_(False))
                .group_by(DigitalCode.status)
            )
        ).all()
    )
    return {s.value: rows.get(s, 0) for s in CodeStatus}
