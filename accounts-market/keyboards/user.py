"""Inline keyboards of the shop."""

from __future__ import annotations

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import (
    Adm,
    Bulk,
    Buy,
    BuyN,
    BuyNOk,
    BuyOk,
    Cat,
    Cheapest,
    Countries,
    CountryProds,
    CountrySearch,
    Qty,
    Nav,
    Noop,
    OrderView,
    Orders,
    Pay,
    Payments,
    Prod,
    RefHistory,
    Topup,
    Txs,
)
from catalog.service import ProductView
from database.models import Category, Order, Payment
from services.formatting import clip, money


def btn(text: str, cb=None, *, url: str | None = None, style: str | None = None, copy: str | None = None):
    if url:
        return InlineKeyboardButton(text=text, url=url, style=style)
    if copy is not None:
        return InlineKeyboardButton(text=text, copy_text=CopyTextButton(text=copy[:256]), style=style)
    return InlineKeyboardButton(text=text, callback_data=cb.pack(), style=style)


def rows(*lines: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[line for line in lines if line])


HOME = btn("🏠 Главное меню", Nav(to="home"))


def main_menu(is_admin: bool, news_url: str | None = None) -> InlineKeyboardMarkup:
    lines = [
        [btn("🛍 Каталог", Nav(to="catalog"), style="primary"), btn("🔥 Популярное", Nav(to="popular"))],
        [btn("👤 Личный кабинет", Nav(to="profile")), btn("💎 Пополнить баланс", Nav(to="topup"))],
        [btn("📦 Мои покупки", Orders(page=0)), btn("🎁 Реферальная программа", Nav(to="ref"))],
        [btn("🆘 Поддержка", Nav(to="support")), btn("📜 Правила магазина", Nav(to="rules"))],
    ]
    if news_url:
        lines.append([btn("📣 Канал новостей", url=news_url)])
    if is_admin:
        lines.append([btn("🛠 Админ-панель", Adm(s="home"))])
    return rows(*lines)


def categories(items: list[tuple[Category, int]]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    buttons = [
        btn(f"{c.emoji} {c.title}" + ("" if count else " · нет"), Cat(id=c.id), style="success" if count else None)
        for c, count in items
    ]
    for i in range(0, len(buttons), 2):
        b.row(*buttons[i : i + 2])
    b.row(btn("🔥 Популярное", Nav(to="popular")))
    b.row(btn("◀️ Назад", Nav(to="home"), style="danger"))
    return b.as_markup()


def country_grid(category_id: int, offers, page: int, pages: int, cheapest_price: int | None) -> InlineKeyboardMarkup:
    from catalog.countries import label

    b = InlineKeyboardBuilder()
    if cheapest_price is not None:
        b.row(btn(f"💸 Самый дешёвый · {money(cheapest_price)}", Cheapest(id=category_id), style="success"))
    b.row(
        btn("🔍 Поиск страны", CountrySearch(id=category_id), style="primary"),
        btn("📦 Массовая покупка", Bulk(id=category_id), style="primary"),
    )
    cells = [
        btn(f"{label(o.code)} · {money(o.min_price)}", CountryProds(id=category_id, cc=o.code)) for o in offers
    ]
    for i in range(0, len(cells), 2):
        b.row(*cells[i : i + 2])
    nav = pager(lambda n: Countries(id=category_id, page=n), page, pages)
    if nav:
        b.row(*nav)
    b.row(btn("◀️ Назад", Nav(to="catalog"), style="danger"))
    return b.as_markup()


def country_results(category_id: int, codes: list[str]) -> InlineKeyboardMarkup:
    from catalog.countries import label

    b = InlineKeyboardBuilder()
    cells = [btn(label(c), CountryProds(id=category_id, cc=c)) for c in codes[:20]]
    for i in range(0, len(cells), 2):
        b.row(*cells[i : i + 2])
    b.row(btn("🔍 Искать ещё", CountrySearch(id=category_id)), btn("◀️ К странам", Countries(id=category_id), style="danger"))
    return b.as_markup()


def country_page(category_id: int, cc: str, views: list[ProductView], page: int, pages: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for v in views:
        p = v.product
        b.row(
            btn(f"ℹ️ {clip(p.title, 26)}", Prod(id=p.id, src="k", page=page)),
            btn(f"🛒 {money(p.price)}", Buy(id=p.id, price=p.price, src="k", page=page)),
        )
    nav = pager(lambda n: CountryProds(id=category_id, cc=cc, page=n), page, pages)
    if nav:
        b.row(*nav)
    b.row(btn("◀️ К странам", Countries(id=category_id), style="danger"), HOME)
    return b.as_markup()


def bulk_list(category_id: int, views: list[ProductView], page: int, pages: int) -> InlineKeyboardMarkup:
    from catalog.countries import label

    b = InlineKeyboardBuilder()
    for v in views:
        p = v.product
        name = label(p.country) if p.country else clip(p.title, 24)
        b.row(btn(f"{name} · {money(p.price)} · {v.stock} шт.", Qty(id=p.id, price=p.price)))
    nav = pager(lambda n: Bulk(id=category_id, page=n), page, pages)
    if nav:
        b.row(*nav)
    b.row(btn("◀️ Назад", Cat(id=category_id), style="danger"), HOME)
    return b.as_markup()


QTY_PRESETS = (2, 3, 5, 10, 25, 50)


def quantity(product_id: int, price: int, stock: int, limit: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    allowed = [q for q in QTY_PRESETS if q <= min(stock, limit)]
    cells = [btn(f"{q} шт. · {money(price * q)}", BuyN(id=product_id, price=price, qty=q)) for q in allowed]
    for i in range(0, len(cells), 2):
        b.row(*cells[i : i + 2])
    b.row(btn("✍️ Своё количество", BuyN(id=product_id, price=price, qty=0)))
    b.row(btn("◀️ Вернуться к товару", Prod(id=product_id), style="danger"))
    return b.as_markup()


def confirm_bulk(product_id: int, price: int, qty: int, nonce: str) -> InlineKeyboardMarkup:
    return rows(
        [btn(f"✅ Оплатить {qty} шт. · {money(price * qty)}", BuyNOk(id=product_id, price=price, qty=qty, nonce=nonce), style="success")],
        [btn("◀️ Изменить количество", Qty(id=product_id, price=price))],
    )


def bulk_done(first_order_id: int) -> InlineKeyboardMarkup:
    return rows(
        [btn("📦 Мои покупки", Orders(page=0), style="primary")],
        [btn("🛍 Продолжить покупки", Nav(to="catalog")), HOME],
    )


def pager(make, page: int, pages: int) -> list[InlineKeyboardButton]:
    if pages <= 1:
        return []
    line = []
    line.append(btn("⬅️", make(page - 1)) if page > 0 else btn("·", Noop()))
    line.append(btn(f"{page + 1} / {pages}", Noop()))
    line.append(btn("➡️ Далее", make(page + 1)) if page + 1 < pages else btn("·", Noop()))
    return line


def category_page(category_id: int, views: list[ProductView], page: int, pages: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for v in views:
        p = v.product
        info = btn(f"ℹ️ {clip(p.title, 26)}", Prod(id=p.id, src="c", page=page))
        if v.stock > 0:
            b.row(info, btn(f"🛒 {money(p.price)}", Buy(id=p.id, price=p.price, src="c", page=page)))
        else:
            b.row(info, btn("⛔ Нет в наличии", Prod(id=p.id, src="c", page=page)))
    nav = pager(lambda n: Cat(id=category_id, page=n), page, pages)
    if nav:
        b.row(*nav)
    b.row(btn("◀️ Назад", Nav(to="catalog")), HOME)
    return b.as_markup()


def popular(views: list[ProductView]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for v in views:
        p = v.product
        b.row(
            btn(f"ℹ️ {clip(p.title, 26)}", Prod(id=p.id, src="p")),
            btn(f"🛒 {money(p.price)}", Buy(id=p.id, price=p.price, src="p")),
        )
    b.row(btn("🛍 Весь каталог", Nav(to="catalog")), HOME)
    return b.as_markup()


def back_to_list(product, src: str, page: int) -> InlineKeyboardButton:
    if src == "p":
        return btn("◀️ К популярному", Nav(to="popular"))
    if src == "k" and product.country:
        return btn("◀️ К товарам страны", CountryProds(id=product.category_id, cc=product.country, page=page))
    if product.country:
        return btn("◀️ К выбору страны", Countries(id=product.category_id))
    return btn("◀️ Вернуться в каталог", Cat(id=product.category_id, page=page))


def product_card(view: ProductView, src: str, page: int, buyable: bool) -> InlineKeyboardMarkup:
    p = view.product
    lines = []
    if buyable:
        lines.append([btn(f"🛒 Купить за {money(p.price)}", Buy(id=p.id, price=p.price, src=src, page=page), style="primary")])
        if view.stock > 1:
            lines.append([btn("📦 Купить несколько", Qty(id=p.id, price=p.price))])
    lines.append([back_to_list(p, src, page)])
    lines.append([HOME])
    return rows(*lines)


def confirm_purchase(product_id: int, price: int, nonce: str, src: str, page: int) -> InlineKeyboardMarkup:
    return rows(
        [btn(f"✅ Подтвердить · {money(price)}", BuyOk(id=product_id, price=price, nonce=nonce), style="success")],
        [btn("◀️ Вернуться к товару", Prod(id=product_id, src=src, page=page))],
    )


def insufficient(product_id: int, src: str, page: int) -> InlineKeyboardMarkup:
    return rows(
        [btn("💎 Пополнить баланс", Nav(to="topup"), style="primary")],
        [btn("◀️ Вернуться к товару", Prod(id=product_id, src=src, page=page))],
    )


def back_to_product(product_id: int, src: str = "c", page: int = 0) -> InlineKeyboardMarkup:
    return rows([btn("◀️ Вернуться к товару", Prod(id=product_id, src=src, page=page))], [HOME])


def purchase_done(order_id: int) -> InlineKeyboardMarkup:
    return rows(
        [btn("📦 Открыть заказ", OrderView(id=order_id), style="primary")],
        [btn("🛍 Продолжить покупки", Nav(to="catalog")), HOME],
    )


def profile() -> InlineKeyboardMarkup:
    return rows(
        [btn("💎 Пополнить баланс", Nav(to="topup"), style="primary")],
        [btn("📦 История заказов", Orders(page=0)), btn("🎁 Мои рефералы", Nav(to="ref"))],
        [btn("💳 История операций", Txs(page=0)), btn("🧾 Пополнения", Payments(page=0))],
        [btn("◀️ Главное меню", Nav(to="home"))],
    )


def orders_list(orders: list[Order], page: int, pages: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for o in orders:
        mark = "✅" if o.status == "completed" else "↩️"
        b.row(btn(f"{mark} {o.number} · {clip(o.product_title, 22)}", OrderView(id=o.id, page=page)))
    nav = pager(lambda n: Orders(page=n), page, pages)
    if nav:
        b.row(*nav)
    b.row(btn("👤 Кабинет", Nav(to="profile")), HOME)
    return b.as_markup()


def order_view(order: Order, page: int, content: str | None) -> InlineKeyboardMarkup:
    lines = []
    if content:
        lines.append([btn("📋 Скопировать данные", copy=content)])
    lines.append([btn("◀️ К списку заказов", Orders(page=page)), HOME])
    return rows(*lines)


def paged(make, page: int, pages: int, back) -> InlineKeyboardMarkup:
    return rows(pager(make, page, pages), [back, HOME])


def topup(presets: list[int]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(*[btn(f"{p:,} ₽".replace(",", " "), Topup(amount=p)) for p in presets[:3]])
    if len(presets) > 3:
        b.row(*[btn(f"{p:,} ₽".replace(",", " "), Topup(amount=p)) for p in presets[3:6]])
    b.row(btn("✍️ Другая сумма", Topup(amount=0)))
    b.row(btn("🧾 История пополнений", Payments(page=0)))
    b.row(btn("👤 Кабинет", Nav(to="profile")), HOME)
    return b.as_markup()


def cancel_input(back) -> InlineKeyboardMarkup:
    return rows([btn("✖️ Отмена", back)])


def payment(p: Payment, demo: bool) -> InlineKeyboardMarkup:
    lines = []
    if p.status == "pending":
        if p.pay_url:
            lines.append([btn(f"💳 Оплатить {money(p.amount)}", url=p.pay_url, style="primary")])
        if demo:
            lines.append([btn("🧪 DEMO: провести оплату", Pay(action="demo", id=p.id), style="success")])
        lines.append([btn("🔄 Проверить оплату", Pay(action="check", id=p.id))])
    lines.append([btn("◀️ Пополнение", Nav(to="topup")), HOME])
    return rows(*lines)


def payments_list(items: list[Payment], page: int, pages: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in items:
        if p.status == "pending":
            b.row(btn(f"⏳ {money(p.amount)} · открыть счёт", Pay(action="show", id=p.id)))
    nav = pager(lambda n: Payments(page=n), page, pages)
    if nav:
        b.row(*nav)
    b.row(btn("💎 Пополнить", Nav(to="topup")), HOME)
    return b.as_markup()


def referral(share_url: str, link: str) -> InlineKeyboardMarkup:
    return rows(
        [btn("📤 Поделиться ссылкой", url=share_url, style="primary")],
        [btn("📋 Скопировать ссылку", copy=link)],
        [btn("🧾 История начислений", RefHistory(page=0))],
        [btn("👤 Кабинет", Nav(to="profile")), HOME],
    )


def support(support_url: str | None, news_url: str | None) -> InlineKeyboardMarkup:
    lines = []
    if support_url:
        lines.append([btn("💬 Написать в поддержку", url=support_url, style="primary")])
    if news_url:
        lines.append([btn("📣 Канал новостей", url=news_url)])
    lines.append([btn("📜 Правила магазина", Nav(to="rules")), HOME])
    return rows(*lines)


def only_home() -> InlineKeyboardMarkup:
    return rows([HOME])


def rules(support_url: str | None) -> InlineKeyboardMarkup:
    return rows([btn("💬 Поддержка", url=support_url)] if support_url else [], [btn("🛍 Каталог", Nav(to="catalog")), HOME])
