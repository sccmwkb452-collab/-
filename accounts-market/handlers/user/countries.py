"""Country grid, country search, cheapest offer and bulk purchase."""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import media
from bot.callbacks import Bulk, BuyN, BuyNOk, Cheapest, Countries, CountryProds, CountrySearch, Qty
from bot.ui import Screen, show
from catalog import countries as cc
from catalog import service as catalog
from catalog.service import PAGE_SIZE
from database.models import Category, User
from handlers.user.catalog import categories, category_text, product_screen
from handlers.user.purchase import insufficient_screen
from keyboards import user as kb
from orders import service as orders
from services.errors import AccessRestricted, InsufficientFunds, OutOfStock, PriceChanged, ProductUnavailable, ShopError
from services.formatting import clip, esc, money, plural
from services.shop_settings import ShopSettings

router = Router(name="countries")

GRID_PAGE = 12
BULK_PAGE = 8
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


class CatalogInput(StatesGroup):
    country = State()
    quantity = State()


async def _category(session: AsyncSession, category_id: int, callback_answer: CallbackAnswer | None) -> Category | None:
    category = await session.get(Category, category_id)
    if category is None or not category.is_active:
        if callback_answer is not None:
            callback_answer.text, callback_answer.show_alert = "Категория больше недоступна", True
        return None
    return category


async def grid_screen(session: AsyncSession, category: Category, page: int, shop: ShopSettings) -> Screen:
    offers = await catalog.country_offers(session, category.id)
    pages = max(1, math.ceil(len(offers) / GRID_PAGE))
    page = min(max(page, 0), pages - 1)
    cheapest = await catalog.cheapest(session, category.id)
    head = f"{category.emoji} <b>{esc(category.title)}</b>"
    if category.description:
        head += f"\n<i>{esc(clip(category.description, 160))}</i>"
    if offers:
        units = sum(o.stock for o in offers)
        text = (
            f"{head}\n\n🌍 Стран: <b>{len(offers)}</b> · в наличии: <b>{units}</b> шт.\n"
            "Цена у страны — минимальная по её товарам.\n\nВыберите страну:"
        )
    else:
        text = f"{head}\n\nСейчас в этой категории нет товаров в наличии. Загляните позже 🙌"
    chunk = offers[page * GRID_PAGE : (page + 1) * GRID_PAGE]
    markup = kb.country_grid(category.id, chunk, page, pages, cheapest.product.price if cheapest else None)
    return Screen(text, markup, await media.banner("catalog", shop.shop_name))


@router.callback_query(Countries.filter())
async def grid(
    callback: CallbackQuery,
    callback_data: Countries,
    session: AsyncSession,
    state: FSMContext,
    shop: ShopSettings,
    callback_answer: CallbackAnswer,
) -> None:
    await state.clear()
    category = await _category(session, callback_data.id, callback_answer)
    if category is None:
        await categories(callback, session, shop)
        return
    await show(callback, await grid_screen(session, category, callback_data.page, shop))


async def country_screen(session: AsyncSession, category: Category, code: str, page: int, shop: ShopSettings) -> Screen:
    views, total = await catalog.category_products(session, category.id, page, country=code)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    text = category_text(category, views, page, pages, total)
    text = text.replace(f"{category.emoji} <b>{esc(category.title)}</b>", f"{cc.label(code)} · <b>{esc(category.title)}</b>", 1)
    return Screen(text, kb.country_page(category.id, code, views, page, pages), await media.banner("catalog", shop.shop_name))


@router.callback_query(CountryProds.filter())
async def country(
    callback: CallbackQuery,
    callback_data: CountryProds,
    session: AsyncSession,
    shop: ShopSettings,
    callback_answer: CallbackAnswer,
) -> None:
    category = await _category(session, callback_data.id, callback_answer)
    if category is None:
        await categories(callback, session, shop)
        return
    views, total = await catalog.category_products(session, category.id, 0, country=callback_data.cc)
    if total == 1 and callback_data.page == 0:  # one product: open its card right away
        await show(callback, await product_screen(views[0], shop, "c", 0))
        return
    await show(callback, await country_screen(session, category, callback_data.cc, callback_data.page, shop))


@router.callback_query(Cheapest.filter())
async def cheapest(
    callback: CallbackQuery,
    callback_data: Cheapest,
    session: AsyncSession,
    shop: ShopSettings,
    callback_answer: CallbackAnswer,
) -> None:
    view = await catalog.cheapest(session, callback_data.id)
    if view is None:
        callback_answer.text, callback_answer.show_alert = "Сейчас нет товаров в наличии", True
        return
    await show(callback, await product_screen(view, shop, "c", 0))


# ── search ───────────────────────────────────────────────────────────────────


@router.callback_query(CountrySearch.filter())
async def search_prompt(callback: CallbackQuery, callback_data: CountrySearch, state: FSMContext, shop: ShopSettings) -> None:
    await state.set_state(CatalogInput.country)
    await state.update_data(category_id=callback_data.id)
    text = "🔍 <b>Поиск страны</b>\n\nОтправьте название или код страны, например <code>Германия</code>, <code>USA</code> или <code>KZ</code>."
    await show(callback, Screen(text, kb.cancel_input(Countries(id=callback_data.id)), await media.banner("catalog", shop.shop_name)))


@router.message(CatalogInput.country, F.text)
async def search(message: Message, state: FSMContext, session: AsyncSession, shop: ShopSettings) -> None:
    category_id = (await state.get_data()).get("category_id", 0)
    category = await _category(session, category_id, None)
    if category is None:
        await state.clear()
        await message.answer("Категория больше недоступна.", reply_markup=kb.only_home())
        return
    offers = await catalog.country_offers(session, category.id)
    found = cc.search(message.text, [o.code for o in offers])
    if len(found) == 1:
        await state.clear()
        await show(message, await country_screen(session, category, found[0], 0, shop))
        return
    if not found:
        await message.answer(
            f"Ничего не нашлось по запросу «{esc(clip(message.text, 40))}» среди стран в наличии. Попробуйте ещё раз:",
            reply_markup=kb.cancel_input(Countries(id=category.id)),
        )
        return
    await state.clear()
    await message.answer(
        f"🔍 Нашлось {len(found)} {plural(len(found), 'страна', 'страны', 'стран')}:",
        reply_markup=kb.country_results(category.id, found),
    )


# ── bulk purchase ────────────────────────────────────────────────────────────


@router.callback_query(Bulk.filter())
async def bulk(
    callback: CallbackQuery,
    callback_data: Bulk,
    session: AsyncSession,
    shop: ShopSettings,
    callback_answer: CallbackAnswer,
) -> None:
    category = await _category(session, callback_data.id, callback_answer)
    if category is None:
        await categories(callback, session, shop)
        return
    views = [
        v
        for v in (await catalog.category_products(session, category.id, 0, page_size=500))[0]
        if catalog.is_buyable(v)
    ]
    pages = max(1, math.ceil(len(views) / BULK_PAGE))
    page = min(max(callback_data.page, 0), pages - 1)
    text = (
        f"📦 <b>Массовая покупка</b> · {esc(category.title)}\n\n"
        f"Выберите товар, затем количество — до {orders.MAX_BULK} шт. за раз. "
        "Все единицы оплачиваются одной операцией и приходят одним сообщением или файлом."
    )
    if not views:
        text += "\n\nСейчас нет товаров в наличии."
    chunk = views[page * BULK_PAGE : (page + 1) * BULK_PAGE]
    await show(callback, Screen(text, kb.bulk_list(category.id, chunk, page, pages), await media.banner("checkout", shop.shop_name)))


async def quantity_screen(view: catalog.ProductView, user: User, shop: ShopSettings) -> Screen:
    p = view.product
    affordable = user.balance // p.price
    text = (
        f"📦 <b>{esc(p.title)}</b>\n\n"
        f"💰 Цена за 1 шт.: <b>{money(p.price)}</b>\n"
        f"📊 В наличии: {view.stock} шт.\n"
        f"💳 Ваш баланс: {money(user.balance)} — хватает на {affordable} шт.\n\n"
        "Выберите количество:"
    )
    return Screen(text, kb.quantity(p.id, p.price, view.stock, orders.MAX_BULK), await media.banner("checkout", shop.shop_name))


@router.callback_query(Qty.filter())
async def quantity(
    callback: CallbackQuery,
    callback_data: Qty,
    session: AsyncSession,
    state: FSMContext,
    user: User,
    shop: ShopSettings,
    callback_answer: CallbackAnswer,
) -> None:
    await state.clear()
    view = await catalog.get_product(session, callback_data.id)
    if view is None or not catalog.is_buyable(view):
        callback_answer.text, callback_answer.show_alert = "Товара нет в наличии", True
        if view is not None:
            await show(callback, await product_screen(view, shop, "c", 0))
        return
    if view.product.price != callback_data.price:
        callback_answer.text, callback_answer.show_alert = f"Цена изменилась: теперь {money(view.product.price)}", True
    await session.refresh(user)
    await show(callback, await quantity_screen(view, user, shop))


async def _bulk_confirm(event, session: AsyncSession, user: User, shop: ShopSettings, product_id: int, qty: int) -> None:
    view = await catalog.get_product(session, product_id)
    if view is None or not catalog.is_buyable(view):
        await show(event, Screen("Товара больше нет в наличии.", kb.only_home()))
        return
    p = view.product
    if qty > view.stock:
        await show(event, Screen(f"⚠️ В наличии только {view.stock} шт.", kb.quantity(p.id, p.price, view.stock, orders.MAX_BULK)))
        return
    await session.refresh(user)
    total = p.price * qty
    if user.balance < total:
        await show(event, await insufficient_screen(shop, p.id, total, user.balance, "c", 0))
        return
    text = (
        "🛒 <b>Подтверждение массовой покупки</b>\n\n"
        f"Товар: <b>{esc(p.title)}</b>\n"
        + (f"Страна: {cc.label(p.country)}\n" if p.country else "")
        + f"Количество: <b>{qty} шт.</b> × {money(p.price)}\n\n"
        f"💰 К оплате: <b>{money(total)}</b>\n"
        f"💳 Баланс после покупки: {money(user.balance - total)}"
    )
    await show(event, Screen(text, kb.confirm_bulk(p.id, p.price, qty, orders.new_nonce()), await media.banner("checkout", shop.shop_name)))


@router.callback_query(BuyN.filter(F.qty == 0))
async def custom_quantity(callback: CallbackQuery, callback_data: BuyN, state: FSMContext, shop: ShopSettings) -> None:
    await state.set_state(CatalogInput.quantity)
    await state.update_data(product_id=callback_data.id, price=callback_data.price)
    text = f"✍️ Отправьте количество числом, от 1 до {orders.MAX_BULK}."
    await show(callback, Screen(text, kb.cancel_input(Qty(id=callback_data.id, price=callback_data.price)), await media.banner("checkout", shop.shop_name)))


@router.message(CatalogInput.quantity, F.text)
async def custom_quantity_value(message: Message, state: FSMContext, session: AsyncSession, user: User, shop: ShopSettings) -> None:
    data = await state.get_data()
    text = message.text.strip()
    if not text.isdigit() or not 1 <= int(text) <= orders.MAX_BULK:
        await message.answer(
            f"Укажите число от 1 до {orders.MAX_BULK}.",
            reply_markup=kb.cancel_input(Qty(id=data["product_id"], price=data["price"])),
        )
        return
    await state.clear()
    await _bulk_confirm(message, session, user, shop, data["product_id"], int(text))


@router.callback_query(BuyN.filter(F.qty > 0))
async def bulk_confirm(callback: CallbackQuery, callback_data: BuyN, session: AsyncSession, user: User, shop: ShopSettings) -> None:
    await _bulk_confirm(callback, session, user, shop, callback_data.id, callback_data.qty)


def _delivery_text(result: orders.BulkResult) -> str:
    first = result.orders[0]
    lines = [
        f"📦 <b>Массовая покупка · {len(result.items)} шт.</b>",
        f"Товар: {esc(first.product_title)}",
        f"Заказы: {result.orders[0].number} — {result.orders[-1].number}",
        f"Сумма: {money(result.total)}",
        "",
        "🔑 <b>Данные товаров</b>",
        "<pre>" + esc("\n".join(r.content for r in result.items)) + "</pre>",
        "",
        "Сохраните данные. Каждый заказ также доступен в «📦 Мои покупки».",
    ]
    return "\n".join(lines)


@router.callback_query(BuyNOk.filter())
async def bulk_pay(
    callback: CallbackQuery,
    callback_data: BuyNOk,
    session: AsyncSession,
    sm: async_sessionmaker[AsyncSession],
    user: User,
    shop: ShopSettings,
    callback_answer: CallbackAnswer,
) -> None:
    lock = _locks[user.id]
    if lock.locked():
        callback_answer.text = "⏳ Заказ уже обрабатывается…"
        return
    try:
        async with lock:
            try:
                result = await orders.purchase_many(
                    sm,
                    user_id=user.id,
                    product_id=callback_data.id,
                    expected_price=callback_data.price,
                    quantity=callback_data.qty,
                    nonce=callback_data.nonce,
                )
            except InsufficientFunds:
                await session.refresh(user)
                await show(
                    callback,
                    await insufficient_screen(shop, callback_data.id, callback_data.price * callback_data.qty, user.balance, "c", 0),
                )
                return
            except (OutOfStock, PriceChanged) as exc:
                callback_answer.text, callback_answer.show_alert = exc.message, True
                view = await catalog.get_product(session, callback_data.id)
                if view is not None:
                    await show(callback, await quantity_screen(view, user, shop))
                return
            except (ProductUnavailable, AccessRestricted, ShopError) as exc:
                callback_answer.text, callback_answer.show_alert = exc.message or "Покупка недоступна", True
                await categories(callback, session, shop)
                return
    finally:
        if not lock.locked():
            _locks.pop(user.id, None)

    if not result.created:
        callback_answer.text = "Этот заказ уже оформлен"
    await session.refresh(user)
    first, last = result.orders[0], result.orders[-1]
    text = (
        f"✅ <b>Оплачено {len(result.items)} шт.</b>\n\n"
        f"Товар: {esc(first.product_title)}\n"
        f"Заказы: {first.number} — {last.number}\n"
        f"Списано: <b>{money(result.total)}</b>\n"
        f"Баланс: {money(user.balance)}\n\n"
        "Данные отправлены отдельным сообщением ниже."
    )
    await show(callback, Screen(text, kb.bulk_done(first.id), await media.banner("success", shop.shop_name)))
    if not result.created:
        return
    delivery = _delivery_text(result)
    if len(delivery) <= 4000:
        await callback.bot.send_message(user.id, delivery)
    else:  # too long for one message: send a text file
        body = "\n".join(f"{r.order.number}\t{r.content}" for r in result.items).encode()
        await callback.bot.send_document(
            user.id,
            BufferedInputFile(body, filename=f"{first.number}-{last.number}.txt"),
            caption=f"📦 Массовая покупка · {len(result.items)} шт. · {esc(first.product_title)}\n"
            "Данные товаров — в файле. Каждый заказ также доступен в «📦 Мои покупки».",
        )
    for tx in result.referral_txs[:1]:
        try:
            amount = sum(t.amount for t in result.referral_txs)
            await callback.bot.send_message(
                tx.user_id, f"🎁 Начислен реферальный бонус: <b>+{money(amount)}</b>\nВаш приглашённый совершил покупку."
            )
        except TelegramAPIError:
            pass
