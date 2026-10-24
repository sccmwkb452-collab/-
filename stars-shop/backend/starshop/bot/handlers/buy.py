"""Buying Stars right in the chat.

package or own amount → for me / for someone else (@username is checked) →
summary → payment method → order. The same services as the Mini App create
the order and the payment, so prices, limits, idempotency and the payment
pipeline are shared. The dialogue state is per user (aiogram FSM).
"""

from __future__ import annotations

import uuid
from html import escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...database.enums import ActorType, ProductKind, RecipientType
from ...database.models import Order, Payment, Product, User
from ...notifications.templates import STATUS_LABELS, fmt_money, fmt_stars
from ...payments import service as payments
from ...payments.demo import DemoPaymentProvider
from ...payments.registry import enabled_providers, get_payment_provider
from ...services import orders as order_service
from ...services import pricing, recipients
from ...services.app_settings import RuntimeSettings
from ...services.orders import OrderInput, RecipientInput
from ...shared.errors import AppError
from ...shared.items import item_line, item_title
from ..keyboards import back_row, button, webapp_button

router = Router(name="buy")


class BuyFlow(StatesGroup):
    amount = State()  # waiting for the own amount
    username = State()  # waiting for the recipient's @username


def _rows(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


CANCEL = button("✖️ Отменить", callback="buy:cancel", style="danger")


async def _reply(target: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    if isinstance(target, CallbackQuery):
        await target.answer()
        if target.message is not None:
            try:
                await target.message.edit_text(text, reply_markup=markup)
                return
            except Exception:  # noqa: BLE001 - too old, unchanged or a photo: send anew
                pass
            await target.message.answer(text, reply_markup=markup)
        return
    await target.answer(text, reply_markup=markup)


async def _products(session: AsyncSession) -> list[Product]:
    rows = await session.execute(
        select(Product).where(Product.is_active.is_(True), Product.is_archived.is_(False)).order_by(Product.sort_order, Product.id)
    )
    return list(rows.scalars())


def _limits(product: Product, runtime: RuntimeSettings) -> tuple[int, int]:
    delivery = order_service.active_delivery_provider(runtime)
    low = max(product.min_stars or 1, delivery.min_stars)
    high = min(product.max_stars or delivery.max_stars, delivery.max_stars)
    return low, high


# --- step 1: what to buy ---------------------------------------------------------


async def show_catalog(target: Message | CallbackQuery, state: FSMContext, session: AsyncSession, runtime: RuntimeSettings) -> None:
    await state.clear()
    if runtime.shop.maintenance:
        await _reply(target, f"🛠 {escape(runtime.shop.maintenance_message)}", _rows(back_row()))
        return
    currency = get_settings().shop_currency
    products = await _products(session)
    packages = [p for p in products if p.kind == ProductKind.package]
    custom = next((p for p in products if p.kind == ProductKind.custom), None)
    lines = ["⭐️ <b>Купить Telegram Stars</b>", "", "Выберите пакет или укажите своё количество:"]
    rows: list[list[InlineKeyboardButton]] = []
    if custom is not None:
        low, high = _limits(custom, runtime)
        rows.append([button(f"✏️ Своё количество · {fmt_stars(low)}–{fmt_stars(high)}", callback="buy:custom", style="primary")])
    pair: list[InlineKeyboardButton] = []
    for p in packages:
        label = ("🔥 " if p.is_popular else "") + f"{fmt_stars(p.stars_amount or 0)} ⭐️ · {fmt_money(p.price, currency)}"
        pair.append(button(label, callback=f"buy:pkg:{p.id}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    if not packages and custom is None:
        lines = ["⭐️ <b>Купить Telegram Stars</b>", "", "Пакеты скоро появятся. Загляните чуть позже ✨"]
    if runtime.shop.mode == "demo":
        lines.append("\n🧪 <i>DEMO: оплата тестовая, Stars не отправляются.</i>")
    rows.append(back_row())
    await _reply(target, "\n".join(lines), _rows(*rows))


async def show_premium(target: Message | CallbackQuery, state: FSMContext, session: AsyncSession, runtime: RuntimeSettings) -> None:
    await state.clear()
    currency = get_settings().shop_currency
    plans = [p for p in await _products(session) if p.kind == ProductKind.premium]
    if not plans:
        await _reply(target, "💎 <b>Telegram Premium</b>\n\nСейчас недоступен. Загляните чуть позже ✨", _rows(back_row()))
        return
    lines = [
        "💎 <b>Telegram Premium</b>",
        "",
        "Подписка себе или в подарок: без рекламы, больше лимитов, премиум-эмодзи и стикеры, расшифровка голосовых.",
        "Выберите срок:",
    ]
    if runtime.shop.mode == "demo":
        lines.append("\n🧪 <i>DEMO: оплата тестовая, Premium не подключается.</i>")
    rows = [[button(f"💎 {item_title(0, p.premium_months)} · {fmt_money(p.price, currency)}", callback=f"buy:pkg:{p.id}")] for p in plans]
    rows.append(back_row())
    await _reply(target, "\n".join(lines), _rows(*rows))


@router.callback_query(F.data == "buy:premium")
async def premium_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession, runtime: RuntimeSettings) -> None:
    await show_premium(callback, state, session, runtime)


@router.message(Command("premium"))
async def premium_cmd(message: Message, state: FSMContext, session: AsyncSession, runtime: RuntimeSettings) -> None:
    await show_premium(message, state, session, runtime)


@router.callback_query(F.data == "buy:start")
async def buy_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession, runtime: RuntimeSettings) -> None:
    await show_catalog(callback, state, session, runtime)


@router.message(Command("buy"))
async def buy_cmd(message: Message, state: FSMContext, session: AsyncSession, runtime: RuntimeSettings) -> None:
    await show_catalog(message, state, session, runtime)


@router.callback_query(F.data.startswith("buy:pkg:"))
async def choose_package(callback: CallbackQuery, state: FSMContext, session: AsyncSession, runtime: RuntimeSettings) -> None:
    try:
        product = await pricing.load_product(session, int((callback.data or "").rsplit(":", 1)[1]))
    except (ValueError, AppError):
        await callback.answer("Пакет недоступен", show_alert=True)
        return
    if product.kind not in (ProductKind.package, ProductKind.premium):
        await callback.answer("Пакет недоступен", show_alert=True)
        return
    await state.clear()
    await state.update_data(product_id=product.id, stars=product.stars_amount or 0, months=product.premium_months)
    await ask_recipient(callback, state, runtime)


@router.callback_query(F.data == "buy:custom")
async def choose_custom(callback: CallbackQuery, state: FSMContext, session: AsyncSession, runtime: RuntimeSettings) -> None:
    custom = next((p for p in await _products(session) if p.kind == ProductKind.custom), None)
    if custom is None:
        await callback.answer("Своё количество сейчас недоступно", show_alert=True)
        return
    try:
        low, high = _limits(custom, runtime)
    except AppError as exc:
        await callback.answer(exc.message, show_alert=True)
        return
    await state.clear()
    await state.set_state(BuyFlow.amount)
    await state.update_data(product_id=custom.id)
    await _reply(
        callback,
        f"✏️ <b>Своё количество</b>\n\nОтправьте число звёзд от <b>{fmt_stars(low)}</b> до <b>{fmt_stars(high)}</b>.\n"
        f"Цена: {fmt_money(custom.price_per_star, get_settings().shop_currency)} за звезду.",
        _rows([button("◀️ К пакетам", callback="buy:start")], [CANCEL]),
    )


@router.message(BuyFlow.amount, F.text)
async def enter_amount(message: Message, state: FSMContext, session: AsyncSession, runtime: RuntimeSettings) -> None:
    data = await state.get_data()
    raw = (message.text or "").replace(" ", "").replace(" ", "").replace("_", "")
    try:
        product = await pricing.load_product(session, int(data.get("product_id") or 0))
        stars = int(raw)
        pricing.stars_for(product, stars, order_service.active_delivery_provider(runtime))
    except ValueError:
        await message.answer("Нужно целое число, например <code>750</code>. Попробуйте ещё раз.", reply_markup=_rows([CANCEL]))
        return
    except AppError as exc:
        await message.answer(f"⚠️ {escape(exc.message)}", reply_markup=_rows([CANCEL]))
        return
    await state.set_state(None)
    await state.update_data(stars=stars)
    await ask_recipient(message, state, runtime)


# --- step 2: for whom --------------------------------------------------------------


async def ask_recipient(target: Message | CallbackQuery, state: FSMContext, runtime: RuntimeSettings) -> None:
    data = await state.get_data()
    gifts = runtime.shop.allow_gift_to_others
    rows = [[button("👤 Себе", callback="buy:self", style="primary")]]
    if gifts:
        rows[0].append(button("🎁 Другому", callback="buy:other"))
    rows += [[_back(data)], [CANCEL]]
    await _reply(target, f"Кому покупаем <b>{escape(_item(data))}</b>?", _rows(*rows))


def _item(data: dict[str, Any]) -> str:
    return item_line(int(data.get("stars") or 0), data.get("months"))


def _back(data: dict[str, Any]) -> InlineKeyboardButton:
    return button("◀️ К тарифам", callback="buy:premium") if data.get("months") else button("◀️ К пакетам", callback="buy:start")


async def _delivery(session: AsyncSession, data: dict[str, Any], runtime: RuntimeSettings):
    return order_service.active_delivery_provider(runtime, premium=bool(data.get("months")))


async def _require(callback: CallbackQuery, state: FSMContext) -> dict[str, Any] | None:
    data = await state.get_data()
    if not data.get("product_id") or not (data.get("stars") or data.get("months")):
        await callback.answer("Покупка устарела — начните заново", show_alert=True)
        return None
    return data


@router.callback_query(F.data == "buy:self")
async def for_me(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, runtime: RuntimeSettings, bot: Bot
) -> None:
    if await _require(callback, state) is None:
        return
    await state.update_data(recipient_type="self", username=None, recipient_note=None)
    await show_summary(callback, state, session, db_user, runtime)


@router.callback_query(F.data.in_({"buy:other", "buy:recipient"}))
async def for_other(callback: CallbackQuery, state: FSMContext, runtime: RuntimeSettings) -> None:
    if await _require(callback, state) is None:
        return
    if not runtime.shop.allow_gift_to_others:
        await callback.answer("Покупка для другого пользователя сейчас недоступна", show_alert=True)
        return
    await state.set_state(BuyFlow.username)
    await _reply(
        callback,
        "🎁 Отправьте <b>@username</b> получателя в Telegram, например <code>@durov</code>.\nПеред оплатой я покажу, кому уйдёт подарок.",
        _rows([button("👤 Лучше себе", callback="buy:self")], [CANCEL]),
    )


@router.message(BuyFlow.username, F.text)
async def enter_username(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, runtime: RuntimeSettings, bot: Bot
) -> None:
    try:
        username = order_service.normalize_username(message.text)
        found = await recipients.lookup(session, db_user, username, await _delivery(session, await state.get_data(), runtime))
    except AppError as exc:
        await message.answer(f"⚠️ {escape(exc.message)}", reply_markup=_rows([CANCEL]))
        return
    if found.status in ("not_found", "unavailable"):
        await message.answer(
            f"🔎 {escape(found.message or 'Пользователь не найден')}. Проверьте username и отправьте ещё раз.", reply_markup=_rows([CANCEL])
        )
        return
    if found.is_self:
        await state.update_data(recipient_type="self", username=None, recipient_note=None)
    else:
        if found.status == "verified":
            note = f"✅ {escape(found.name or '@' + found.username)} (@{escape(found.username)})"
        else:
            note = f"⚠️ @{escape(found.username)} — {escape(found.message or 'не удалось проверить')}"
        await state.update_data(recipient_type="username", username=found.username, recipient_note=note)
        await _send_avatar(message, bot, found)
    await state.set_state(None)
    await show_summary(message, state, session, db_user, runtime)


async def _send_avatar(message: Message, bot: Bot, found: recipients.Recipient) -> None:
    """The recipient's profile photo when Telegram gives it to the bot."""
    try:
        if found.telegram_id:
            photos = await bot.get_user_profile_photos(found.telegram_id, limit=1)
            if photos.total_count:
                await message.answer_photo(photos.photos[0][-1].file_id, caption=f"Получатель: @{escape(found.username)}")
                return
        if found.photo_url and found.photo_url.startswith("https://") and not found.photo_url.endswith(".svg"):
            await message.answer_photo(found.photo_url, caption=f"Получатель: @{escape(found.username)}")
    except Exception:  # noqa: BLE001 - the photo is a nicety, never a blocker
        pass


# --- step 3: summary and payment -------------------------------------------------------


async def show_summary(
    target: Message | CallbackQuery, state: FSMContext, session: AsyncSession, user: User, runtime: RuntimeSettings
) -> None:
    data = await state.get_data()
    providers = enabled_providers(runtime.shop.mode)
    if not providers:
        await _reply(target, "💳 Оплата временно недоступна. Попробуйте позже.", _rows(back_row()))
        return
    try:
        product = await pricing.load_product(session, int(data["product_id"]))
        delivery = await _delivery(session, data, runtime)
        quotes = []
        for p in providers:
            q = await pricing.build_quote(
                session,
                user=user,
                product=product,
                stars_requested=int(data["stars"]),
                promo_code=None,
                use_bonus=False,
                payment_provider=p.name,
                delivery=delivery,
                runtime=runtime,
                strict_promo=False,
            )
            quotes.append((p, q))
    except AppError as exc:
        await _reply(target, f"⚠️ {escape(exc.message)}", _rows([_back(data)], [CANCEL]))
        return
    # A new key for each summary: a repeated tap on «Оплатить» returns the same order.
    await state.update_data(idem=uuid.uuid4().hex)
    recipient = "себе" if data.get("recipient_type") != "username" else data.get("recipient_note") or f"@{escape(data['username'])}"
    first = quotes[0][1]
    lines = [
        "🧾 <b>Проверьте заказ</b>",
        "",
        f"{'💎 Подписка' if data.get('months') else '⭐️ Количество'}: <b>{escape(item_title(first.stars_amount, data.get('months')))}</b>",
        f"👤 Получатель: {recipient}",
        f"💰 Стоимость: <b>{fmt_money(first.subtotal, first.currency)}</b>",
    ]
    if any(q.fee > 0 for _, q in quotes):
        lines.append("Комиссия способа оплаты указана на кнопке.")
    lines.append("\nНажимая «Оплатить», вы принимаете условия покупки.")
    if runtime.shop.mode == "demo":
        lines.append("🧪 <i>DEMO: оплата тестовая, ничего не отправляется.</i>")
    rows = [
        [button(f"💳 Оплатить {fmt_money(q.total, q.currency)} · {p.title}", callback=f"buy:pay:{p.name}", style="success")]
        for p, q in quotes
    ]
    rows += [
        [button("✏️ Изменить получателя", callback="buy:recipient"), _back(data)],
        [CANCEL],
    ]
    await _reply(target, "\n".join(lines), _rows(*rows))


@router.callback_query(F.data.startswith("buy:pay:"))
async def pay(callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    data = await _require(callback, state)
    if data is None or not data.get("idem"):
        if data is not None:
            await callback.answer("Покупка устарела — начните заново", show_alert=True)
        return
    provider = (callback.data or "").removeprefix("buy:pay:")
    recipient = (
        RecipientInput(type=RecipientType.username, username=data["username"])
        if data.get("recipient_type") == "username"
        else RecipientInput(type=RecipientType.self)
    )
    product_id = int(data["product_id"])
    stars = int(data.get("stars") or 0)
    try:
        product = await pricing.load_product(session, product_id)
        order, _ = await order_service.create_order(
            session,
            db_user,
            OrderInput(
                product_id=product_id,
                stars_amount=stars if product.kind == ProductKind.custom else None,
                recipient=recipient,
                payment_provider=provider,
            ),
            str(data["idem"]),
            runtime,
        )
        payment = await payments.create_payment(session, order, provider, runtime, notify_user=False)
    except AppError as exc:
        await session.rollback()
        await callback.answer(exc.message[:190], show_alert=True)
        return
    await session.commit()
    await state.clear()
    await _reply(callback, *payment_message(order, payment))


def payment_message(order: Order, payment: Payment) -> tuple[str, InlineKeyboardMarkup]:
    lines = [
        f"🧾 <b>Заказ #{order.number}</b> создан",
        f"{escape(item_line(order.stars_amount, order.premium_months))} · к оплате <b>{fmt_money(order.total, order.currency)}</b>",
        "",
        "Заказ уйдёт в работу сразу после того, как платёжный провайдер подтвердит оплату.",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    if payment.pay_url_kind == "internal":
        lines.append("\n🧪 <i>DEMO: деньги не списываются.</i>")
        rows.append([button("✅ Оплатить (DEMO)", callback=f"pay:demo:{payment.id}", style="success")])
    elif payment.pay_url:
        rows.append([button("💳 Перейти к оплате", url=payment.pay_url, style="success")])
    rows.append([button("🔄 Проверить оплату", callback=f"order:check:{order.id}")])
    rows.append([webapp_button("📦 Открыть заказ", f"orders/{order.id}", style="primary")])
    rows.append([button("✖️ Отменить заказ", callback=f"order:cancel:{order.id}", style="danger")])
    return "\n".join(lines), _rows(*rows)


@router.callback_query(F.data == "buy:cancel")
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _reply(callback, "Покупка отменена. Возвращайтесь, когда будете готовы ✨", _rows(back_row()))


@router.message(BuyFlow.amount)
@router.message(BuyFlow.username)
async def not_text(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте ответ текстом.", reply_markup=_rows([CANCEL]))


# --- after the order ----------------------------------------------------------------------


async def _own_order(session: AsyncSession, user: User, raw: str) -> Order | None:
    try:
        order_id = uuid.UUID(raw)
    except ValueError:
        return None
    return (await session.execute(select(Order).where(Order.id == order_id, Order.user_id == user.id))).scalar_one_or_none()


def status_message(order: Order) -> tuple[str, InlineKeyboardMarkup]:
    text = f"🧾 Заказ <b>#{order.number}</b>: {STATUS_LABELS.get(order.status, order.status)}"
    rows = [[webapp_button("📦 Открыть заказ", f"orders/{order.id}", style="primary")]]
    if order.status in ("created", "pending_payment"):
        rows.insert(0, [button("🔄 Проверить оплату", callback=f"order:check:{order.id}")])
    rows.append(back_row())
    return text, _rows(*rows)


@router.callback_query(F.data.startswith("pay:demo:"))
async def demo_pay(callback: CallbackQuery, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    """DEMO only: the same signed event and pipeline as the Mini App's DEMO checkout."""
    try:
        payment_id = uuid.UUID((callback.data or "").removeprefix("pay:demo:"))
    except ValueError:
        await callback.answer()
        return
    row = (
        await session.execute(
            select(Payment, Order)
            .join(Order, Order.id == Payment.order_id)
            .where(Payment.id == payment_id, Order.user_id == db_user.id, Payment.provider == "demo")
        )
    ).one_or_none()
    if row is None or runtime.shop.mode != "demo":
        await callback.answer("DEMO-оплата недоступна", show_alert=True)
        return
    payment, order = row
    if payment.status not in ("created", "pending"):
        await callback.answer("Платёж уже обработан")
        await _reply(callback, *status_message(order))
        return
    provider = get_payment_provider("demo")
    assert isinstance(provider, DemoPaymentProvider)
    headers, raw = provider.build_event(payment, "success")
    await payments.handle_webhook(session, "demo", headers, raw, "bot", runtime)
    await session.commit()
    await session.refresh(order)
    await callback.answer("Оплата подтверждена (DEMO)")
    await _reply(callback, *status_message(order))


@router.callback_query(F.data.startswith("order:check:"))
async def check(callback: CallbackQuery, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    order = await _own_order(session, db_user, (callback.data or "").removeprefix("order:check:"))
    if order is None:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order.status in ("created", "pending_payment"):
        try:
            await payments.reconcile_order(session, order, runtime, source="bot")
            await session.commit()
        except AppError:
            await session.rollback()
        await session.refresh(order)
    await _reply(callback, *status_message(order))


@router.callback_query(F.data.startswith("order:cancel:"))
async def cancel_order(callback: CallbackQuery, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    order = await _own_order(session, db_user, (callback.data or "").removeprefix("order:cancel:"))
    if order is None:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    try:
        await order_service.cancel_order(
            session, order, runtime, actor_type=ActorType.user, actor_id=db_user.telegram_id, reason="Отменён покупателем в боте"
        )
        await session.commit()
    except AppError as exc:
        await session.rollback()
        await callback.answer(exc.message[:190], show_alert=True)
        return
    await session.refresh(order)
    await _reply(callback, *status_message(order))
