from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class SubCb(CallbackData, prefix="sub"):
    action: str  # offer | buy | check | cancel
    payment_id: int = 0


class AccountCb(CallbackData, prefix="acc"):
    action: str  # status | revoke | revoke_yes | notify_on | notify_off


class GiftCb(CallbackData, prefix="gift"):
    action: str  # list | open | transfer | confirm | cancel | abort
    id: int = 0


class AdminCb(CallbackData, prefix="adm"):
    section: str  # stats | users | payments | transfers | tickets | audit | help
