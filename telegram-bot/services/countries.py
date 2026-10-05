from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient


async def get_user_country(client: TelegramClient, user_id: int) -> str | None:
    from telethon import functions
    from telethon.tl.types import User

    try:
        result = await client(functions.users.GetFullUserRequest(id=user_id))
        users = [u for u in (result.users or []) if isinstance(u, User) and u.id == user_id]
        user = users[0] if users else None
        if user and hasattr(user, 'restricted_by_default') and hasattr(user, 'restriction_reason'):
            pass
        full_user = result.full_user
        if hasattr(full_user, 'location') and full_user.location:
            location = full_user.location
            if hasattr(location, 'country_iso2'):
                return location.country_iso2.lower()
    except Exception:
        pass
    return None


def country_key_for_user_id(user_id: int | None, country_code: str | None) -> str:
    if country_code:
        country_code_lower = country_code.lower()
        if country_code_lower == "ua":
            return "country:ua"
        elif country_code_lower == "uz":
            return "country:uz"
        elif country_code_lower == "kz":
            return "country:kz"
    return "other"
