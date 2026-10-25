"""Inline keyboards of the admin panel."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import Adm, Nav
from keyboards.user import btn, pager, rows

ADMIN_HOME = btn("🛠 Админ-панель", Adm(s="home"))


def back(section: str, label: str = "◀️ Назад", **kw) -> InlineKeyboardButton:
    return btn(label, Adm(s=section, **kw))


def menu() -> InlineKeyboardMarkup:
    return rows(
        [btn("📊 Статистика", Adm(s="stats")), btn("📦 Товары", Adm(s="prods"))],
        [btn("🗂 Категории", Adm(s="cats")), btn("🛒 Заказы", Adm(s="ords"))],
        [btn("👥 Пользователи", Adm(s="users")), btn("💳 Платежи", Adm(s="pays"))],
        [btn("📢 Рассылки", Adm(s="bc")), btn("⚙️ Настройки", Adm(s="set"))],
        [btn("🏠 Выйти в магазин", Nav(to="home"))],
    )


def listing(
    items: list[tuple[str, Adm]],
    page: int,
    pages: int,
    page_cb,
    extra: list[list[InlineKeyboardButton]] | None = None,
    back_to: InlineKeyboardButton | None = None,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, cb in items:
        b.row(btn(label, cb))
    nav = pager(page_cb, page, pages)
    if nav:
        b.row(*nav)
    for line in extra or []:
        b.row(*line)
    b.row(back_to or ADMIN_HOME)
    return b.as_markup()


def cancel(section: str, **kw) -> InlineKeyboardMarkup:
    return rows([btn("✖️ Отмена", Adm(s=section, **kw))])


def confirm(yes: Adm, no: Adm, yes_label: str = "✅ Подтвердить") -> InlineKeyboardMarkup:
    return rows([btn(yes_label, yes, style="danger"), btn("✖️ Отмена", no)])


def product(pid: int, archived: bool, featured: bool, stock: int, has_photo: bool) -> InlineKeyboardMarkup:
    e = lambda field: Adm(s="pe", id=pid, v=field)  # noqa: E731
    lines = [
        [btn("✏️ Название", e("title")), btn("💰 Цена", e("price"))],
        [btn("🧾 Кратко", e("short_description")), btn("📝 Описание", e("description"))],
        [btn("🏳️ Страна", e("country")), btn("🌍 Регион", e("region"))],
        [btn("📋 Характеристики", e("specs"))],
        [btn("🗂 Категория", Adm(s="pcat", id=pid)), btn("🖼 Фото", Adm(s="pphoto", id=pid))],
        [btn(f"📦 Наличие: {stock} шт.", Adm(s="pstock", id=pid), style="primary")],
        [
            btn("🔥 Убрать из популярного" if featured else "🔥 В популярное", Adm(s="pfeat", id=pid)),
            btn("♻️ Вернуть в продажу" if archived else "🗄 В архив", Adm(s="parch", id=pid)),
        ],
        [back("prods", "◀️ К товарам")],
    ]
    if has_photo:
        lines[4].append(btn("🗑 Фото", Adm(s="pphotodel", id=pid)))
    return rows(*lines)


def stock(pid: int, available: int) -> InlineKeyboardMarkup:
    lines = [[btn("➕ Добавить единицы", Adm(s="padd", id=pid), style="primary")]]
    if available:
        lines.append([btn("📤 Снять доступные с продажи", Adm(s="pwd", id=pid), style="danger")])
    lines.append([back("prod", "◀️ К товару", id=pid)])
    return rows(*lines)
