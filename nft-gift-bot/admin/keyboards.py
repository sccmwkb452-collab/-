"""Inline keyboards for the admin panel."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models.shop import ProductStatus, ShopOrder, ShopProduct


def main_panel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"),
        InlineKeyboardButton(text="💳 Платежи", callback_data="adm:payments"),
    )
    b.row(
        InlineKeyboardButton(text="🛒 Заказы", callback_data="adm:orders"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="adm:settings"),
    )
    b.row(
        InlineKeyboardButton(text="🏪 Магазин", callback_data="adm:shop"),
        InlineKeyboardButton(text="📋 Аудит", callback_data="adm:audit"),
    )
    b.row(
        InlineKeyboardButton(text="👑 Администраторы", callback_data="adm:admins"),
        InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:broadcast"),
    )
    return b.as_markup()


def back_panel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Панель", callback_data="adm:home")
    return b.as_markup()


def settings_kb(sub_dur: int, sub_price: float, shop_price: float) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text=f"⏱ Срок подписки: {sub_dur} дн.",
        callback_data="adm:settings:sub_dur",
    ))
    b.row(InlineKeyboardButton(
        text=f"💰 Цена подписки: {sub_price:.2f} TON",
        callback_data="adm:settings:sub_price",
    ))
    b.row(InlineKeyboardButton(
        text=f"🏷 Цена в магазине: {shop_price:.2f} TON",
        callback_data="adm:settings:shop_price",
    ))
    b.row(InlineKeyboardButton(text="◀️ Панель", callback_data="adm:home"))
    return b.as_markup()


def shop_list_kb(products: list[ShopProduct]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in products:
        status_icon = "✅" if p.status == ProductStatus.ACTIVE else "⚠️" if not p.is_verified else "⏸"
        b.row(InlineKeyboardButton(
            text=f"{status_icon} #{p.id} {p.title[:30]}",
            callback_data=f"adm:shop:p:{p.id}",
        ))
    b.row(InlineKeyboardButton(text="◀️ Панель", callback_data="adm:home"))
    return b.as_markup()


def product_actions_kb(product: ShopProduct) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not product.is_verified:
        b.row(InlineKeyboardButton(
            text="✅ Верифицировать",
            callback_data=f"adm:shop:verify:{product.id}",
        ))
    if product.status == ProductStatus.ACTIVE:
        b.row(InlineKeyboardButton(
            text="⏸ Снять с продажи",
            callback_data=f"adm:shop:dis:{product.id}",
        ))
    elif product.status == ProductStatus.INACTIVE and product.is_verified:
        b.row(InlineKeyboardButton(
            text="▶️ Опубликовать",
            callback_data=f"adm:shop:en:{product.id}",
        ))
    b.row(InlineKeyboardButton(
        text="🗑 Удалить",
        callback_data=f"adm:confirm:del_prod:{product.id}",
    ))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="adm:shop"))
    return b.as_markup()


def confirm_kb(action_code: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm:do:{action_code}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="adm:home"),
    )
    return b.as_markup()


def admins_kb(db_admins: list, env_ids: list[int]) -> InlineKeyboardMarkup:
    """db_admins: list of User objects with is_admin=True."""
    b = InlineKeyboardBuilder()
    for admin in db_admins:
        is_env = admin.telegram_id in env_ids
        suffix = " 🔒" if is_env else ""
        label = f"@{admin.username}" if admin.username else str(admin.telegram_id)
        row = [InlineKeyboardButton(
            text=f"👤 {label}{suffix}",
            callback_data="adm:admins",
        )]
        if not is_env:
            row.append(InlineKeyboardButton(
                text="❌",
                callback_data=f"adm:confirm:rm_admin:{admin.telegram_id}",
            ))
        b.row(*row)
    b.row(
        InlineKeyboardButton(text="➕ Добавить", callback_data="adm:admins:add"),
        InlineKeyboardButton(text="◀️ Панель", callback_data="adm:home"),
    )
    return b.as_markup()


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📢 Отправить всем", callback_data="adm:broadcast:send"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="adm:home"),
    )
    return b.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="❌ Отмена", callback_data="adm:home")
    return b.as_markup()


def orders_list_kb(orders: list[ShopOrder]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for o in orders:
        product_title = o.product.title[:20] if o.product else "?"
        b.row(InlineKeyboardButton(
            text=f"#{o.id} {product_title} → Выдать",
            callback_data=f"adm:confirm:deliver:{o.id}",
        ))
    b.row(InlineKeyboardButton(text="◀️ Панель", callback_data="adm:home"))
    return b.as_markup()
