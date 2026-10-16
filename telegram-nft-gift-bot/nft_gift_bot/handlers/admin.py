"""Admin panel. The whole router is gated by AdminFilter (numeric IDs from ADMIN_IDS).

Non-admins never see that these commands exist: their messages fall through
to the regular handlers.
"""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.admin.guards import AdminFilter
from nft_gift_bot.admin.service import AdminService
from nft_gift_bot.bot import texts
from nft_gift_bot.bot.notifier import send_safe
from nft_gift_bot.config.emoji import EMOJI_KEYS, is_configured_id, resolve
from nft_gift_bot.config.settings import Settings
from nft_gift_bot.database.base import utcnow
from nft_gift_bot.keyboards import inline
from nft_gift_bot.keyboards.callbacks import AdminCb
from nft_gift_bot.middlewares.context import EmojiMiddleware
from nft_gift_bot.payments.ton import format_ton
from nft_gift_bot.services.crypto import mask

HELP = (
    "🛠 Команды администратора\n\n"
    "/admin — панель\n"
    "/user <telegram_id> — карточка пользователя\n"
    "/grant <telegram_id> <дни> — выдать/продлить подписку\n"
    "/block <telegram_id>, /unblock <telegram_id>\n"
    "/payments [pending|paid|expired|cancelled|failed]\n"
    "/reply <№ обращения> <текст> — ответ в поддержку\n"
    "/set_price <TON> — цена подписки\n"
    "/set_days <дни> — срок подписки\n"
    "/set_emoji <ключ> <custom_emoji_id | -> — Premium Emoji\n"
    "/check_emoji — проверить настроенные Premium Emoji\n\n"
    f"Ключи эмодзи: {', '.join(EMOJI_KEYS)}"
)


def _parse_tg_id(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value.isdigit() and len(value) <= 15 else None


def create_admin_router(admin_ids: frozenset[int]) -> Router:
    router = Router(name="admin")
    router.message.filter(AdminFilter(admin_ids))
    router.callback_query.filter(AdminFilter(admin_ids))

    def svc(session: AsyncSession, settings: Settings, admin_id: int) -> AdminService:
        return AdminService(session, settings, admin_id)

    async def stats_text(service: AdminService) -> str:
        s = await service.stats(utcnow())
        by_status = ", ".join(f"{k}: {v}" for k, v in sorted(s.payments_by_status.items())) or "—"
        return (
            "📊 Статистика\n\n"
            f"Пользователей: {s.users}\n"
            f"Активных подписок: {s.active_subscriptions}\n"
            f"Подключённых аккаунтов: {s.active_connections}\n"
            f"Выручка: {format_ton(s.revenue_nano)} TON\n"
            f"Платежи: {by_status}\n"
            f"Открытых обращений: {s.open_tickets}"
        )

    @router.message(Command("admin"))
    async def panel(message: Message, session: AsyncSession, settings: Settings) -> None:
        service = svc(session, settings, message.from_user.id)
        service.audit("open_panel")
        await message.answer(await stats_text(service), reply_markup=inline.admin_panel(), parse_mode=None)

    @router.callback_query(AdminCb.filter())
    async def section(cb: CallbackQuery, callback_data: AdminCb, session: AsyncSession, settings: Settings) -> None:
        service = svc(session, settings, cb.from_user.id)
        name = callback_data.section
        lines: list[str]
        if name == "stats":
            text = await stats_text(service)
        elif name == "users":
            lines = [f"{u.telegram_id} · @{u.username or '—'} · {texts.fmt_dt(u.created_at)}" for u in await service.recent_users()]
            text = "👥 Последние пользователи\n\n" + ("\n".join(lines) or "—")
        elif name == "payments":
            lines = [
                f"#{p.id} {p.memo} · {format_ton(p.amount_nano)} TON · {p.status} · user {p.user_id} · {texts.fmt_dt(p.created_at)}"
                for p in await service.recent_payments()
            ]
            text = "💳 Последние платежи\n\n" + ("\n".join(lines) or "—")
        elif name == "transfers":
            lines = [
                f"#{t.id} {t.gift_title} → {t.recipient_label} · {t.status}{' (' + t.error_code + ')' if t.error_code else ''} · {texts.fmt_dt(t.created_at)}"
                for t in await service.recent_transfers()
            ]
            text = "🎁 Последние передачи\n\n" + ("\n".join(lines) or "—")
        elif name == "tickets":
            lines = [f"№{t.id} · user {t.user_id} · {t.message[:80]}" for t in await service.open_tickets()]
            text = "🆘 Открытые обращения\n\n" + ("\n".join(lines) or "—") + "\n\nОтвет: /reply <№> <текст>"
        elif name == "audit":
            lines = [f"{texts.fmt_dt(a.created_at)} · {a.admin_telegram_id} · {a.action} {a.target or ''}" for a in await service.recent_audit()]
            text = "🧾 Журнал действий администраторов\n\n" + ("\n".join(lines) or "—")
        else:
            text = HELP
        service.audit("view_section", name)
        await cb.answer()
        if cb.message:
            await cb.message.answer(text[:4000], parse_mode=None)

    @router.message(Command("user"))
    async def user_card(message: Message, command: CommandObject, session: AsyncSession, settings: Settings) -> None:
        tg_id = _parse_tg_id(command.args)
        if tg_id is None:
            await message.answer("Формат: /user <telegram_id>")
            return
        card = await svc(session, settings, message.from_user.id).user_card(tg_id)
        if card is None:
            await message.answer("Пользователь не найден.")
            return
        sub = card.subscription
        acc = card.account
        pays = "\n".join(f"  {p.memo} · {format_ton(p.amount_nano)} TON · {p.status}" for p in card.payments) or "  —"
        await message.answer(
            f"👤 {card.user.telegram_id} @{card.user.username or '—'}\n"
            f"Заблокирован: {'да' if card.user.is_blocked else 'нет'}\n"
            f"Подписка: {sub.status + ' до ' + texts.fmt_dt(sub.expires_at) if sub else 'нет'}\n"
            # Connection IDs are never shown, even to admins.
            f"Аккаунт: {(mask(acc.telegram_account_id) + ' · ' + acc.status) if acc else 'нет'}\n"
            f"Платежи:\n{pays}",
            parse_mode=None,
        )

    @router.message(Command("grant"))
    async def grant(message: Message, command: CommandObject, session: AsyncSession, settings: Settings) -> None:
        parts = (command.args or "").split()
        if len(parts) != 2 or _parse_tg_id(parts[0]) is None or not parts[1].isdigit() or not 1 <= int(parts[1]) <= 3650:
            await message.answer("Формат: /grant <telegram_id> <дни 1–3650>")
            return
        sub = await svc(session, settings, message.from_user.id).grant_subscription(int(parts[0]), int(parts[1]), utcnow())
        await message.answer(f"Подписка активна до {texts.fmt_dt(sub.expires_at)}" if sub else "Пользователь не найден.")

    @router.message(Command("block", "unblock"))
    async def block(message: Message, command: CommandObject, session: AsyncSession, settings: Settings) -> None:
        tg_id = _parse_tg_id(command.args)
        if tg_id is None:
            await message.answer(f"Формат: /{command.command} <telegram_id>")
            return
        if tg_id in admin_ids:
            await message.answer("Нельзя заблокировать администратора.")
            return
        user = await svc(session, settings, message.from_user.id).set_blocked(tg_id, command.command == "block")
        await message.answer("Готово." if user else "Пользователь не найден.")

    @router.message(Command("payments"))
    async def payments(message: Message, command: CommandObject, session: AsyncSession, settings: Settings) -> None:
        status = (command.args or "").strip() or None
        if status and status not in texts.PAYMENT_STATUS:
            await message.answer("Статусы: " + ", ".join(texts.PAYMENT_STATUS))
            return
        rows = await svc(session, settings, message.from_user.id).recent_payments(30, status)
        lines = [f"#{p.id} {p.memo} · {format_ton(p.amount_nano)} TON · {p.status} · user {p.user_id}" for p in rows]
        await message.answer("\n".join(lines) or "Платежей нет.", parse_mode=None)

    @router.message(Command("reply"))
    async def reply(message: Message, command: CommandObject, bot: Bot, session: AsyncSession, settings: Settings, emoji: dict) -> None:
        parts = (command.args or "").split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            await message.answer("Формат: /reply <№ обращения> <текст>")
            return
        result = await svc(session, settings, message.from_user.id).reply_ticket(int(parts[0]), parts[1], utcnow())
        if result is None:
            await message.answer("Обращение не найдено или уже закрыто.")
            return
        ticket, user = result
        delivered = await send_safe(bot, user.telegram_id, texts.support_reply(emoji, ticket.id, parts[1]))
        await message.answer("Ответ отправлен." if delivered else "Сохранено, но доставить не удалось.")

    @router.message(Command("set_price"))
    async def set_price(message: Message, command: CommandObject, session: AsyncSession, settings: Settings) -> None:
        try:
            price = await svc(session, settings, message.from_user.id).set_price((command.args or "").strip())
        except (ValueError, ArithmeticError):
            await message.answer("Формат: /set_price 10 (положительное число, до 9 знаков после точки)")
            return
        await message.answer(f"Цена подписки: {price} TON. Новые счета будут выставляться по ней.")

    @router.message(Command("set_days"))
    async def set_days(message: Message, command: CommandObject, session: AsyncSession, settings: Settings) -> None:
        try:
            days = await svc(session, settings, message.from_user.id).set_days((command.args or "").strip())
        except ValueError:
            await message.answer("Формат: /set_days 30 (1–3650)")
            return
        await message.answer(f"Срок подписки: {days} дн.")

    @router.message(Command("set_emoji"))
    async def set_emoji(
        message: Message, command: CommandObject, bot: Bot, session: AsyncSession, settings: Settings,
        emoji_cache: EmojiMiddleware,
    ) -> None:
        parts = (command.args or "").split()
        if len(parts) != 2:
            await message.answer(HELP, parse_mode=None)
            return
        if parts[1] != "-":
            # Verify with Telegram before saving: an invalid ID would break every message using it.
            try:
                stickers = await bot.get_custom_emoji_stickers([parts[1]]) if parts[1].isdigit() else []
            except TelegramAPIError:
                stickers = []
            if not stickers:
                await message.answer("Telegram не нашёл custom emoji с таким ID. Ничего не изменено.")
                return
        try:
            await svc(session, settings, message.from_user.id).set_emoji(parts[0], parts[1])
        except ValueError as exc:
            await message.answer(str(exc), parse_mode=None)
            return
        emoji_cache.invalidate()
        await message.answer("Сохранено. Проверьте: /check_emoji")

    @router.message(Command("check_emoji"))
    async def check_emoji(message: Message, bot: Bot, emoji: dict) -> None:
        specs = [resolve(key, emoji) for key in EMOJI_KEYS]
        configured = [s for s in specs if is_configured_id(s.custom_id)]
        found: set[str] = set()
        if configured:
            try:
                stickers = await bot.get_custom_emoji_stickers([s.custom_id for s in configured])
                found = {s.custom_emoji_id for s in stickers if s.custom_emoji_id}
            except TelegramAPIError as exc:
                await message.answer(f"Telegram не принял список ID: {exc.message[:200]}", parse_mode=None)
                return
        lines = []
        for s in specs:
            if not is_configured_id(s.custom_id):
                state = "fallback (демо-значение)"
            else:
                state = "✅ доступен" if s.custom_id in found else "❌ не найден Telegram — замените ID"
            lines.append(f"{s.fallback} {s.key}: {state}")
        await message.answer("Premium Emoji\n\n" + "\n".join(lines), parse_mode=None)

    @router.message(Command("admin_help"))
    async def admin_help(message: Message) -> None:
        await message.answer(HELP, parse_mode=None)

    return router
