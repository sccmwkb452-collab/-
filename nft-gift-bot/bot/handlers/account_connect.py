"""
Раздел «Подключить аккаунт» — MTProto авторизация через Telethon.

Пользователь проходит официальный Telegram-flow (телефон → код → опционально 2FA).
Сессия хранится зашифрованной (Fernet) в БД. tdata не принимаются.
Сессионные файлы не отправляются администратору и не доступны никому кроме самого
владельца.
"""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import back_kb, connect_account_kb
from bot.states.account_states import AccountConnect
from bot.ui.templates import (
    account_connected,
    account_disconnected,
    account_error,
    account_info,
    account_pending_2fa,
    account_pending_code,
)
from config import settings
from database.models.connected_account import AccountStatus
from database.models.user import User
from services.account_service import AccountService

logger = logging.getLogger(__name__)
router = Router(name="account_connect")

# In-memory registry of active Telethon clients during the auth flow.
# Keyed by user_id. Cleaned up on success / failure / cancel.
_pending_clients: dict[int, object] = {}


def _make_client(session_string: str = ""):
    """Create a Telethon client using the configured api_id / api_hash."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    return TelegramClient(
        StringSession(session_string),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )


async def _cleanup_client(user_id: int) -> None:
    client = _pending_clients.pop(user_id, None)
    if client is not None:
        try:
            await client.disconnect()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Info screen — show current status
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "connect:info")
async def cb_connect_info(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    account = await AccountService(session).get(db_user.id)

    if account is None or account.status == AccountStatus.DISCONNECTED:
        text, entities = account_info()
        kb = connect_account_kb("none")
    elif account.status == AccountStatus.CONNECTED:
        text, entities = account_connected(account)
        kb = connect_account_kb("connected")
    elif account.status in (AccountStatus.PENDING_CODE, AccountStatus.PENDING_2FA):
        if account.status == AccountStatus.PENDING_CODE:
            text, entities = account_pending_code()
        else:
            text, entities = account_pending_2fa()
        kb = connect_account_kb("pending")
    else:  # ERROR
        text, entities = account_error(account.error_message or "")
        kb = connect_account_kb("none")

    await callback.message.edit_text(text=text, entities=entities, reply_markup=kb)
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
#  Start auth flow — ask for phone number
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "connect:start")
async def cb_connect_start(
    callback: CallbackQuery,
    db_user: User,
    state: FSMContext,
) -> None:
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        await callback.answer(
            "❌ MTProto не настроен. Обратитесь к администратору.",
            show_alert=True,
        )
        return
    if not settings.account_encryption_key:
        await callback.answer(
            "❌ Шифрование сессий не настроено. Обратитесь к администратору.",
            show_alert=True,
        )
        return

    await state.set_state(AccountConnect.waiting_phone)
    await callback.message.edit_text(
        "📱 Введи номер телефона в международном формате:\n\n"
        "<code>+79123456789</code>\n\n"
        "<i>Telegram отправит код подтверждения на этот номер.</i>",
        parse_mode="HTML",
        reply_markup=back_kb("connect:cancel"),
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
#  Cancel / back — clear state and pending client
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "connect:cancel")
async def cb_connect_cancel(
    callback: CallbackQuery,
    db_user: User,
    state: FSMContext,
) -> None:
    await state.clear()
    await _cleanup_client(db_user.id)
    text, entities = account_info()
    await callback.message.edit_text(
        text=text, entities=entities, reply_markup=connect_account_kb("none")
    )
    await callback.answer("Отменено")


# ─────────────────────────────────────────────────────────────────────────────
#  Step 1 — receive phone number
# ─────────────────────────────────────────────────────────────────────────────

@router.message(AccountConnect.waiting_phone)
async def handle_phone(
    message: Message,
    db_user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    phone = (message.text or "").strip()
    # Delete message so phone number isn't left visible in chat
    try:
        await message.delete()
    except Exception:
        pass

    if not phone.startswith("+") or len(phone) < 8:
        await message.answer(
            "❌ Неверный формат. Введи номер с кодом страны, например:\n"
            "<code>+79123456789</code>",
            parse_mode="HTML",
        )
        return

    status_msg = await message.answer("⏳ Отправляю запрос в Telegram...")

    try:
        client = _make_client()
        await client.connect()
        result = await client.send_code_request(phone)
        _pending_clients[db_user.id] = client

        await AccountService(session).start_auth(db_user.id, phone)
        await session.commit()

        await state.set_state(AccountConnect.waiting_code)
        await state.update_data(
            phone=phone,
            phone_code_hash=result.phone_code_hash,
        )

        await status_msg.edit_text(
            "✅ Код отправлен!\n\n"
            "Telegram прислал тебе код подтверждения.\n"
            "Введи его здесь (только цифры, например <code>12345</code>):\n\n"
            "<i>Есть 5 минут до истечения кода.</i>",
            parse_mode="HTML",
            reply_markup=back_kb("connect:cancel"),
        )
    except Exception as exc:
        await _cleanup_client(db_user.id)
        await state.clear()
        logger.warning("send_code_request failed for user_id=%d: %s", db_user.id, exc)
        err = _friendly_error(exc)
        await status_msg.edit_text(
            f"❌ Ошибка: {err}\n\nПопробуй снова — нажми «Подключить аккаунт».",
            reply_markup=back_kb("connect:info"),
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Step 2 — receive verification code
# ─────────────────────────────────────────────────────────────────────────────

@router.message(AccountConnect.waiting_code)
async def handle_code(
    message: Message,
    db_user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    code = (message.text or "").strip().replace(" ", "").replace("-", "")
    try:
        await message.delete()
    except Exception:
        pass

    if not code.isdigit():
        await message.answer(
            "❌ Введи только цифры кода, например: <code>12345</code>",
            parse_mode="HTML",
        )
        return

    client = _pending_clients.get(db_user.id)
    if client is None:
        await state.clear()
        await message.answer(
            "⚠️ Сессия авторизации устарела (бот перезапускался).\n"
            "Нажми «Подключить аккаунт» и начни заново.",
            reply_markup=back_kb("connect:info"),
        )
        return

    data = await state.get_data()
    phone = data["phone"]
    phone_code_hash = data["phone_code_hash"]

    status_msg = await message.answer("⏳ Проверяю код...")

    try:
        from telethon.errors import SessionPasswordNeededError
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        session_string = client.session.save()
        await _cleanup_client(db_user.id)

        svc = AccountService(session)
        account = await svc.get(db_user.id)
        await svc.save_session(account, session_string)
        await session.commit()

        await state.clear()
        await status_msg.edit_text(
            "✅ Аккаунт успешно подключён!\n\n"
            "Сессия зашифрована и сохранена.",
            reply_markup=back_kb("connect:info"),
        )
        logger.info("Account connected for user_id=%d", db_user.id)

    except Exception as exc:
        from telethon.errors import SessionPasswordNeededError  # noqa: F811
        if isinstance(exc, SessionPasswordNeededError):
            svc = AccountService(session)
            account = await svc.get(db_user.id)
            await svc.mark_pending_2fa(account)
            await session.commit()
            await state.set_state(AccountConnect.waiting_2fa)
            await status_msg.edit_text(
                "🔐 Включена двухфакторная аутентификация.\n\n"
                "Введи пароль от аккаунта:",
                reply_markup=back_kb("connect:cancel"),
            )
        else:
            await _cleanup_client(db_user.id)
            await state.clear()
            logger.warning("sign_in failed for user_id=%d: %s", db_user.id, exc)
            err = _friendly_error(exc)
            await status_msg.edit_text(
                f"❌ Ошибка: {err}\n\nПопробуй снова.",
                reply_markup=back_kb("connect:info"),
            )


# ─────────────────────────────────────────────────────────────────────────────
#  Step 3 — receive 2FA password
# ─────────────────────────────────────────────────────────────────────────────

@router.message(AccountConnect.waiting_2fa)
async def handle_2fa(
    message: Message,
    db_user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    password = message.text or ""
    try:
        await message.delete()
    except Exception:
        pass

    client = _pending_clients.get(db_user.id)
    if client is None:
        await state.clear()
        await message.answer(
            "⚠️ Сессия устарела. Начни авторизацию заново.",
            reply_markup=back_kb("connect:info"),
        )
        return

    status_msg = await message.answer("⏳ Проверяю пароль...")

    try:
        await client.sign_in(password=password)
        session_string = client.session.save()
        await _cleanup_client(db_user.id)

        svc = AccountService(session)
        account = await svc.get(db_user.id)
        await svc.save_session(account, session_string)
        await session.commit()

        await state.clear()
        await status_msg.edit_text(
            "✅ Аккаунт успешно подключён!\n\n"
            "Сессия зашифрована и сохранена.",
            reply_markup=back_kb("connect:info"),
        )
        logger.info("Account connected (2FA) for user_id=%d", db_user.id)

    except Exception as exc:
        await _cleanup_client(db_user.id)
        await state.clear()
        logger.warning("2FA sign_in failed for user_id=%d: %s", db_user.id, exc)
        err = _friendly_error(exc)

        svc = AccountService(session)
        account = await svc.get(db_user.id)
        if account:
            await svc.set_error(account, str(exc)[:200])
            await session.commit()

        await status_msg.edit_text(
            f"❌ Ошибка 2FA: {err}\n\nПопробуй снова.",
            reply_markup=back_kb("connect:info"),
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Disconnect
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "connect:disconnect")
async def cb_disconnect(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    svc = AccountService(session)
    account = await svc.get(db_user.id)
    if account:
        await svc.disconnect(account)
        await session.commit()
    await state.clear()
    await _cleanup_client(db_user.id)

    text, entities = account_disconnected()
    await callback.message.edit_text(
        text=text,
        entities=entities,
        reply_markup=connect_account_kb("none"),
    )
    await callback.answer("Аккаунт отключён")
    logger.info("Account disconnected for user_id=%d", db_user.id)


# ─────────────────────────────────────────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────────────────────────────────────────

def _friendly_error(exc: Exception) -> str:
    name = type(exc).__name__
    msg = str(exc)
    if "PHONE_NUMBER_INVALID" in msg or "PHONE_NUMBER_INVALID" in name:
        return "Неверный номер телефона."
    if "PHONE_CODE_INVALID" in msg or "PHONE_CODE_INVALID" in name:
        return "Неверный код подтверждения."
    if "PHONE_CODE_EXPIRED" in msg or "PHONE_CODE_EXPIRED" in name:
        return "Код истёк. Запроси новый."
    if "PASSWORD_HASH_INVALID" in msg:
        return "Неверный пароль 2FA."
    if "FLOOD_WAIT" in msg or "FloodWait" in name:
        return "Слишком много попыток. Попробуй позже."
    if "AUTH_KEY_UNREGISTERED" in msg:
        return "Сессия устарела."
    return f"{name}: {msg[:120]}"
