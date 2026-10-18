"""Простой парсер NFT-подарков Telegram с публичных страниц t.me/nft/."""
from gift_parser.models import Attribute, Gift
from gift_parser.parser import GiftParser, parse_gift_html

__all__ = ["Attribute", "Gift", "GiftParser", "parse_gift_html"]
