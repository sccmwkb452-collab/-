"""
Модуль работы с NFT-подарками Telegram.

Telegram Bot API предоставляет методы для работы с подарками:
- getAvailableGifts  — список доступных подарков
- sendGift           — отправить подарок пользователю
- transferGift       — передать подарок другому владельцу (Bot API 9.0+)

Документация: https://core.telegram.org/bots/api#gifts
"""

from gift_manager.client import GiftManagerClient

__all__ = ["GiftManagerClient"]
