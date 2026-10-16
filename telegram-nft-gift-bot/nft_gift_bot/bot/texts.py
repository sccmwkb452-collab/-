"""All user-facing texts. Short, confident, one style for every notification."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from nft_gift_bot.bot.ui import Rich
from nft_gift_bot.gifts.service import TransferPreview
from nft_gift_bot.models import (
    ConnectedAccount,
    ConnectionStatus,
    Gift,
    GiftTransfer,
    Payment,
    Subscription,
    SubscriptionStatus,
    TransferStatus,
    User,
)
from nft_gift_bot.payments.ton import format_ton
from nft_gift_bot.services.crypto import mask

Ov = dict[str, str]

PAYMENT_STATUS = {
    "pending": "⏳ ожидает оплаты",
    "paid": "✅ оплачено",
    "expired": "⌛ истёк срок",
    "cancelled": "✖️ отменено",
    "failed": "❌ ошибка",
}

TRANSFER_STATUS = {
    TransferStatus.PENDING_CONFIRMATION: "⏳ ждёт подтверждения",
    TransferStatus.PROCESSING: "🔄 выполняется",
    TransferStatus.SUCCEEDED: "✅ выполнено",
    TransferStatus.FAILED: "❌ ошибка",
    TransferStatus.CANCELLED: "✖️ отменено",
    TransferStatus.EXPIRED: "⌛ истекло",
}

GIFT_ERRORS = {
    "no_subscription": "Нужна активная подписка. Откройте «💎 Купить подписку».",
    "no_connection": "Аккаунт не подключён. Откройте «🔐 Подключить аккаунт».",
    "no_view_right": "Включите боту право «Просмотр подарков и звёзд»: Настройки → Telegram Business → Чат-боты.",
    "no_transfer_right": "Включите боту право «Передача и улучшение подарков»: Настройки → Telegram Business → Чат-боты.",
    "no_stars_right": "Передача платная (комиссия в Stars). Включите боту право «Передача звёзд».",
    "gift_not_found": "Подарок не найден. Обновите список подарков.",
    "not_unique": "Через Telegram Bot API передаются только уникальные (NFT) подарки. "
    "Обычный подарок можно улучшить в приложении Telegram.",
    "not_transferable": "Telegram сейчас не разрешает передать этот подарок. "
    "Передать его можно вручную в приложении Telegram, если там доступна кнопка «Передать».",
    "too_early": "Передача станет доступна {detail}.",
    "self_transfer": "Нельзя передать подарок самому себе.",
    "bad_recipient": "Укажите получателя: @username, ссылку t.me/username или числовой ID.",
    "recipient_error": "{detail}",
    "transfer_not_found": "Операция не найдена.",
    "already_processed": "Эта операция уже обработана.",
    "confirmation_expired": "Время подтверждения истекло. Подготовьте передачу заново.",
}


def fmt_dt(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M UTC") if value else "—"


def gift_error_text(code: str, detail: str | None = None) -> str:
    return GIFT_ERRORS.get(code, "Операция недоступна.").format(detail=detail or "")


def error(ov: Ov, message: str) -> Rich:
    return Rich(ov).e("error").t(" ").t(message)


def notice(ov: Ov, key: str, title: str, body: str = "") -> Rich:
    r = Rich(ov).e(key).t(" ").b(title)
    if body:
        r.nl(2).t(body)
    return r


def welcome(ov: Ov, price_ton: Decimal) -> Rich:
    return (
        Rich(ov)
        .e("brand").t(" ").b("Добро пожаловать в NFT Gift Manager.").nl(2)
        .t("Управляйте своими Telegram-подарками, подключайте аккаунт и отслеживайте операции в одном месте.")
        .nl(2)
        .line("subscription", f"Подписка — {price_ton.normalize():f} TON")
        .line("security", "Подключение собственного аккаунта")
        .line("gift", "Управление NFT-подарками")
        .nl()
        .t("Выберите действие ниже.")
    )


def subscription_offer(ov: Ov, price_ton: Decimal, days: int, sub: Subscription | None, now: datetime) -> Rich:
    r = Rich(ov).e("subscription").t(" ").b("Подписка NFT Gift Manager").nl(2)
    r.t("Стоимость: ").b(f"{price_ton.normalize():f} TON").nl()
    r.t("Срок: ").b(f"{days} дн.").nl(2)
    if sub and sub.status == SubscriptionStatus.ACTIVE and sub.expires_at > now:
        r.line("time", f"Активна до {fmt_dt(sub.expires_at)}. Продление добавит срок к текущему.")
        r.nl()
    r.t("Что входит:").nl()
    r.t("• подключение аккаунта через Telegram Business").nl()
    r.t("• просмотр и передача NFT-подарков с подтверждением").nl()
    r.t("• журнал операций и уведомления")
    return r


def invoice(ov: Ov, payment: Payment, address: str, ton_link: str) -> Rich:
    return (
        Rich(ov)
        .e("wallet").t(" ").b("Счёт на оплату").nl(2)
        .t("Сумма: ").b(f"{format_ton(payment.amount_nano)} TON").nl()
        .t("Срок подписки: ").t(f"{payment.subscription_days} дн.").nl()
        .t("Счёт действителен до: ").t(fmt_dt(payment.expires_at)).nl(2)
        .b("Как оплатить").nl()
        .t("1. Нажмите «Оплатить» или переведите сумму на адрес:").nl()
        .code(address).nl()
        .t("2. Обязательно укажите комментарий к переводу:").nl()
        .code(payment.memo).nl(2)
        .e("security").t(" Оплата подтверждается автоматически по данным блокчейна TON. Скриншоты не нужны.")
        .nl(2)
        .t("Ссылка для любого TON-кошелька:").nl()
        .code(ton_link)
    )


def payment_confirmed(ov: Ov, sub: Subscription | None) -> Rich:
    r = Rich(ov).e("payment_ok").t(" ").b("Оплата подтверждена").nl(2)
    if sub:
        r.t("Подписка активна до ").b(fmt_dt(sub.expires_at)).t(".").nl(2)
    r.t("Следующий шаг — подключите свой аккаунт Telegram.")
    return r


def subscription_expiring(ov: Ov, sub: Subscription) -> Rich:
    return notice(ov, "time", "Подписка скоро закончится", f"Срок действия — до {fmt_dt(sub.expires_at)}. Продлите, чтобы не прерывать работу.")


def subscription_expired(ov: Ov) -> Rich:
    return notice(ov, "warning", "Подписка закончилась", "Операции с подарками приостановлены. Продлите подписку, чтобы продолжить.")


def _rights(r: Rich, account: ConnectedAccount) -> None:
    yes, no = "✅", "❌"
    r.t(f"{yes if account.can_view_gifts else no} Просмотр подарков").nl()
    r.t(f"{yes if account.can_transfer_gifts else no} Передача подарков").nl()
    r.t(f"{yes if account.can_transfer_stars else no} Оплата комиссии в Stars").nl()


def connect_screen(ov: Ov, account: ConnectedAccount | None, has_subscription: bool, bot_username: str) -> Rich:
    r = Rich(ov).e("security").t(" ").b("Подключение аккаунта").nl(2)
    if account and account.status == ConnectionStatus.ACTIVE:
        r.t("Статус: ").b("✅ подключён").nl()
        r.t("Аккаунт: ").code(mask(account.telegram_account_id)).nl()
        r.t("Подключён: ").t(fmt_dt(account.connected_at)).nl(2)
        r.b("Права бота").nl()
        _rights(r, account)
        r.nl().t("Права меняются в Telegram: Настройки → Telegram Business → Чат-боты.")
        return r
    if account and account.status == ConnectionStatus.DISABLED:
        r.line("warning", "Подключение выключено в Telegram.").nl()
    r.t("Подключение выполняется официальным механизмом Telegram Business. ")
    r.b("Бот никогда не запрашивает коды входа, облачный пароль или файлы сессии.").nl(2)
    r.t("1. Откройте Telegram → ").b("Настройки → Telegram Business → Чат-боты").t(".").nl()
    r.t("2. Введите ").code(f"@{bot_username}").t(" и добавьте бота.").nl()
    r.t("3. Включите права «Просмотр подарков и звёзд» и «Передача и улучшение подарков». "
        "Для платных передач — «Передача звёзд».").nl()
    r.t("4. Вернитесь в бот — статус обновится автоматически.").nl(2)
    r.line("warning", "Telegram Business доступен владельцам Telegram Premium.")
    if not has_subscription:
        r.line("subscription", "Сначала оформите подписку — без неё подключение не активируется.")
    return r


def connected(ov: Ov, account: ConnectedAccount) -> Rich:
    r = Rich(ov).e("payment_ok").t(" ").b("Аккаунт подключён").nl(2)
    _rights(r, account)
    r.nl().t("Откройте «🎁 Мои NFT-подарки», чтобы увидеть подарки.")
    return r


def revoke_confirm(ov: Ov) -> Rich:
    return notice(
        ov, "security", "Отключить аккаунт?",
        "Бот удалит сохранённый идентификатор подключения и прекратит любые операции с аккаунтом.",
    )


def revoked(ov: Ov) -> Rich:
    return notice(
        ov, "security", "Подключение отозвано",
        "Бот больше не может выполнять операции с вашим аккаунтом.\n\n"
        "Чтобы полностью удалить бота из аккаунта: Настройки → Telegram Business → Чат-боты → Удалить бота.",
    )


def cabinet(
    ov: Ov,
    user: User,
    sub: Subscription | None,
    account: ConnectedAccount | None,
    gifts_count: int | None,
    operations: int,
    payments: Sequence[Payment],
    now: datetime,
) -> Rich:
    r = Rich(ov).e("account").t(" ").b("Личный кабинет").nl(2)
    r.t("Telegram ID: ").code(user.telegram_id).nl()
    if sub and sub.status == SubscriptionStatus.ACTIVE and sub.expires_at > now:
        r.t("Подписка: ").b("активна").nl().t("Действует до: ").t(fmt_dt(sub.expires_at)).nl()
    elif sub:
        r.t("Подписка: ").b("истекла").t(f" ({fmt_dt(sub.expires_at)})").nl()
    else:
        r.t("Подписка: ").b("нет").nl()
    if account and account.status == ConnectionStatus.ACTIVE:
        r.t("Аккаунт: ").code(mask(account.telegram_account_id)).t(" — ✅ подключён").nl()
    elif account:
        r.t("Аккаунт: отключён").nl()
    else:
        r.t("Аккаунт: не подключён").nl()
    r.t("Подарков: ").t(gifts_count if gifts_count is not None else "—").nl()
    r.t("Выполнено передач: ").t(operations).nl(2)
    r.b("Последние платежи").nl()
    if not payments:
        r.t("Платежей пока нет.")
    for p in payments[:3]:
        r.t(f"• {fmt_dt(p.created_at)} — {format_ton(p.amount_nano)} TON — {PAYMENT_STATUS.get(p.status, p.status)}").nl()
    return r


def payments_list(ov: Ov, payments: Sequence[Payment]) -> Rich:
    r = Rich(ov).e("payment").t(" ").b("Мои платежи").nl(2)
    if not payments:
        return r.t("Платежей пока нет.")
    for p in payments:
        r.code(p.memo).t(f" · {format_ton(p.amount_nano)} TON").nl()
        r.t(f"{PAYMENT_STATUS.get(p.status, p.status)} · {fmt_dt(p.paid_at or p.created_at)}").nl(2)
    return r


def _gift_state(gift: Gift, now: datetime) -> str:
    if not gift.is_unique:
        return "обычный"
    if gift.next_transfer_date and gift.next_transfer_date > now:
        return f"⏳ с {gift.next_transfer_date:%d.%m}"
    return "✅ можно передать" if gift.can_be_transferred else "🔒 передача недоступна"


def gift_list(ov: Ov, gifts: Sequence[Gift], now: datetime) -> Rich:
    r = Rich(ov).e("gift").t(" ").b("Мои NFT-подарки").nl(2)
    if not gifts:
        return r.t("Подарков на аккаунте не найдено.")
    for g in gifts:
        r.b(f"{g.id}.").t(f" {g.title} — {_gift_state(g, now)}").nl()
    r.nl().i("Можно написать боту: «передай 12 @username»")
    return r


def gift_card(ov: Ov, gift: Gift, now: datetime) -> Rich:
    r = Rich(ov).e("gift").t(" ").b(gift.title).nl(2)
    r.t("Номер в боте: ").code(gift.id).nl()
    r.t("ID подарка: ").code(gift.owned_gift_id[:48]).nl()
    r.t("Тип: ").t("уникальный (NFT)" if gift.is_unique else "обычный").nl()
    r.t("Передача: ").t(_gift_state(gift, now)).nl()
    if gift.is_unique:
        fee = f"{gift.transfer_star_count} ⭐" if gift.transfer_star_count else "нет"
        r.t("Комиссия Telegram: ").t(fee).nl()
    else:
        r.nl().i(GIFT_ERRORS["not_unique"])
    return r


def ask_recipient(ov: Ov, gift: Gift) -> Rich:
    return (
        Rich(ov).e("gift").t(" ").b(f"Передача: {gift.title}").nl(2)
        .t("Отправьте получателя одним сообщением: @username, ссылку t.me/username или числовой ID.")
    )


def transfer_preview(ov: Ov, preview: TransferPreview, ttl_seconds: int) -> Rich:
    t = preview.transfer
    r = Rich(ov).e("gift").t(" ").b("Подтвердите передачу").nl(2)
    r.t("Подарок: ").b(t.gift_title).nl()
    r.t("Получатель: ").b(t.recipient_label).t(" (ID ").code(t.recipient_chat_id).t(")").nl()
    r.t("Комиссия: ")
    if t.star_count:
        r.b(f"{t.star_count} ⭐").t(" — спишется с баланса Stars аккаунта").nl()
    else:
        r.t("нет").nl()
    r.t("Подтверждение действует ").t(f"{ttl_seconds // 60} мин.").nl(2)
    if not preview.recipient.verified:
        r.line("warning", "Бот не смог заранее проверить этот ID — Telegram проверит его при передаче.")
    r.line("warning", "Передача необратима. Проверьте получателя.")
    return r


def transfer_result(ov: Ov, transfer: GiftTransfer) -> Rich:
    if transfer.status == TransferStatus.SUCCEEDED:
        return notice(ov, "payment_ok", "Подарок передан", f"{transfer.gift_title} → {transfer.recipient_label}")
    return notice(
        ov, "error", "Передача не выполнена",
        f"{transfer.gift_title} → {transfer.recipient_label}\n\n{transfer.error_message or 'Неизвестная ошибка.'}",
    )


def history(ov: Ov, transfers: Sequence[GiftTransfer]) -> Rich:
    r = Rich(ov).e("history").t(" ").b("История операций").nl(2)
    if not transfers:
        return r.t("Операций пока нет.")
    for t in transfers:
        r.b(t.gift_title).t(f" → {t.recipient_label}").nl()
        r.t(f"{TRANSFER_STATUS.get(t.status, t.status)} · {fmt_dt(t.executed_at or t.created_at)} · ").code(t.owned_gift_id[:16]).nl(2)
    return r


def settings_screen(ov: Ov, account: ConnectedAccount | None, sub: Subscription | None, now: datetime) -> Rich:
    r = Rich(ov).e("settings").t(" ").b("Настройки").nl(2)
    if sub and sub.expires_at > now and sub.status == SubscriptionStatus.ACTIVE:
        r.t("Подписка до ").t(fmt_dt(sub.expires_at)).nl()
    else:
        r.t("Подписка не активна").nl()
    if account and account.status == ConnectionStatus.ACTIVE:
        r.t("Уведомления о подарках: ").t("включены" if account.notify_new_gifts else "выключены").nl()
    else:
        r.t("Аккаунт не подключён").nl()
    return r


def support_prompt(ov: Ov) -> Rich:
    return notice(ov, "support", "Поддержка", "Опишите вопрос одним сообщением. Никогда не отправляйте коды входа, пароли и файлы сессий — поддержка их не запрашивает.")


def support_created(ov: Ov, ticket_id: int) -> Rich:
    return notice(ov, "payment_ok", f"Обращение №{ticket_id} принято", "Ответ придёт в этот чат.")


def support_reply(ov: Ov, ticket_id: int, text: str) -> Rich:
    return Rich(ov).e("support").t(" ").b(f"Ответ поддержки (обращение №{ticket_id})").nl(2).t(text)
