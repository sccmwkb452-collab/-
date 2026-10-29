"""Админ-панель: статистика, рассылка, обязательная подписка, загрузка базы из TXT."""
import asyncio
import logging
import re
import time
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import (
    TelegramAPIError, TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from gift_parser.parser import GiftParser

from gift_bot.common import DANGER, LINE, PRIMARY, SUCCESS, IsAdmin, Menu, btn, esc
from gift_bot.db import Database
from gift_bot.importer import ImportJob, parse_targets

logger = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

MAX_FILE_SIZE = 5 * 1024 * 1024
_tasks: set[asyncio.Task] = set()
_job: ImportJob | None = None
_broadcast_running = False


class AdminStates(StatesGroup):
    upload = State()
    broadcast = State()
    broadcast_confirm = State()
    add_channel = State()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


BACK = [btn("⬅️ Админ-панель", Menu(action="admin"))]


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("📥 Загрузить базу (TXT)", "adm:upload", SUCCESS)],
        [btn("📊 Статистика", "adm:stats", PRIMARY), btn("📢 Рассылка", "adm:broadcast", PRIMARY)],
        [btn("🔒 Обязательная подписка", "adm:subs")],
        [btn("🗑 Очистить базу", "adm:clear", DANGER)],
        [btn("🏠 Главное меню", Menu(action="main"))],
    ])


async def edit(c: CallbackQuery, text: str, rows: list[list]) -> None:
    try:
        await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                                  disable_web_page_preview=True)
    except TelegramBadRequest:
        pass
    await c.answer()


ADMIN_TEXT = (
    f"⚙️ <b>А Д М И Н - П А Н Е Л Ь</b>\n{LINE}\n"
    "<blockquote>Загрузка базы, статистика, рассылка и обязательная подписка.</blockquote>"
)


@router.message(Command("admin"))
async def admin_cmd(m: Message, state: FSMContext) -> None:
    await state.clear()
    await m.answer(ADMIN_TEXT, reply_markup=admin_kb())


@router.callback_query(Menu.filter(F.action == "admin"))
async def admin_menu(c: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit(c, ADMIN_TEXT, admin_kb().inline_keyboard)


@router.message(Command("cancel"))
async def cancel(m: Message, state: FSMContext) -> None:
    await state.clear()
    await m.answer("Отменено.", reply_markup=admin_kb())


# --- статистика ---

@router.callback_query(F.data == "adm:stats")
async def stats(c: CallbackQuery, db: Database) -> None:
    s = db.stats()
    last = datetime.fromtimestamp(s["last_upload"]).strftime("%d.%m.%Y %H:%M") if s["last_upload"] else "—"
    job = "идёт" if _job and not _job.finished else "нет"
    text = (
        f"📊 <b>С Т А Т И С Т И К А</b>\n{LINE}\n"
        "<b>👥 Пользователи</b>\n"
        f"<blockquote>Всего: <b>{s['users']}</b>\n"
        f"✅ Активных: {s['active']}\n"
        f"🚫 Заблокировали бота: {s['blocked']}\n"
        f"🆕 За сутки: {s['today']} · за 7 дней: {s['week']}</blockquote>\n"
        "<b>💎 База NFT</b>\n"
        f"<blockquote>NFT: <b>{s['gifts']}</b> · подарков: {s['collections']}\n"
        f"🕒 Последняя загрузка: {last}\n"
        f"⚡ Парсинг сейчас: {job}</blockquote>\n"
        f"🔒 Каналов в обязательной подписке: <b>{s['channels']}</b>"
    )
    await edit(c, text, [[btn("🔄 Обновить", "adm:stats", PRIMARY)], BACK])


# --- загрузка базы ---

UPLOAD_HELP = (
    "📥 <b>Загрузка базы</b>\n\n"
    "Пришли <b>.txt</b> файл — по одной записи в строке:\n"
    "<code>@username - https://t.me/nft/PlushPepe-1</code> — подарок и его владелец "
    "(сохраняется сразу, без запроса к t.me)\n"
    "<code>https://t.me/nft/PlushPepe-1</code> — один подарок\n"
    "<code>PlushPepe-1</code> — то же самое\n"
    "<code>PlushPepe 1 500</code> — номера с 1 по 500\n"
    "<code>PlushPepe</code> — вся коллекция\n\n"
    "Бот спарсит подарки и разложит их по моделям. Уже загруженные номера обновятся.\n"
    "/cancel — отмена"
)


def progress_text(job: ImportJob) -> str:
    total = f"{job.total}" if job.total else "?"
    elapsed = int(time.monotonic() - job.started_at)
    status = "⛔ Остановлено" if job.cancelled else ("✅ Готово" if job.finished else "⏳ Парсинг…")
    share = job.done / job.total if job.total else 0
    bar = "▰" * round(share * 12) + "▱" * (12 - round(share * 12))
    return (
        f"<b>{status}</b>\n{LINE}\n"
        f"{bar} <b>{round(share * 100)}%</b>\n\n"
        f"<blockquote>📄 Записей в файле: {len(job.targets)}\n"
        f"🎀 Сейчас: {esc(job.current)}\n"
        f"🔢 Проверено: {job.done} / {total}\n"
        f"💎 Сохранено NFT: <b>{job.found}</b>\n"
        f"♻️ Повторов пропущено: {job.skipped}\n"
        f"⏱ Время: {elapsed // 60} мин {elapsed % 60} с</blockquote>"
    )


STOP_KB = InlineKeyboardMarkup(inline_keyboard=[[btn("⛔ Остановить", "adm:stop", DANGER)]])


@router.callback_query(F.data == "adm:upload")
async def upload_start(c: CallbackQuery, state: FSMContext) -> None:
    if _job and not _job.finished:
        await c.answer("Парсинг уже идёт — дождись окончания или останови его.", show_alert=True)
        return
    await state.set_state(AdminStates.upload)
    await edit(c, UPLOAD_HELP, [BACK])


@router.message(AdminStates.upload, F.document)
async def upload_file(m: Message, state: FSMContext, bot: Bot, db: Database, parser: GiftParser) -> None:
    global _job
    doc = m.document
    if not (doc.file_name or "").lower().endswith(".txt"):
        await m.answer("Нужен файл с расширением .txt")
        return
    if (doc.file_size or 0) > MAX_FILE_SIZE:
        await m.answer("Файл больше 5 МБ.")
        return
    if _job and not _job.finished:
        await m.answer("Парсинг уже идёт.")
        return
    raw = (await bot.download(doc)).read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251", errors="replace")
    parsed = parse_targets(text)
    if not parsed.targets:
        await m.answer("В файле не нашлось ни одной ссылки или коллекции. Проверь формат.\n\n" + UPLOAD_HELP)
        return
    await state.clear()
    if parsed.bad_lines:
        sample = "\n".join(esc(x) for x in parsed.bad_lines[:5])
        await m.answer(f"⚠️ Пропущено непонятных строк: {len(parsed.bad_lines)}\n<code>{sample}</code>")

    job = _job = ImportJob(parsed.targets, skipped=parsed.duplicates)
    status = await m.answer(progress_text(job), reply_markup=STOP_KB)

    async def report(j: ImportJob) -> None:
        try:
            await status.edit_text(progress_text(j), reply_markup=None if j.finished else STOP_KB)
        except TelegramBadRequest:
            pass

    async def run() -> None:
        try:
            await job.run(db, parser, report)
        except Exception:
            logger.exception("Ошибка парсинга")
            await m.answer("❌ Парсинг прервался из-за ошибки, подробности в логе. "
                           "То, что успели спарсить, сохранено.")
        await report(job)
        await m.answer(f"Загрузка завершена: сохранено {job.found} NFT, повторов пропущено: {job.skipped}.", reply_markup=admin_kb())

    _spawn(run())


@router.message(AdminStates.upload)
async def upload_wrong(m: Message) -> None:
    await m.answer("Пришли .txt файл документом или /cancel.")


@router.callback_query(F.data == "adm:stop")
async def upload_stop(c: CallbackQuery) -> None:
    if _job and not _job.finished:
        _job.cancelled = True
        await c.answer("Останавливаю… сохранённое останется в базе.")
    else:
        await c.answer("Парсинг не идёт.")


@router.callback_query(F.data == "adm:clear")
async def clear_ask(c: CallbackQuery) -> None:
    await edit(c, "🗑 Удалить <b>все</b> NFT из базы? Пользователи и каналы останутся.",
               [[btn("🗑 Да, удалить всё", "adm:clear_yes", DANGER)], BACK])


@router.callback_query(F.data == "adm:clear_yes")
async def clear_yes(c: CallbackQuery, db: Database) -> None:
    if _job and not _job.finished:
        await c.answer("Сначала останови парсинг.", show_alert=True)
        return
    db.clear_gifts()
    await edit(c, "✅ База NFT очищена.", [BACK])


# --- рассылка ---

@router.callback_query(F.data == "adm:broadcast")
async def broadcast_start(c: CallbackQuery, state: FSMContext) -> None:
    if _broadcast_running:
        await c.answer("Рассылка уже идёт.", show_alert=True)
        return
    await state.set_state(AdminStates.broadcast)
    await edit(c, "📢 <b>Рассылка</b>\n\nПришли сообщение для рассылки — текст, фото, видео, "
                  "что угодно. Оно будет скопировано всем пользователям как есть.\n/cancel — отмена",
               [BACK])


@router.message(AdminStates.broadcast)
async def broadcast_preview(m: Message, state: FSMContext, db: Database) -> None:
    await state.update_data(chat_id=m.chat.id, message_id=m.message_id)
    await state.set_state(AdminStates.broadcast_confirm)
    await m.send_copy(m.chat.id)
    await m.answer(
        f"☝️ Так будет выглядеть сообщение. Получателей: {len(db.user_ids())}. Отправляем?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [btn("✅ Отправить", "adm:bc_go", SUCCESS), btn("❌ Отмена", Menu(action="admin"), DANGER)],
        ]),
    )


async def _send_copy(bot: Bot, user_id: int, chat_id: int, message_id: int) -> bool:
    for _ in range(3):
        try:
            await bot.copy_message(user_id, chat_id, message_id)
            return True
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except (TelegramForbiddenError, TelegramBadRequest):
            return False
        except TelegramAPIError:
            await asyncio.sleep(1)
    return False


@router.callback_query(AdminStates.broadcast_confirm, F.data == "adm:bc_go")
async def broadcast_go(c: CallbackQuery, state: FSMContext, bot: Bot, db: Database) -> None:
    global _broadcast_running
    data = await state.get_data()
    await state.clear()
    if _broadcast_running:
        await c.answer("Рассылка уже идёт.", show_alert=True)
        return
    _broadcast_running = True
    users = db.user_ids()
    await edit(c, f"⏳ Рассылка запущена: {len(users)} получателей.", [])

    async def run() -> None:
        global _broadcast_running
        ok = fail = 0
        try:
            for uid in users:
                if await _send_copy(bot, uid, data["chat_id"], data["message_id"]):
                    ok += 1
                else:
                    fail += 1
                    db.set_blocked(uid)
                await asyncio.sleep(0.05)  # ~20 сообщений в секунду, ниже лимита Telegram
        finally:
            _broadcast_running = False
            await c.message.answer(
                f"📢 Рассылка завершена.\n✅ Доставлено: {ok}\n🚫 Не доставлено: {fail}",
                reply_markup=admin_kb(),
            )

    _spawn(run())


# --- обязательная подписка ---

async def subs_view(c: CallbackQuery, db: Database) -> None:
    channels = db.channels()
    lines = [f"• <a href=\"{esc(ch.url)}\">{esc(ch.title)}</a> <code>{ch.chat_id}</code>" for ch in channels]
    text = "🔒 <b>Обязательная подписка</b>\n\n" + ("\n".join(lines) if lines else "Каналов нет — бот открыт для всех.")
    rows = [[btn(f"❌ {ch.title}", f"adm:subdel:{ch.chat_id}", DANGER)] for ch in channels]
    rows += [[btn("➕ Добавить канал", "adm:subadd", SUCCESS)], BACK]
    await edit(c, text, rows)


@router.callback_query(F.data == "adm:subs")
async def subs(c: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    await subs_view(c, db)


@router.callback_query(F.data.startswith("adm:subdel:"))
async def subs_delete(c: CallbackQuery, db: Database) -> None:
    db.remove_channel(c.data.removeprefix("adm:subdel:"))
    await subs_view(c, db)


@router.callback_query(F.data == "adm:subadd")
async def subs_add_start(c: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.add_channel)
    await edit(c, (
        "➕ <b>Добавить канал</b>\n\n"
        "1. Добавь бота в канал/группу <b>администратором</b>.\n"
        "2. Пришли сюда одно из:\n"
        "• <code>@username</code> или ссылку <code>https://t.me/username</code>\n"
        "• пересланный пост из канала\n"
        "• ID и ссылку-приглашение: <code>-1001234567890 https://t.me/+abc</code>\n"
        "/cancel — отмена"
    ), [[btn("⬅️ Назад", "adm:subs")]])


_PUBLIC_LINK_RE = re.compile(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,})/?$")
_INVITE_RE = re.compile(r"(?:https?://)?t\.me/(?:\+|joinchat/)\S+")


@router.message(AdminStates.add_channel)
async def subs_add(m: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    ref: str | int | None = None
    url: str | None = None
    if m.forward_origin and getattr(m.forward_origin, "chat", None):
        ref = m.forward_origin.chat.id
    elif m.text:
        for part in m.text.split():
            if inv := _INVITE_RE.fullmatch(part):
                url = inv.group(0) if inv.group(0).startswith("http") else "https://" + inv.group(0)
            elif pub := _PUBLIC_LINK_RE.fullmatch(part):
                ref = "@" + pub.group(1)
            elif re.fullmatch(r"@[A-Za-z0-9_]{4,}", part):
                ref = part
            elif re.fullmatch(r"-?\d+", part):
                ref = int(part)
    if ref is None:
        await m.answer("Не понял, какой это канал. Пришли @username, ссылку или перешли пост. /cancel — отмена")
        return
    try:
        chat = await bot.get_chat(ref)
        me = await bot.get_chat_member(chat.id, bot.id)
    except TelegramAPIError as exc:
        await m.answer(f"Не получилось открыть канал: {esc(str(exc))}\nБот добавлен в него?")
        return
    if me.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
        await m.answer("Бот не админ в этом канале — без этого он не сможет проверять подписку.")
        return
    if not url:
        if chat.username:
            url = f"https://t.me/{chat.username}"
        else:
            try:
                url = chat.invite_link or await bot.export_chat_invite_link(chat.id)
            except TelegramAPIError:
                await m.answer("Канал приватный — пришли ID вместе со ссылкой-приглашением.")
                return
    db.add_channel(str(chat.id), chat.title or str(chat.id), url)
    await state.clear()
    await m.answer(f"✅ Канал <b>{esc(chat.title)}</b> добавлен в обязательную подписку.",
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn("🔒 К подпискам", "adm:subs")], BACK]))
