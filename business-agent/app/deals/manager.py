"""Deal Manager — жизненный цикл сделок.

Гарантии:
- одна и та же договорённость не создаёт две сделки (idempotency_key);
- перед внешним вызовом статус фиксируется в БД (CREATING/PAYING), чтобы после сбоя
  было видно, что операция могла выполниться;
- неизвестный результат → UNKNOWN и только сверка; повторный платёж вслепую невозможен;
- каждая операция проходит TradeGuard (идентичность бота) и политику лимитов.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.state import DealState, Stage, to_decimal
from app.core.audit import audit
from app.core.owners import get_policy
from app.db.models import Contact, Conversation, Deal, DealEvent, DealStatus, TradeBotConfig, utcnow
from app.trading.base import Capability, DealRequest, OpResult, OpStatus
from app.trading.guard import TradeBlocked, require_trade_bot
from app.trading.policy import check_deal_policy
from app.trading.registry import AdapterFactory

S = DealStatus

TRANSITIONS: dict[DealStatus, set[DealStatus]] = {
    S.DRAFT: {S.AWAITING_CONFIRMATION, S.CANCELLED},
    S.AWAITING_CONFIRMATION: {S.CONFIRMED, S.CANCELLED, S.CREATING},
    S.CONFIRMED: {S.CREATING, S.CANCELLED},
    S.CREATING: {S.CREATED, S.USER_ACTION_REQUIRED, S.FAILED, S.UNKNOWN},
    S.CREATED: {S.PAYING, S.PAID, S.USER_ACTION_REQUIRED, S.CANCELLED, S.FAILED, S.COMPLETED},
    S.USER_ACTION_REQUIRED: {S.CREATED, S.PAID, S.COMPLETED, S.CANCELLED, S.FAILED},
    S.PAYING: {S.PAID, S.FAILED, S.UNKNOWN},
    S.PAID: {S.COMPLETED},
    S.UNKNOWN: {S.CREATED, S.PAYING, S.PAID, S.FAILED},
    S.FAILED: set(),
    S.CANCELLED: set(),
    S.COMPLETED: set(),
}

# Статусы, которые человек может отметить вручную для ботов без API.
MANUAL_MARKS = {S.CREATED, S.PAID, S.COMPLETED, S.CANCELLED, S.FAILED}


class DealError(Exception):
    pass


@dataclass
class Prepared:
    deal: Deal | None
    missing: list[str] = field(default_factory=list)
    created_now: bool = False


@dataclass
class StepResult:
    deal: Deal
    message: str
    blocked: bool = False
    problems: list[str] = field(default_factory=list)


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000000001"), rounding=ROUND_HALF_UP)


class DealManager:
    def __init__(self, factory: AdapterFactory) -> None:
        self.factory = factory
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ── служебное ─────────────────────────────────────────────────────────

    async def _transition(self, session: AsyncSession, deal: Deal, to: DealStatus, note: str | None = None) -> None:
        current = DealStatus(deal.status)
        if to != current and to not in TRANSITIONS[current]:
            raise DealError(f"Недопустимый переход {current} → {to}")
        session.add(DealEvent(deal_id=deal.id, from_status=current, to_status=to, note=note))
        deal.status = to
        if to == S.PAYING and deal.funds_committed_at is None:
            deal.funds_committed_at = utcnow()
        if to in (S.FAILED, S.CANCELLED) and current != S.UNKNOWN:
            deal.funds_committed_at = None
        await self._sync_conversation(session, deal)
        await session.flush()

    async def _sync_conversation(self, session: AsyncSession, deal: Deal) -> None:
        if not deal.conversation_id:
            return
        conv = await session.get(Conversation, deal.conversation_id)
        if conv is None:
            return
        state = DealState.load(conv.state)
        state.deal_status = str(deal.status)
        state.deal_id = deal.id
        if deal.status in (S.CREATED, S.PAID, S.COMPLETED, S.USER_ACTION_REQUIRED):
            state.conversation_stage = Stage.DEAL_CREATED
        conv.state = state.dump()

    async def _lock_owner(self, session: AsyncSession, owner_id: int) -> None:
        """Блокировка денежных операций владельца в рамках транзакции (для нескольких инстансов)."""
        if session.bind.dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": 7_000_000 + owner_id})

    def _request(self, deal: Deal) -> DealRequest:
        item = deal.item or {}
        desc = item.get("description") or ", ".join(f"{k}: {v}" for k, v in (item.get("attributes") or {}).items())
        return DealRequest(
            deal_id=deal.id, side=deal.side, amount=deal.total, currency=deal.currency,
            description=f"Сделка #{deal.id}: {desc or deal.product_type or 'товар'} × {deal.quantity}",
            counterparty_telegram_id=deal.counterparty_telegram_id, idempotency_key=deal.idempotency_key,
        )

    # ── подготовка ────────────────────────────────────────────────────────

    async def prepare_from_conversation(self, session: AsyncSession, conv: Conversation, *, created_by: str = "user") -> Prepared:
        state = DealState.load(conv.state)
        missing = []
        price = to_decimal(state.agreed_price)
        if price is None or price <= 0:
            missing.append("согласованная цена")
        if not state.currency:
            missing.append("валюта")
        if not state.quantity:
            missing.append("количество")
        if not (state.item_description or state.item_attributes):
            missing.append("товар")
        if state.counterparty_role not in ("seller", "buyer"):
            missing.append("роль собеседника (продавец/покупатель)")
        if missing:
            return Prepared(None, missing)

        guarded = await require_trade_bot(session, conv.owner_id, self.factory, check_availability=False)
        bot = guarded.config
        side = "buy" if state.counterparty_role == "seller" else "sell"
        item = {"description": state.item_description, "attributes": state.item_attributes}
        key_src = json.dumps(
            [conv.owner_id, conv.id, side, item, str(price), state.currency, state.quantity, bot.bot_user_id],
            ensure_ascii=False, sort_keys=True,
        )
        key = hashlib.sha256(key_src.encode()).hexdigest()
        existing = await session.scalar(select(Deal).where(Deal.idempotency_key == key))
        if existing is not None:
            return Prepared(existing)

        contact = await session.get(Contact, conv.contact_id)
        subtotal = _money(price * state.quantity)
        fees = _money(subtotal * (bot.fee_percent or 0) / 100 + (bot.fee_fixed or 0))
        deal = Deal(
            owner_id=conv.owner_id, conversation_id=conv.id, contact_id=conv.contact_id,
            trade_bot_id=bot.id, trade_bot_user_id=bot.bot_user_id, trade_bot_username=bot.bot_username,
            side=side, product_type=state.product_type, item=item, quantity=state.quantity,
            unit_price=_money(price), currency=state.currency, fees=fees,
            total=subtotal + fees if side == "buy" else subtotal,
            counterparty_telegram_id=contact.telegram_user_id if contact else None,
            status=S.DRAFT, created_by=created_by, idempotency_key=key,
        )
        session.add(deal)
        await session.flush()
        await self._transition(session, deal, S.AWAITING_CONFIRMATION, "подготовлена из переписки")
        await audit(session, "deal_prepared", owner_id=conv.owner_id, conversation_id=conv.id,
                    trade_bot=bot.bot_username, deal_id=deal.id, total=str(deal.total), currency=deal.currency)
        return Prepared(deal, created_now=True)

    # ── создание ──────────────────────────────────────────────────────────

    async def confirm_and_create(self, session: AsyncSession, deal: Deal, *, automatic: bool = False) -> StepResult:
        async with self._locks[deal.owner_id]:
            await self._lock_owner(session, deal.owner_id)
            await session.refresh(deal)
            if deal.status not in (S.AWAITING_CONFIRMATION, S.CONFIRMED):
                return StepResult(deal, f"Сделка уже в статусе «{deal.status}», повторное создание не требуется.")
            op = Capability.CREATE_INVOICE if deal.side == "sell" else Capability.PAY
            try:
                guarded = await require_trade_bot(session, deal.owner_id, self.factory, operation=op,
                                                  expected_bot_user_id=deal.trade_bot_user_id)
            except TradeBlocked as exc:
                await audit(session, "deal_create", "blocked", owner_id=deal.owner_id, trade_bot=deal.trade_bot_username,
                            error=exc.message, deal_id=deal.id)
                return StepResult(deal, exc.message, blocked=True)
            policy = await get_policy(session, deal.owner_id)
            check = await check_deal_policy(session, policy, deal, guarded.config, automatic=automatic)
            if not check.ok:
                await audit(session, "deal_create", "blocked", owner_id=deal.owner_id, trade_bot=deal.trade_bot_username,
                            error="; ".join(check.problems), deal_id=deal.id)
                return StepResult(deal, "Ограничения не выполнены", blocked=True, problems=check.problems)

            if deal.status == S.AWAITING_CONFIRMATION and not automatic:
                await self._transition(session, deal, S.CONFIRMED, "подтверждено пользователем")
            await self._transition(session, deal, S.CREATING, "auto" if automatic else "user")
            await session.commit()  # фиксируем намерение до внешнего вызова

            adapter = guarded.adapter
            if deal.side == "sell" or adapter.manual_only:
                result = await (adapter.create_invoice if deal.side == "sell" else adapter.create_deal)(self._request(deal))
            else:
                # Crypto Pay: отдельной «сделки» нет — сделка фиксируется у нас, затем идёт перевод.
                result = OpResult(OpStatus.SUCCESS)
            return await self._apply_create_result(session, deal, result)

    async def _apply_create_result(self, session: AsyncSession, deal: Deal, result: OpResult) -> StepResult:
        deal.external_deal_id = result.external_id or deal.external_deal_id
        deal.external_url = result.url or deal.external_url
        if result.status == OpStatus.SUCCESS:
            await self._transition(session, deal, S.CREATED)
            msg = "Сделка создана" + (f": {deal.external_url}" if deal.external_url else ".")
            res = "ok"
        elif result.status == OpStatus.REQUIRES_USER_ACTION:
            deal.item = {**(deal.item or {}), "instructions": result.instructions}
            await self._transition(session, deal, S.USER_ACTION_REQUIRED)
            msg = result.instructions or "Нужно действие пользователя в торговом боте."
            res = "skipped"
        elif result.status == OpStatus.UNKNOWN:
            deal.last_error = result.error
            await self._transition(session, deal, S.UNKNOWN, result.error)
            msg = "Результат создания неизвестен — выполняю только сверку, повторно не создаю."
            res = "unknown"
        else:
            deal.last_error = result.error
            await self._transition(session, deal, S.FAILED, result.error)
            msg = f"Не удалось создать сделку: {result.error}"
            res = "error"
        await audit(session, "deal_create", res, owner_id=deal.owner_id, trade_bot=deal.trade_bot_username,
                    error=result.error, deal_id=deal.id, external_id=deal.external_deal_id)
        return StepResult(deal, msg)

    # ── оплата ────────────────────────────────────────────────────────────

    async def pay(self, session: AsyncSession, deal: Deal, *, automatic: bool = False) -> StepResult:
        async with self._locks[deal.owner_id]:
            await self._lock_owner(session, deal.owner_id)
            await session.refresh(deal)
            if deal.side != "buy":
                return StepResult(deal, "Оплата выполняется только для покупок.", blocked=True)
            if deal.status in (S.PAID, S.COMPLETED):
                return StepResult(deal, "Сделка уже оплачена.")
            if deal.status in (S.PAYING, S.UNKNOWN):
                return await self.reconcile(session, deal, _locked=True)
            if deal.status != S.CREATED:
                return StepResult(deal, f"Оплата невозможна в статусе «{deal.status}».", blocked=True)
            try:
                guarded = await require_trade_bot(session, deal.owner_id, self.factory, operation=Capability.PAY,
                                                  expected_bot_user_id=deal.trade_bot_user_id)
            except TradeBlocked as exc:
                await audit(session, "deal_pay", "blocked", owner_id=deal.owner_id, trade_bot=deal.trade_bot_username,
                            error=exc.message, deal_id=deal.id)
                return StepResult(deal, exc.message, blocked=True)
            if guarded.adapter.manual_only:
                result = await guarded.adapter.pay(self._request(deal), "")
                deal.item = {**(deal.item or {}), "instructions": result.instructions}
                await self._transition(session, deal, S.USER_ACTION_REQUIRED, "оплата вручную")
                return StepResult(deal, result.instructions or "Оплатите в торговом боте и отметьте в панели.")
            policy = await get_policy(session, deal.owner_id)
            check = await check_deal_policy(session, policy, deal, guarded.config, automatic=automatic, for_payment=True)
            if not check.ok:
                await audit(session, "deal_pay", "blocked", owner_id=deal.owner_id, trade_bot=deal.trade_bot_username,
                            error="; ".join(check.problems), deal_id=deal.id)
                return StepResult(deal, "Ограничения не выполнены", blocked=True, problems=check.problems)

            if deal.payment_spend_id is None:
                deal.payment_spend_id = uuid.uuid4().hex
            await self._transition(session, deal, S.PAYING, "auto" if automatic else "user")
            await session.commit()  # spend_id и PAYING сохранены до отправки платежа

            result = await guarded.adapter.pay(self._request(deal), deal.payment_spend_id)
            return await self._apply_pay_result(session, deal, result)

    async def _apply_pay_result(self, session: AsyncSession, deal: Deal, result: OpResult) -> StepResult:
        if result.external_id:
            deal.external_deal_id = result.external_id
        if result.status == OpStatus.SUCCESS:
            await self._transition(session, deal, S.PAID)
            msg, res = "Оплата прошла.", "ok"
        elif result.status in (OpStatus.UNKNOWN, OpStatus.PENDING):
            deal.last_error = result.error
            await self._transition(session, deal, S.UNKNOWN, result.error)
            msg, res = "Результат оплаты неизвестен. Повторный платёж НЕ отправлен — идёт сверка.", "unknown"
        else:
            deal.last_error = result.error
            await self._transition(session, deal, S.FAILED, result.error)
            msg, res = f"Оплата не прошла: {result.error}", "error"
        await audit(session, "deal_pay", res, owner_id=deal.owner_id, trade_bot=deal.trade_bot_username,
                    error=result.error, deal_id=deal.id, spend_id=deal.payment_spend_id)
        return StepResult(deal, msg)

    async def retry_payment_same_spend_id(self, session: AsyncSession, deal: Deal) -> StepResult:
        """Повтор после сверки «платёж не найден». Только по явному подтверждению человека и
        только у адаптеров с идемпотентными платежами (тот же spend_id не спишет дважды)."""
        async with self._locks[deal.owner_id]:
            await self._lock_owner(session, deal.owner_id)
            await session.refresh(deal)
            if deal.status != S.UNKNOWN or not deal.payment_spend_id:
                return StepResult(deal, "Повтор доступен только для оплаты с неизвестным результатом.", blocked=True)
            guarded = await require_trade_bot(session, deal.owner_id, self.factory, operation=Capability.IDEMPOTENT_PAYMENTS,
                                              expected_bot_user_id=deal.trade_bot_user_id)
            status = await guarded.adapter.payment_status(deal.payment_spend_id, deal.external_deal_id)
            if status.status != OpStatus.NOT_FOUND:
                return await self._apply_reconcile(session, deal, status)
            await self._transition(session, deal, S.PAYING, "повтор с тем же spend_id (подтверждён пользователем)")
            await session.commit()
            result = await guarded.adapter.pay(self._request(deal), deal.payment_spend_id)
            return await self._apply_pay_result(session, deal, result)

    # ── сверка ────────────────────────────────────────────────────────────

    async def reconcile(self, session: AsyncSession, deal: Deal, *, _locked: bool = False) -> StepResult:
        if not _locked:
            async with self._locks[deal.owner_id]:
                return await self.reconcile(session, deal, _locked=True)
        try:
            guarded = await require_trade_bot(session, deal.owner_id, self.factory,
                                              expected_bot_user_id=deal.trade_bot_user_id, check_availability=False)
        except TradeBlocked as exc:
            return StepResult(deal, exc.message, blocked=True)
        adapter = guarded.adapter
        if adapter.manual_only:
            return StepResult(deal, "Бот без API: статус отмечается вручную в панели.")
        if deal.payment_spend_id and deal.status in (S.PAYING, S.UNKNOWN):
            return await self._apply_reconcile(session, deal, await adapter.payment_status(deal.payment_spend_id, deal.external_deal_id))
        if deal.side == "sell":
            if deal.status == S.UNKNOWN and not deal.external_deal_id and hasattr(adapter, "find_invoice_by_payload"):
                found = await adapter.find_invoice_by_payload(deal.idempotency_key)
                if found.status == OpStatus.SUCCESS:
                    return await self._apply_create_result(session, deal, found)
                return StepResult(deal, "Счёт не найден. Результат остаётся неизвестным; пересоздание — только вручную.")
            if deal.status == S.CREATED and deal.external_deal_id:
                st = await adapter.deal_status(deal.external_deal_id)
                if st.status == OpStatus.SUCCESS:
                    await self._transition(session, deal, S.PAID, "покупатель оплатил счёт")
                    await audit(session, "deal_invoice_paid", owner_id=deal.owner_id, deal_id=deal.id,
                                trade_bot=deal.trade_bot_username)
                    return StepResult(deal, "Покупатель оплатил счёт.")
                if st.status == OpStatus.FAILED and st.data.get("raw_status") == "expired":
                    await self._transition(session, deal, S.FAILED, "счёт истёк")
                    return StepResult(deal, "Счёт истёк без оплаты.")
                return StepResult(deal, f"Статус счёта: {st.data.get('raw_status') or st.status}.")
        return StepResult(deal, f"Сверка не требуется (статус «{deal.status}»).")

    async def _apply_reconcile(self, session: AsyncSession, deal: Deal, status: OpResult) -> StepResult:
        if status.status == OpStatus.SUCCESS:
            if status.external_id:
                deal.external_deal_id = status.external_id
            await self._transition(session, deal, S.PAID, "подтверждено сверкой")
            await audit(session, "deal_reconcile", owner_id=deal.owner_id, deal_id=deal.id, found="paid")
            return StepResult(deal, "Сверка: оплата прошла.")
        if status.status == OpStatus.NOT_FOUND:
            if deal.status == S.PAYING:
                await self._transition(session, deal, S.UNKNOWN, "платёж не найден при сверке")
            await audit(session, "deal_reconcile", "unknown", owner_id=deal.owner_id, deal_id=deal.id, found="not_found")
            return StepResult(deal, "Платёж не найден. Автоматически НЕ повторяется; можно повторить вручную с тем же spend_id.")
        if status.status == OpStatus.PENDING:
            return StepResult(deal, "Платёж в обработке.")
        await audit(session, "deal_reconcile", "unknown", owner_id=deal.owner_id, deal_id=deal.id, error=status.error)
        return StepResult(deal, f"Сверка не удалась: {status.error}. Статус остаётся неизвестным.")

    # ── ручные действия ───────────────────────────────────────────────────

    async def cancel(self, session: AsyncSession, deal: Deal) -> StepResult:
        if S.CANCELLED not in TRANSITIONS[DealStatus(deal.status)]:
            return StepResult(deal, f"Отменить сделку в статусе «{deal.status}» нельзя.", blocked=True)
        await self._transition(session, deal, S.CANCELLED, "отменено пользователем")
        await audit(session, "deal_cancel", actor="user", owner_id=deal.owner_id, deal_id=deal.id)
        return StepResult(deal, "Сделка отменена.")

    async def mark_manual(self, session: AsyncSession, deal: Deal, to: DealStatus, external_id: str | None = None) -> StepResult:
        """Пользователь отмечает результат шага в боте без API, либо подтверждает получение товара."""
        adapter_manual = True
        if deal.trade_bot_id:
            cfg = await session.get(TradeBotConfig, deal.trade_bot_id)
            adapter_manual = cfg is None or self.factory.for_config(cfg).manual_only
        if to not in MANUAL_MARKS:
            raise DealError("Недопустимая ручная отметка")
        if to in (S.CREATED, S.PAID) and not adapter_manual:
            return StepResult(deal, "Для бота с API статус оплаты подтверждается только сверкой.", blocked=True)
        if to not in TRANSITIONS[DealStatus(deal.status)]:
            return StepResult(deal, f"Переход «{deal.status}» → «{to}» недопустим.", blocked=True)
        if external_id:
            deal.external_deal_id = external_id[:128]
        await self._transition(session, deal, to, "отмечено пользователем")
        await audit(session, "deal_mark", actor="user", owner_id=deal.owner_id, deal_id=deal.id, status=str(to))
        return StepResult(deal, f"Статус: {to}.")
