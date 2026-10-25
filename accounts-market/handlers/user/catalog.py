"""Catalog: categories, paginated product lists, popular items and product cards."""

from __future__ import annotations

import math

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy.ext.asyncio import AsyncSession

from bot import media
from bot.callbacks import Cat, Nav, Prod
from bot.ui import CAPTION_LIMIT, Screen, show
from catalog import service as catalog
from catalog.countries import name as country_name
from catalog.service import PAGE_SIZE, ProductView
from database.models import Category
from keyboards import user as kb
from services.formatting import clip, esc, money
from services.shop_settings import ShopSettings

router = Router(name="catalog")


def stock_label(stock: int) -> str:
    return f"в наличии · {stock} шт." if stock > 0 else "нет в наличии"


def specs_line(specs: str, limit: int = 2) -> str:
    parts = [f"{n}: {v}" if n else v for n, v in catalog.parse_specs(specs)[:limit]]
    return " · ".join(parts)


def product_entry(index: int, view: ProductView, desc_limit: int) -> str:
    p = view.product
    lines = [f"<b>{index}. {esc(p.title)}</b>"]
    specs = specs_line(p.specs)
    if specs:
        lines.append(f"⚙️ {esc(clip(specs, 70))}")
    meta = []
    if p.country:
        from catalog.countries import label

        meta.append(label(p.country))
    elif p.region:
        meta.append(f"🌍 {esc(p.region)}")
    meta.append(f"📦 {stock_label(view.stock)}")
    meta.append(f"💰 <b>{money(p.price)}</b>")
    lines.append(" · ".join(meta))
    if p.short_description and desc_limit:
        lines.append(f"<i>{esc(clip(p.short_description, desc_limit))}</i>")
    return "\n".join(lines)


def category_text(category: Category, views: list[ProductView], page: int, pages: int, total: int) -> str:
    head = f"{category.emoji} <b>{esc(category.title)}</b>"
    if category.description:
        head += f"\n{esc(clip(category.description, 140))}"
    if not views:
        return head + "\n\nВ этой категории пока нет товаров. Загляните позже 🙌"
    footer = f"\n\nСтраница {page + 1} из {pages} · позиций: {total}" if pages > 1 else ""
    # Shrink descriptions until the caption fits Telegram's limit.
    for desc_limit in (90, 60, 30, 0):
        body = "\n\n".join(product_entry(i, v, desc_limit) for i, v in enumerate(views, start=page * PAGE_SIZE + 1))
        text = f"{head}\n\n{body}{footer}"
        if len(text) <= CAPTION_LIMIT:
            return text
    return text


@router.callback_query(Nav.filter(F.to == "catalog"))
async def categories(callback: CallbackQuery, session: AsyncSession, shop: ShopSettings) -> None:
    items = await catalog.active_categories(session)
    if items:
        legend = "\n".join(
            f"{esc(c.emoji)} <b>{esc(c.title)}</b>" + (f" — {esc(clip(c.description, 90))}" if c.description else "")
            for c, _ in items
        )
        text = f"🛍 <b>Каталог</b>\n\n<blockquote expandable>{legend}</blockquote>\n\nВыберите вид:"
        if len(text) > CAPTION_LIMIT:
            text = "🛍 <b>Каталог</b>\n\nВыберите вид:"
    else:
        text = "🛍 <b>Каталог</b>\n\nКаталог пока пуст. Мы скоро добавим товары."
    await show(callback, Screen(text, kb.categories(items), await media.banner("catalog", shop.shop_name)))


@router.callback_query(Cat.filter())
async def category_page(
    callback: CallbackQuery,
    callback_data: Cat,
    session: AsyncSession,
    shop: ShopSettings,
    callback_answer: CallbackAnswer,
) -> None:
    category = await session.get(Category, callback_data.id)
    if category is None or not category.is_active:
        callback_answer.text, callback_answer.show_alert = "Категория больше недоступна", True
        await categories(callback, session, shop)
        return
    if await catalog.has_countries(session, category.id):
        from handlers.user.countries import grid_screen

        await show(callback, await grid_screen(session, category, 0, shop))
        return
    page = max(callback_data.page, 0)
    views, total = await catalog.category_products(session, category.id, page)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    if not views and page > 0:  # the page vanished (items archived): go to the last one
        page = pages - 1
        views, total = await catalog.category_products(session, category.id, page)
    text = category_text(category, views, page, pages, total)
    await show(
        callback, Screen(text, kb.category_page(category.id, views, page, pages), await media.banner("catalog", shop.shop_name))
    )


@router.callback_query(Nav.filter(F.to == "popular"))
async def popular(callback: CallbackQuery, session: AsyncSession, shop: ShopSettings) -> None:
    views = await catalog.popular_products(session)
    if views:
        body = "\n\n".join(product_entry(i, v, 60) for i, v in enumerate(views, start=1))
        text = f"🔥 <b>Популярное</b>\n\nТо, что выбирают чаще всего:\n\n{body}"
        if len(text) > CAPTION_LIMIT:
            body = "\n\n".join(product_entry(i, v, 0) for i, v in enumerate(views, start=1))
            text = f"🔥 <b>Популярное</b>\n\n{body}"
    else:
        text = "🔥 <b>Популярное</b>\n\nПока здесь пусто: товары появятся после первых продаж."
    await show(callback, Screen(text, kb.popular(views), await media.banner("popular", shop.shop_name)))


async def product_screen(view: ProductView, shop: ShopSettings, src: str, page: int) -> Screen:
    p = view.product
    buyable = catalog.is_buyable(view)
    lines = [f"💎 <b>{esc(p.title.upper())}</b>"]
    if p.short_description:
        lines.append(f"<i>{esc(p.short_description)}</i>")
    lines.append("")
    if p.is_demo:
        lines.append("🧪 <b>Демо-позиция</b> для проверки магазина, не реальный товар")
    lines.append(f"📦 Категория: {esc(p.category.title)}")
    if p.country:
        from catalog.countries import label

        lines.append(f"🌍 Страна: {label(p.country)}")
    if p.region:
        lines.append(f"🌍 Регион: {esc(p.region)}")
    if p.is_archived or not p.category.is_active:
        status = "снят с продажи"
    else:
        status = stock_label(view.stock)
    lines.append(f"📊 Статус: {status}")
    lines.append(f"💰 Стоимость: <b>{money(p.price)}</b>")
    specs = catalog.parse_specs(p.specs)
    if specs:
        lines += ["", "📋 <b>Характеристики</b>"]
        lines += [f"• {esc(n)}: {esc(v)}" if n else f"• {esc(v)}" for n, v in specs[:10]]
    head = "\n".join(lines)
    tail = "\n\n🔒 Данные товара выдаются только после оплаты и видны только покупателю."
    text = head + tail
    if p.description:
        room = CAPTION_LIMIT - len(text) - 4
        if room > 40:
            text = f"{head}\n\n{esc(clip(p.description, room))}{tail}"

    if p.photo_file_id:
        photo = (f"photo:{p.id}", p.photo_file_id)
    else:
        key = f"card:{p.id}:{p.updated_at.timestamp()}:{view.stock}:{shop.shop_name}"
        photo = await media.product_card(
            key,
            shop_name=shop.shop_name,
            title=p.title,
            category=p.category.title,
            region=p.region or (country_name(p.country) if p.country else None),
            price=money(p.price),
            stock=view.stock if buyable else 0,
            demo=p.is_demo,
        )
    return Screen(text, kb.product_card(view, src, page, buyable), photo)


@router.callback_query(Prod.filter())
async def product(
    callback: CallbackQuery,
    callback_data: Prod,
    session: AsyncSession,
    shop: ShopSettings,
    callback_answer: CallbackAnswer,
) -> None:
    view = await catalog.get_product(session, callback_data.id)
    if view is None:
        callback_answer.text, callback_answer.show_alert = "Товар больше недоступен", True
        await categories(callback, session, shop)
        return
    await show(callback, await product_screen(view, shop, callback_data.src, callback_data.page))
