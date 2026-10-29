"""Общее для всех роутеров: callback-данные, фильтр админа, главное меню."""
import re

from aiogram.filters import Filter
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, TelegramObject

from gift_bot.config import Config


class Menu(CallbackData, prefix="menu"):
    action: str  # main | parse | admin


class Collections(CallbackData, prefix="cols"):
    page: int = 0


ALL = "*"  # slug «Вся база»


class GiftList(CallbackData, prefix="gl"):
    slug: str  # коллекция или ALL
    page: int = 0


class IsAdmin(Filter):
    async def __call__(self, event: TelegramObject, config: Config) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in config.admin_ids)


def esc(s: str | None) -> str:
    return (s or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def collection_name(slug: str) -> str:
    """PlushPepe → Plush Pepe, BDayCandle → B Day Candle, UFCStrike → UFC Strike."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", slug)


PRIMARY, SUCCESS, DANGER = "primary", "success", "danger"  # синяя, зелёная, красная кнопка
LINE = "━━━━━━━━━━━━━━━"


def btn(text: str, cb: CallbackData | str, style: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, callback_data=cb if isinstance(cb, str) else cb.pack(), style=style
    )


def main_menu(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [[btn("🔍 Парсинг", Menu(action="parse"), PRIMARY)]]
    if is_admin:
        rows.append([btn("⚙️ Админ-панель", Menu(action="admin"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pager(make: callable, page: int, pages: int) -> list[InlineKeyboardButton]:
    """Ряд «◀️ 2/5 ▶️»; make(page) возвращает CallbackData нужной страницы."""
    if pages <= 1:
        return []
    row = []
    if page > 0:
        row.append(btn("◀️", make(page - 1)))
    row.append(btn(f"{page + 1}/{pages}", "noop"))
    if page < pages - 1:
        row.append(btn("▶️", make(page + 1)))
    return row


def main_text(gifts: int, collections: int) -> str:
    return (
        "🎁 <b>N F T   G I F T   P A R S E R</b>\n"
        f"{LINE}\n"
        "<blockquote>Владельцы NFT-подарков Telegram — по коллекциям, в пару кликов.</blockquote>\n\n"
        f"💎 NFT в базе: <b>{gifts}</b>\n"
        f"🎀 Подарков: <b>{collections}</b>\n\n"
        "👇 <i>Жми «Парсинг», чтобы начать</i>"
    )
