from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from nft_gift_bot.keyboards.callbacks import AccountCb, AdminCb, GiftCb, SubCb
from nft_gift_bot.models import ConnectedAccount, ConnectionStatus, Gift


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def btn(text: str, cb: object = None, url: str | None = None) -> InlineKeyboardButton:
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=cb.pack())  # type: ignore[union-attr]


def subscription_offer() -> InlineKeyboardMarkup:
    return _kb([[btn("💎 Оплатить в TON", SubCb(action="buy"))]])


def invoice(payment_id: int, pay_url: str) -> InlineKeyboardMarkup:
    return _kb([
        [btn("👛 Оплатить", url=pay_url)],
        [btn("🔄 Проверить оплату", SubCb(action="check", payment_id=payment_id))],
        [btn("✖️ Отменить счёт", SubCb(action="cancel", payment_id=payment_id))],
    ])


def after_payment() -> InlineKeyboardMarkup:
    return _kb([[btn("🔐 Подключить свой аккаунт", AccountCb(action="status"))]])


def connect(account: ConnectedAccount | None) -> InlineKeyboardMarkup:
    rows = [[btn("🔄 Обновить статус", AccountCb(action="status"))]]
    if account and account.status == ConnectionStatus.ACTIVE:
        rows.insert(0, [btn("🎁 Мои подарки", GiftCb(action="list"))])
        rows.append([btn("⛔ Отключить аккаунт", AccountCb(action="revoke"))])
    return _kb(rows)


def revoke_confirm() -> InlineKeyboardMarkup:
    return _kb([[btn("⛔ Да, отключить", AccountCb(action="revoke_yes")), btn("Отмена", AccountCb(action="status"))]])


def gift_list(gifts: Sequence[Gift]) -> InlineKeyboardMarkup:
    rows = [[btn(f"🎁 {g.id}. {g.title}"[:60], GiftCb(action="open", id=g.id))] for g in gifts[:40]]
    rows.append([btn("🔄 Обновить", GiftCb(action="list"))])
    return _kb(rows)


def gift_card(gift: Gift, transferable: bool) -> InlineKeyboardMarkup:
    rows = []
    if transferable:
        rows.append([btn("➡️ Передать", GiftCb(action="transfer", id=gift.id))])
    rows.append([btn("← К списку", GiftCb(action="list"))])
    return _kb(rows)


def recipient_prompt() -> InlineKeyboardMarkup:
    return _kb([[btn("Отмена", GiftCb(action="abort"))]])


def transfer_confirm(transfer_id: int) -> InlineKeyboardMarkup:
    return _kb([[
        btn("✅ Подтвердить передачу", GiftCb(action="confirm", id=transfer_id)),
        btn("✖️ Отмена", GiftCb(action="cancel", id=transfer_id)),
    ]])


def settings(account: ConnectedAccount | None) -> InlineKeyboardMarkup:
    rows = [[btn("💎 Продлить подписку", SubCb(action="offer"))]]
    if account and account.status == ConnectionStatus.ACTIVE:
        if account.notify_new_gifts:
            rows.append([btn("🔕 Выключить уведомления", AccountCb(action="notify_off"))])
        else:
            rows.append([btn("🔔 Включить уведомления", AccountCb(action="notify_on"))])
        rows.append([btn("⛔ Отключить аккаунт", AccountCb(action="revoke"))])
    return _kb(rows)


def admin_panel() -> InlineKeyboardMarkup:
    return _kb([
        [btn("📊 Статистика", AdminCb(section="stats")), btn("👥 Пользователи", AdminCb(section="users"))],
        [btn("💳 Платежи", AdminCb(section="payments")), btn("🎁 Передачи", AdminCb(section="transfers"))],
        [btn("🆘 Обращения", AdminCb(section="tickets")), btn("🧾 Аудит", AdminCb(section="audit"))],
        [btn("❔ Команды", AdminCb(section="help"))],
    ])
