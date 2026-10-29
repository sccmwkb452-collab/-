"""Пользовательская часть: главное меню → Парсинг → коллекция → модель → список NFT."""
import math

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message

from gift_bot.common import (
    MAIN_TEXT, Collections, Menu, ModelFile, ModelGifts, Models,
    btn, collection_name, esc, main_menu, pager,
)
from gift_bot.config import Config
from gift_bot.db import Database, GiftRow

router = Router(name="user")

COLLECTIONS_PER_PAGE = 20
MODELS_PER_PAGE = 30
GIFTS_PER_PAGE = 15


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
        await target.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb, disable_web_page_preview=True)


@router.message(CommandStart())
async def start(m: Message, config: Config) -> None:
    await m.answer(MAIN_TEXT, reply_markup=main_menu(m.from_user.id in config.admin_ids))


@router.callback_query(Menu.filter(F.action == "main"))
async def to_main(c: CallbackQuery, config: Config) -> None:
    await show(c, MAIN_TEXT, main_menu(c.from_user.id in config.admin_ids))


@router.callback_query(F.data == "noop")
async def noop(c: CallbackQuery) -> None:
    await c.answer()


@router.callback_query(Menu.filter(F.action == "parse"))
async def parse_menu(c: CallbackQuery, db: Database) -> None:
    cols = db.collections()
    if len(cols) == 1:
        await models_page(c, Models(slug=cols[0][0]), db)
    else:
        await collections_page(c, Collections(page=0), db)


@router.callback_query(Collections.filter())
async def collections_page(c: CallbackQuery, callback_data: Collections, db: Database) -> None:
    cols = db.collections()
    back = [btn("⬅️ Главное меню", Menu(action="main"))]
    if not cols:
        await show(c, "📭 База пока пустая — админ ещё не загрузил подарки.",
                   InlineKeyboardMarkup(inline_keyboard=[back]))
        return
    pages = math.ceil(len(cols) / COLLECTIONS_PER_PAGE)
    page = min(callback_data.page, pages - 1)
    chunk = cols[page * COLLECTIONS_PER_PAGE:(page + 1) * COLLECTIONS_PER_PAGE]
    buttons = [btn(f"{collection_name(slug)} · {n}", Models(slug=slug)) for slug, n in chunk]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows += [pager(lambda p: Collections(page=p), page, pages), back]
    total = sum(n for _, n in cols)
    await show(c, f"🔍 <b>Парсинг</b>\n\nКоллекций: {len(cols)}, NFT в базе: {total}\nВыбери коллекцию:",
               InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r]))


@router.callback_query(Models.filter())
async def models_page(c: CallbackQuery, callback_data: Models, db: Database) -> None:
    models = db.models(callback_data.slug)
    single_collection = len(db.collections()) <= 1
    back = [btn("⬅️ Главное меню", Menu(action="main"))] if single_collection \
        else [btn("⬅️ К коллекциям", Collections())]
    if not models:
        await show(c, "В этой коллекции нет подарков.", InlineKeyboardMarkup(inline_keyboard=[back]))
        return
    pages = math.ceil(len(models) / MODELS_PER_PAGE)
    page = min(callback_data.page, pages - 1)
    chunk = models[page * MODELS_PER_PAGE:(page + 1) * MODELS_PER_PAGE]
    buttons = [btn(f"{m.name} · {m.count}", ModelGifts(model_id=m.id)) for m in chunk]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows += [pager(lambda p: Models(slug=callback_data.slug, page=p), page, pages), back]
    total = sum(m.count for m in models)
    await show(
        c,
        f"🎁 <b>{esc(collection_name(callback_data.slug))}</b>\n\n"
        f"Моделей: {len(models)}, NFT: {total}\nВыбери модель:",
        InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r]),
    )


@router.callback_query(ModelGifts.filter())
async def model_gifts(c: CallbackQuery, callback_data: ModelGifts, db: Database) -> None:
    model = db.model(callback_data.model_id)
    if not model or not model.count:
        await c.answer("Модель не найдена — база обновилась.", show_alert=True)
        return
    pages = math.ceil(model.count / GIFTS_PER_PAGE)
    page = min(callback_data.page, pages - 1)
    gifts = db.gifts_by_model(model.id, page * GIFTS_PER_PAGE, GIFTS_PER_PAGE)
    rarity = f" · {gifts[0].model_rarity:g}%" if gifts and gifts[0].model_rarity is not None else ""
    text = (
        f"🎁 <b>{esc(collection_name(model.slug))} — {esc(model.name)}</b>{rarity}\n"
        f"Всего NFT: {model.count}\n\n" + "\n".join(
            gift_line(page * GIFTS_PER_PAGE + i, g) for i, g in enumerate(gifts, 1))
    )
    rows = [
        pager(lambda p: ModelGifts(model_id=model.id, page=p), page, pages),
        [btn("📥 Скачать списком (TXT)", ModelFile(model_id=model.id))],
        [btn("⬅️ К моделям", Models(slug=model.slug))],
    ]
    await show(c, text, InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r]))


@router.callback_query(ModelFile.filter())
async def model_file(c: CallbackQuery, callback_data: ModelFile, db: Database) -> None:
    model = db.model(callback_data.model_id)
    if not model:
        await c.answer("Модель не найдена — база обновилась.", show_alert=True)
        return
    lines = [
        f"{g.owner_name or '-'} - {g.url}"
        for g in db.gifts_by_model(model.id)
    ]
    name = f"{model.slug}_{model.name}".replace(" ", "_").replace("/", "_")
    await c.message.answer_document(
        BufferedInputFile("\n".join(lines).encode("utf-8"), filename=f"{name}.txt"),
        caption=f"{esc(collection_name(model.slug))} — {esc(model.name)}: {len(lines)} NFT",
    )
    await c.answer()


@router.message()
async def fallback(m: Message, config: Config) -> None:
    await start(m, config)
