"""Banner images with Telegram file_id caching (uploaded once per process)."""

from __future__ import annotations

import asyncio

from aiogram.types import BufferedInputFile, Message

from bot import banners

_file_ids: dict[str, str] = {}


def banner_key(name: str, shop_name: str) -> str:
    return f"banner:{name}:{shop_name}"


async def banner(name: str, shop_name: str) -> tuple[str, str | BufferedInputFile]:
    key = banner_key(name, shop_name)
    if key in _file_ids:
        return key, _file_ids[key]
    data = await asyncio.to_thread(banners.render_banner, name, shop_name)
    return key, BufferedInputFile(data, filename=f"{name}.jpg")


async def product_card(key: str, **kwargs) -> tuple[str, str | BufferedInputFile]:
    if key in _file_ids:
        return key, _file_ids[key]
    data = await asyncio.to_thread(lambda: banners.render_product_card(**kwargs))
    return key, BufferedInputFile(data, filename="product.jpg")


def remember(key: str | None, message: Message | bool | None) -> None:
    if key and isinstance(message, Message) and message.photo:
        if len(_file_ids) > 2000:
            _file_ids.clear()
        _file_ids[key] = message.photo[-1].file_id
