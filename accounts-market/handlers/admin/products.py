"""Admin: products, stock, photos, CSV import."""

from __future__ import annotations

import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.states import CsvImport, ProductEdit, ProductForm
from bot.callbacks import Adm
from bot.ui import Screen, show
from catalog import countries, csv_import, manage
from catalog.service import parse_specs
from database.models import Category, ItemStatus, Product, ProductItem
from keyboards import admin as akb
from keyboards.user import btn, rows
from services.audit import log_action
from services.formatting import clip, esc, money, parse_rubles

router = Router(name="admin_products")
PAGE = 8
MAX_CSV = 2 * 1024 * 1024

FIELDS = {
    "title": ("Название", 128, False),
    "price": ("Цена", 0, False),
    "short_description": ("Краткое описание", 256, True),
    "description": ("Описание", 3000, True),
    "region": ("Регион", 64, True),
    "country": ("Страна", 64, True),
    "specs": ("Характеристики", 1500, True),
}


async def products_screen(session: AsyncSession, page: int, archived: bool) -> Screen:
    stock = (
        select(ProductItem.product_id, func.count().label("n"))
        .where(ProductItem.status == ItemStatus.AVAILABLE)
        .group_by(ProductItem.product_id)
        .subquery()
    )
    cond = Product.is_archived.is_(archived)
    total = await session.scalar(select(func.count(Product.id)).where(cond)) or 0
    pages = max(1, math.ceil(total / PAGE))
    page = min(max(page, 0), pages - 1)
    rows_ = (
        await session.execute(
            select(Product, func.coalesce(stock.c.n, 0))
            .outerjoin(stock, stock.c.product_id == Product.id)
            .where(cond)
            .order_by(Product.category_id, Product.id)
            .limit(PAGE)
            .offset(page * PAGE)
        )
    ).all()
    items = [
        (f"{'🟢' if n else '⚪'} {clip(p.title, 30)} · {money(p.price)} · {n} шт.", Adm(s="prod", id=p.id))
        for p, n in rows_
    ]
    v = "a" if archived else ""
    title = "🗄 <b>Архив товаров</b>" if archived else "📦 <b>Товары</b>"
    text = f"{title}\n\nВсего: {total}. 🟢 в наличии · ⚪ нет единиц.\nНажмите на товар, чтобы изменить его."
    extra = [
        [btn("➕ Добавить товар", Adm(s="pnew"), style="primary"), btn("📥 Импорт CSV", Adm(s="csv"))],
        [btn("📦 Активные" if archived else "🗄 Архив", Adm(s="prods", v="" if archived else "a"))],
    ]
    return Screen(text, akb.listing(items, page, pages, lambda n: Adm(s="prods", p=n, v=v), extra))


@router.callback_query(Adm.filter(F.s == "prods"))
async def products(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await show(callback, await products_screen(session, callback_data.p, callback_data.v == "a"))


async def product_screen(session: AsyncSession, product: Product) -> Screen:
    counts = await manage.stock_breakdown(session, product.id)
    specs = "\n".join(f"• {esc(n)}: {esc(v)}" if n else f"• {esc(v)}" for n, v in parse_specs(product.specs)) or "—"
    status = "🗄 в архиве" if product.is_archived else "🟢 в продаже"
    text = (
        f"📦 <b>{esc(product.title)}</b> · #{product.id}\n\n"
        f"Статус: {status}{' · 🔥 популярное' if product.is_featured else ''}{' · 🧪 демо' if product.is_demo else ''}\n"
        f"Категория: {esc(product.category.emoji)} {esc(product.category.title)}\n"
        f"Цена: <b>{money(product.price)}</b>\n"
        f"Страна: {countries.label(product.country) if product.country else '—'}\n"
        f"Регион: {esc(product.region or '—')}\n"
        f"Фото: {'загружено' if product.photo_file_id else 'генерируется автоматически'}\n\n"
        f"Кратко: {esc(product.short_description or '—')}\n\n"
        f"Описание: {esc(clip(product.description, 600) or '—')}\n\n"
        f"Характеристики:\n{specs}\n\n"
        f"Наличие: доступно {counts[ItemStatus.AVAILABLE]} · продано {counts[ItemStatus.SOLD]} · "
        f"отозвано {counts[ItemStatus.REVOKED]} · снято {counts[ItemStatus.WITHDRAWN]}"
    )
    kb = akb.product(
        product.id, product.is_archived, product.is_featured, counts[ItemStatus.AVAILABLE], bool(product.photo_file_id)
    )
    return Screen(text, kb)


async def _product(session: AsyncSession, pid: int, callback_answer: CallbackAnswer | None = None) -> Product | None:
    product = await session.get(Product, pid, populate_existing=True)
    if product is None and callback_answer is not None:
        callback_answer.text, callback_answer.show_alert = "Товар не найден", True
    return product


@router.callback_query(Adm.filter(F.s == "prod"))
async def product_card(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext, callback_answer: CallbackAnswer
) -> None:
    await state.clear()
    product = await _product(session, callback_data.id, callback_answer)
    if product:
        await show(callback, await product_screen(session, product))


# ── create ───────────────────────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.s == "pnew"))
async def new_product(callback: CallbackQuery, session: AsyncSession) -> None:
    cats = (await session.execute(select(Category).order_by(Category.sort_order, Category.id))).scalars().all()
    if not cats:
        await show(
            callback,
            Screen("Сначала создайте хотя бы одну категорию.", rows([btn("🗂 Категории", Adm(s="cats"))], [akb.ADMIN_HOME])),
        )
        return
    items = [(f"{c.emoji} {c.title}", Adm(s="pnewc", id=c.id)) for c in cats]
    await show(callback, Screen("➕ <b>Новый товар</b>\n\nШаг 1/4. Выберите категорию:", akb.listing(items, 0, 1, None, back_to=akb.back("prods"))))


@router.callback_query(Adm.filter(F.s == "pnewc"))
async def new_product_category(callback: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    await state.set_state(ProductForm.title)
    await state.update_data(category_id=callback_data.id)
    await show(callback, Screen("➕ <b>Новый товар</b>\n\nШаг 2/4. Отправьте название (до 128 символов):", akb.cancel("prods")))


@router.message(ProductForm.title, F.text)
async def new_product_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title or len(title) > 128:
        await message.answer("Название должно быть от 1 до 128 символов.", reply_markup=akb.cancel("prods"))
        return
    await state.update_data(title=title)
    await state.set_state(ProductForm.price)
    await message.answer("Шаг 3/4. Отправьте цену в рублях, например <code>1490</code>:", reply_markup=akb.cancel("prods"))


@router.message(ProductForm.price, F.text)
async def new_product_price(message: Message, state: FSMContext) -> None:
    price = parse_rubles(message.text)
    if price is None or price > 10_000_000_00:
        await message.answer("Некорректная цена. Пример: <code>1490</code> или <code>99.90</code>", reply_markup=akb.cancel("prods"))
        return
    await state.update_data(price=price)
    await state.set_state(ProductForm.short)
    await message.answer(
        "Шаг 4/4. Отправьте краткое описание (до 256 символов) или <code>-</code>, чтобы пропустить:",
        reply_markup=akb.cancel("prods"),
    )


@router.message(ProductForm.short, F.text)
async def new_product_short(message: Message, state: FSMContext, session: AsyncSession) -> None:
    short = "" if message.text.strip() == "-" else message.text.strip()
    if len(short) > 256:
        await message.answer("До 256 символов.", reply_markup=akb.cancel("prods"))
        return
    data = await state.get_data()
    await state.clear()
    if await session.get(Category, data["category_id"]) is None:
        await message.answer("Категория удалена, начните заново.", reply_markup=rows([akb.back("prods")]))
        return
    product = await manage.create_product(session, data["category_id"], data["title"], data["price"], short)
    await log_action(session, message.from_user.id, "product_create", f"product:{product.id}", product.title)
    await session.commit()
    product = await _product(session, product.id)
    await message.answer("✅ Товар создан. Добавьте единицы в «Наличие», чтобы он появился в продаже.")
    await show(message, await product_screen(session, product))


# ── edit fields ──────────────────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.s == "pe"))
async def edit_field(callback: CallbackQuery, callback_data: Adm, state: FSMContext, session: AsyncSession, callback_answer: CallbackAnswer) -> None:
    if callback_data.v not in FIELDS:
        callback_answer.text = "Неизвестное поле"
        return
    product = await _product(session, callback_data.id, callback_answer)
    if product is None:
        return
    name, limit, optional = FIELDS[callback_data.v]
    current = getattr(product, callback_data.v)
    if callback_data.v == "price":
        current = money(product.price)
    hint = "Отправьте новую цену в рублях." if callback_data.v == "price" else f"Отправьте новое значение (до {limit} символов)."
    if callback_data.v == "country":
        hint = "Отправьте код страны ISO (<code>DE</code>) или название (<code>Германия</code>). Товары со страной показываются через выбор страны."
    if callback_data.v == "specs":
        hint += "\nКаждая характеристика с новой строки в формате <code>Название: значение</code>."
    if optional:
        hint += "\nОтправьте <code>-</code>, чтобы очистить."
    await state.set_state(ProductEdit.value)
    await state.update_data(pid=product.id, field=callback_data.v)
    text = f"✏️ <b>{name}</b> · {esc(product.title)}\n\nСейчас:\n<blockquote>{esc(clip(str(current or '—'), 800))}</blockquote>\n\n{hint}"
    await show(callback, Screen(text, akb.cancel("prod", id=product.id)))


@router.message(ProductEdit.value, F.text)
async def edit_field_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    pid, field = data["pid"], data["field"]
    name, limit, optional = FIELDS[field]
    raw = message.text.strip()
    product = await _product(session, pid)
    if product is None:
        await state.clear()
        await message.answer("Товар не найден.")
        return
    if field == "price":
        value = parse_rubles(raw)
        if value is None:
            await message.answer("Некорректная цена, пример: <code>1490</code>", reply_markup=akb.cancel("prod", id=pid))
            return
    elif field == "country" and raw != "-":
        value = countries.parse(raw)
        if value is None:
            await message.answer(
                "Не знаю такую страну. Укажите код ISO (<code>DE</code>) или название (<code>Германия</code>).",
                reply_markup=akb.cancel("prod", id=pid),
            )
            return
    elif raw == "-" and optional:
        value = None if field in ("region", "country") else ""
    else:
        if not raw or len(raw) > limit:
            await message.answer(f"Длина: от 1 до {limit} символов.", reply_markup=akb.cancel("prod", id=pid))
            return
        value = raw
    old = getattr(product, field)
    setattr(product, field, value)
    await log_action(
        session, message.from_user.id, f"product_{field}", f"product:{pid}", f"{clip(str(old), 200)} -> {clip(str(value), 200)}"
    )
    await session.commit()
    await state.clear()
    await message.answer(f"✅ {name}: сохранено")
    await show(message, await product_screen(session, await _product(session, pid)))


@router.callback_query(Adm.filter(F.s == "pcat"))
async def choose_category(callback: CallbackQuery, callback_data: Adm, session: AsyncSession) -> None:
    cats = (await session.execute(select(Category).order_by(Category.sort_order, Category.id))).scalars().all()
    items = [(f"{c.emoji} {c.title}", Adm(s="psetcat", id=callback_data.id, v=str(c.id))) for c in cats]
    await show(callback, Screen("🗂 Выберите новую категорию:", akb.listing(items, 0, 1, None, back_to=akb.back("prod", id=callback_data.id))))


@router.callback_query(Adm.filter(F.s == "psetcat"))
async def set_category(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, callback_answer: CallbackAnswer) -> None:
    product = await _product(session, callback_data.id, callback_answer)
    category = await session.get(Category, int(callback_data.v or 0))
    if product is None or category is None:
        callback_answer.text, callback_answer.show_alert = "Не найдено", True
        return
    product.category_id = category.id
    await log_action(session, callback.from_user.id, "product_category", f"product:{product.id}", category.title)
    await session.commit()
    callback_answer.text = "Категория изменена"
    await show(callback, await product_screen(session, await _product(session, product.id)))


@router.callback_query(Adm.filter(F.s.in_({"parch", "pfeat"})))
async def toggle(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, callback_answer: CallbackAnswer) -> None:
    product = await _product(session, callback_data.id, callback_answer)
    if product is None:
        return
    if callback_data.s == "parch":
        product.is_archived = not product.is_archived
        callback_answer.text = "Товар в архиве" if product.is_archived else "Товар снова в продаже"
        action = "product_archive" if product.is_archived else "product_unarchive"
    else:
        product.is_featured = not product.is_featured
        callback_answer.text = "Добавлен в «Популярное»" if product.is_featured else "Убран из «Популярного»"
        action = "product_featured"
    await log_action(session, callback.from_user.id, action, f"product:{product.id}")
    await session.commit()
    await show(callback, await product_screen(session, await _product(session, product.id)))


# ── photo ────────────────────────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.s == "pphoto"))
async def photo_prompt(callback: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    await state.set_state(ProductEdit.photo)
    await state.update_data(pid=callback_data.id)
    text = "🖼 Отправьте фотографию товара (как фото, не файлом). Рекомендуемый формат 2:1, например 1280×640."
    await show(callback, Screen(text, akb.cancel("prod", id=callback_data.id)))


@router.message(ProductEdit.photo, F.photo)
async def photo_save(message: Message, state: FSMContext, session: AsyncSession) -> None:
    pid = (await state.get_data())["pid"]
    product = await _product(session, pid)
    await state.clear()
    if product is None:
        await message.answer("Товар не найден.")
        return
    product.photo_file_id = message.photo[-1].file_id
    await log_action(session, message.from_user.id, "product_photo", f"product:{pid}")
    await session.commit()
    await message.answer("✅ Фото сохранено")
    await show(message, await product_screen(session, await _product(session, pid)))


@router.message(ProductEdit.photo)
async def photo_wrong(message: Message, state: FSMContext) -> None:
    pid = (await state.get_data())["pid"]
    await message.answer("Нужна фотография. Отправьте изображение как фото.", reply_markup=akb.cancel("prod", id=pid))


@router.callback_query(Adm.filter(F.s == "pphotodel"))
async def photo_delete(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, callback_answer: CallbackAnswer) -> None:
    product = await _product(session, callback_data.id, callback_answer)
    if product is None:
        return
    product.photo_file_id = None
    await log_action(session, callback.from_user.id, "product_photo_delete", f"product:{product.id}")
    await session.commit()
    callback_answer.text = "Фото удалено, будет использоваться сгенерированная карточка"
    await show(callback, await product_screen(session, await _product(session, product.id)))


# ── stock ────────────────────────────────────────────────────────────────────


async def stock_screen(session: AsyncSession, product: Product) -> Screen:
    c = await manage.stock_breakdown(session, product.id)
    text = (
        f"📦 <b>Наличие</b> · {esc(product.title)}\n\n"
        f"🟢 Доступно к продаже: <b>{c[ItemStatus.AVAILABLE]}</b>\n"
        f"✅ Продано: {c[ItemStatus.SOLD]}\n"
        f"↩️ Отозвано после возврата: {c[ItemStatus.REVOKED]}\n"
        f"📤 Снято с продажи: {c[ItemStatus.WITHDRAWN]}\n\n"
        "Единица товара — это то, что получит покупатель после оплаты: ключ, данные "
        "передаваемого аккаунта, ссылка и т.п. Добавляйте только то, что разрешено продавать и передавать."
    )
    return Screen(text, akb.stock(product.id, c[ItemStatus.AVAILABLE]))


@router.callback_query(Adm.filter(F.s == "pstock"))
async def stock(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext, callback_answer: CallbackAnswer) -> None:
    await state.clear()
    product = await _product(session, callback_data.id, callback_answer)
    if product:
        await show(callback, await stock_screen(session, product))


@router.callback_query(Adm.filter(F.s == "padd"))
async def items_prompt(callback: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    await state.set_state(ProductEdit.items)
    await state.update_data(pid=callback_data.id)
    text = (
        "➕ <b>Добавление единиц</b>\n\n"
        "Отправьте сообщение, где <b>каждая строка — отдельная единица</b> товара, "
        "или .txt-файл в том же формате (UTF-8)."
    )
    await show(callback, Screen(text, akb.cancel("pstock", id=callback_data.id)))


@router.message(ProductEdit.items, F.text | F.document)
async def items_save(message: Message, state: FSMContext, session: AsyncSession) -> None:
    pid = (await state.get_data())["pid"]
    if message.document:
        if (message.document.file_size or 0) > MAX_CSV:
            await message.answer("Файл больше 2 МБ.", reply_markup=akb.cancel("pstock", id=pid))
            return
        buf = await message.bot.download(message.document)
        try:
            raw = buf.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            await message.answer("Файл должен быть в UTF-8.", reply_markup=akb.cancel("pstock", id=pid))
            return
    else:
        raw = message.text
    try:
        items = manage.split_items(raw)
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}", reply_markup=akb.cancel("pstock", id=pid))
        return
    if not items:
        await message.answer("Не найдено ни одной строки.", reply_markup=akb.cancel("pstock", id=pid))
        return
    product = await _product(session, pid)
    if product is None:
        await state.clear()
        await message.answer("Товар не найден.")
        return
    added = await manage.add_items(session, pid, items)
    await log_action(session, message.from_user.id, "stock_add", f"product:{pid}", f"{added} items")
    await session.commit()
    await state.clear()
    if not message.document:
        try:  # the message holds item contents: don't leave it in the admin chat
            await message.delete()
        except Exception:
            pass
    await message.answer(f"✅ Добавлено единиц: {added}")
    await show(message, await stock_screen(session, product))


@router.callback_query(Adm.filter(F.s == "pwd"))
async def withdraw_confirm(callback: CallbackQuery, callback_data: Adm) -> None:
    await show(
        callback,
        Screen(
            "📤 Снять все доступные единицы с продажи? Их нельзя будет вернуть, только добавить заново.",
            akb.confirm(Adm(s="pwdok", id=callback_data.id), Adm(s="pstock", id=callback_data.id), "📤 Снять"),
        ),
    )


@router.callback_query(Adm.filter(F.s == "pwdok"))
async def withdraw(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, callback_answer: CallbackAnswer) -> None:
    product = await _product(session, callback_data.id, callback_answer)
    if product is None:
        return
    n = await manage.withdraw_available(session, product.id)
    await log_action(session, callback.from_user.id, "stock_withdraw", f"product:{product.id}", f"{n} items")
    await session.commit()
    callback_answer.text = f"Снято с продажи: {n}"
    await show(callback, await stock_screen(session, product))


# ── CSV import ───────────────────────────────────────────────────────────────

CSV_HELP = (
    "📥 <b>Импорт товаров из CSV</b>\n\n"
    "Отправьте CSV-файл (UTF-8, разделитель <code>,</code> или <code>;</code>) с заголовком:\n"
    "<code>category,title,price,country,region,short_description,description,specs,items,featured</code>\n\n"
    "• обязательны: category, title, price (в рублях)\n"
    "• specs: характеристики через <code>|</code>, например <code>Стаж: 1 год|Почта: есть</code>\n"
    "• items: единицы товара через <code>|</code> или переносом строки внутри ячейки\n"
    "• featured: 1 — показать в «Популярном»\n"
    "• country: код страны ISO (DE, US, KZ) или название — товар попадёт в выбор страны\n\n"
    "Товар с тем же названием в той же категории обновляется, а единицы добавляются. "
    "Отсутствующие категории создаются."
)


@router.callback_query(Adm.filter(F.s == "csv"))
async def csv_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CsvImport.file)
    await show(callback, Screen(CSV_HELP, akb.cancel("prods")))


@router.message(CsvImport.file, F.document)
async def csv_file(message: Message, state: FSMContext, session: AsyncSession) -> None:
    doc = message.document
    if (doc.file_size or 0) > MAX_CSV:
        await message.answer("Файл больше 2 МБ, разделите его на части.", reply_markup=akb.cancel("prods"))
        return
    data = (await message.bot.download(doc)).read()
    try:
        report = await csv_import.import_csv(session, data)
    except ValueError as exc:
        await session.rollback()
        await message.answer(f"⚠️ {exc}", reply_markup=akb.cancel("prods"))
        return
    await log_action(
        session,
        message.from_user.id,
        "csv_import",
        doc.file_name or "",
        f"created={report.created} updated={report.updated} items={report.items} errors={len(report.errors)}",
    )
    await session.commit()
    await state.clear()
    errors = "\n".join(esc(e) for e in report.errors[:15])
    text = (
        "📥 <b>Импорт завершён</b>\n\n"
        f"Создано товаров: {report.created}\n"
        f"Обновлено: {report.updated}\n"
        f"Новых категорий: {report.categories}\n"
        f"Добавлено единиц: {report.items}\n"
        f"Ошибок: {len(report.errors)}" + (f"\n\n{errors}" if errors else "")
    )
    await message.answer(text, reply_markup=rows([akb.back("prods", "📦 К товарам")], [akb.ADMIN_HOME]))


@router.message(CsvImport.file)
async def csv_wrong(message: Message) -> None:
    await message.answer("Нужен CSV-файл документом.", reply_markup=akb.cancel("prods"))
