from aiogram.filters.callback_data import CallbackData


class Cb(CallbackData, prefix="c"):
    """s — раздел, a — действие, i — id объекта, v — значение."""

    s: str
    a: str = "show"
    i: int = 0
    v: str = ""
