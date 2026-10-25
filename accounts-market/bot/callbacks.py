"""Callback data. Every payload stays well below Telegram's 64-byte limit."""

from aiogram.filters.callback_data import CallbackData


class Nav(CallbackData, prefix="n"):
    to: str  # home, catalog, popular, profile, topup, orders, ref, support, rules


class Cat(CallbackData, prefix="c"):
    id: int
    page: int = 0


class Prod(CallbackData, prefix="p"):
    id: int
    src: str = "c"  # c = category list, p = popular, o = order
    page: int = 0


class Buy(CallbackData, prefix="b"):
    id: int
    price: int
    src: str = "c"
    page: int = 0


class BuyOk(CallbackData, prefix="bo"):
    id: int
    price: int
    nonce: str


class Orders(CallbackData, prefix="os"):
    page: int = 0


class OrderView(CallbackData, prefix="ov"):
    id: int
    page: int = 0


class Txs(CallbackData, prefix="tx"):
    page: int = 0


class Topup(CallbackData, prefix="t"):
    amount: int  # rubles; 0 = enter manually


class Pay(CallbackData, prefix="pay"):
    action: str  # check, demo, show
    id: int


class Payments(CallbackData, prefix="ps"):
    page: int = 0


class RefHistory(CallbackData, prefix="rh"):
    page: int = 0


class Adm(CallbackData, prefix="a"):
    """Admin actions: s = section/action, id = object, p = page, v = extra value."""

    s: str
    id: int = 0
    p: int = 0
    v: str = ""


class Noop(CallbackData, prefix="x"):
    pass


class Countries(CallbackData, prefix="cg"):
    id: int  # category
    page: int = 0


class CountryProds(CallbackData, prefix="ck"):
    id: int  # category
    cc: str
    page: int = 0


class Cheapest(CallbackData, prefix="ch"):
    id: int  # category


class CountrySearch(CallbackData, prefix="cs"):
    id: int  # category


class Bulk(CallbackData, prefix="bk"):
    id: int  # category
    page: int = 0


class Qty(CallbackData, prefix="qq"):
    id: int  # product
    price: int


class BuyN(CallbackData, prefix="bn"):
    id: int
    price: int
    qty: int


class BuyNOk(CallbackData, prefix="bq"):
    id: int
    price: int
    qty: int
    nonce: str
