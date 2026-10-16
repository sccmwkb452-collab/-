"""FSM states for the inline admin panel."""
from aiogram.fsm.state import State, StatesGroup


class AdminFSM(StatesGroup):
    # Settings
    enter_sub_duration = State()
    enter_sub_price = State()
    enter_shop_price = State()

    # Shop
    enter_verify_note = State()     # FSM data: product_id

    # Admins
    enter_new_admin_id = State()

    # Broadcast
    enter_broadcast_text = State()
    confirm_broadcast = State()     # FSM data: broadcast_text
