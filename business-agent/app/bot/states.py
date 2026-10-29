from aiogram.fsm.state import State, StatesGroup


class Input(StatesGroup):
    value = State()  # универсальный ввод значения (ключ — в данных FSM)
    file = State()  # ожидание файла импорта парсера
    media = State()  # ожидание медиа для медиатеки


class AdminInput(StatesGroup):
    collecting = State()


class TradeAdd(StatesGroup):
    choose_bot = State()
