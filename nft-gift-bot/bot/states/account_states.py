from aiogram.fsm.state import State, StatesGroup


class AccountConnect(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_2fa = State()
