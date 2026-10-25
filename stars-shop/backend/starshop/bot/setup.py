"""What the bot registers in Telegram: commands, the menu button and the
update types. Plain data without aiogram, so the serverless API can check the
setup without importing the bot (seconds of a cold start)."""

from __future__ import annotations

MENU_BUTTON_TEXT = "🌐 Открыть магазин"
COMMANDS = (
    ("start", "Главное меню"),
    ("buy", "Купить Stars"),
    ("premium", "Telegram Premium"),
    ("orders", "Мои заказы"),
    ("profile", "Мой профиль"),
    ("ref", "Реферальная программа"),
    ("support", "Поддержка"),
)
# Must match the handlers (checked by tests against the dispatcher).
ALLOWED_UPDATES = ("message", "callback_query", "pre_checkout_query")
