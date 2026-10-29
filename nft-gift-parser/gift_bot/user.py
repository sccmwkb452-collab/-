"""Пользовательская часть: главное меню → Парсинг → подарок (или вся база) → список владельцев."""
import math

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from gift_bot.common import (
    ALL, LINE, PRIMARY, SUCCESS, Collections, GiftList, Menu,
    btn, collection_name, esc, main_menu, main_text, pager,
)
from gift_bot.config import Config
from gift_bot.db import Database, GiftRow

router = Router(name="user")

COLLECTIONS_PER_PAGE = 40  # 20 рядов по 2 кнопки
GIFTS_PER_PAGE = 20  # больше 20 NFT за раз не показываем, выгрузки базы файлом нет


def owner_text(g: GiftRow) -> str:
    if g.owner_name and g.owner_name.startswith("@"):
        return esc(g.owner_name)
    if g.owner_link and g.owner_name:
        return f'<a href="{esc(g.owner_link)}">{esc(g.owner_name)}</a>'
    return esc(g.owner_name)


def gift_line(index: int, g: GiftRow) -> str:
    """3. @user - Lunar Snake (#1298), название — скрытая ссылка на подарок."""
    name = esc(collection_name(g.slug))
    return f'{index}. {owner_text(g)} - <a href="{g.url}">{name} (#{g.number})</a>'


async def show(target: Message | CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    """Из кнопки — редактируем сообщение, из команды — отправляем новое."""
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc):  # нажали ту же кнопку ещё раз
                raise
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb, disable_web_page_preview=True)


def home(db: Database) -> str:
    return main_text(db.count_gifts(), len(db.collections()))


@router.message(CommandStart())
async def start(m: Message, config: Config, db: Database) -> None:
    await m.answer(home(db), reply_markup=main_menu(m.from_user.id in config.admin_ids))


@router.callback_query(Menu.filter(F.action == "main"))
async def to_main(c: CallbackQuery, config: Config, db: Database) -> None:
    await show(c, home(db), main_menu(c.from_user.id in config.admin_ids))


@router.callback_query(F.data == "noop")
async def noop(c: CallbackQuery) -> None:
    await c.answer()


@router.callback_query(Menu.filter(F.action == "parse"))
async def parse_menu(c: CallbackQuery, db: Database) -> None:
    await collections_page(c, Collections(page=0), db)


@router.callback_query(Collections.filter())
async def collections_page(c: CallbackQuery, callback_data: Collections, db: Database) -> None:
    cols = db.collections()
    back = [btn("🏠 Главное меню", Menu(action="main"))]
    if not cols:
        await show(c, f"📭 <b>База пока пустая</b>\n{LINE}\n<i>Админ ещё не загрузил подарки — загляни позже.</i>",
                   InlineKeyboardMarkup(inline_keyboard=[back]))
        return
    cols.sort(key=lambda x: collection_name(x[0]).lower())
    pages = math.ceil(len(cols) / COLLECTIONS_PER_PAGE)
    page = min(callback_data.page, pages - 1)
    chunk = cols[page * COLLECTIONS_PER_PAGE:(page + 1) * COLLECTIONS_PER_PAGE]
    buttons = [btn(collection_name(slug), GiftList(slug=slug)) for slug, _ in chunk]
    rows = [[btn("🌐 ВСЯ БАЗА", GiftList(slug=ALL), SUCCESS)]]
    rows += [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows += [pager(lambda p: Collections(page=p), page, pages), back]
    total = sum(n for _, n in cols)
    await show(c, f"🔍 <b>П А Р С И Н Г</b>\n{LINE}\n"
                  f"🎀 Подарков: <b>{len(cols)}</b>   💎 NFT: <b>{total}</b>\n\n"
                  "<i>Выбери подарок или открой всю базу</i> 👇",
               InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r]))


@router.callback_query(GiftList.filter())
async def gift_list(c: CallbackQuery, callback_data: GiftList, db: Database) -> None:
    slug = None if callback_data.slug == ALL else callback_data.slug
    count = db.count_gifts(slug)
    back = [btn("⬅️ К подаркам", Collections()), btn("🏠 Меню", Menu(action="main"))]
    if not count:
        await show(c, "🫥 <i>Здесь пока пусто — база обновилась.</i>", InlineKeyboardMarkup(inline_keyboard=[back]))
        return
    pages = math.ceil(count / GIFTS_PER_PAGE)
    page = min(callback_data.page, pages - 1)
    gifts = db.gifts(slug, page * GIFTS_PER_PAGE, GIFTS_PER_PAGE)
    title = "🌐 ВСЯ БАЗА" if slug is None else f"💎 {esc(collection_name(slug)).upper()}"
    first = page * GIFTS_PER_PAGE + 1
    text = (
        f"<b>{title}</b>\n{LINE}\n"
        f"<blockquote>Найдено: <b>{count}</b> NFT · показаны {first}–{first + len(gifts) - 1}</blockquote>\n\n"
        + "\n".join(gift_line(first + i, g) for i, g in enumerate(gifts))
    )
    if page < pages - 1:
        more = [btn("🔎 Искать ещё", GiftList(slug=callback_data.slug, page=page + 1), PRIMARY)]
    else:
        text += f"\n\n{LINE}\n✅ <b>Это все NFT</b>"
        more = [btn("🔁 Сначала", GiftList(slug=callback_data.slug))] if pages > 1 else []
    rows = [more, back]
    await show(c, text, InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r]))


@router.message()
async def fallback(m: Message, config: Config, db: Database) -> None:
    await start(m, config, db)


@router.callback_query()
async def stale_callback(c: CallbackQuery) -> None:
    await c.answer("Кнопка устарела — открой меню заново: /start", show_alert=True)
