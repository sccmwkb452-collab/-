from aiogram.fsm.state import State, StatesGroup


class ProductForm(StatesGroup):
    title = State()
    price = State()
    short = State()


class ProductEdit(StatesGroup):
    value = State()
    photo = State()
    items = State()


class CsvImport(StatesGroup):
    file = State()


class CategoryEdit(StatesGroup):
    value = State()


class OrderSearch(StatesGroup):
    number = State()
    refund_reason = State()


class UserSearch(StatesGroup):
    query = State()
    amount = State()
    reason = State()
    ban_reason = State()


class PaymentAdmin(StatesGroup):
    refund_reason = State()


class BroadcastForm(StatesGroup):
    message = State()


class SettingEdit(StatesGroup):
    value = State()
