"""
Конфигурация Telegram Premium Custom Emoji.

Как получить custom_emoji_id:
1. Найди нужный стикер/эмодзи в Telegram Premium наборе
2. Перешли его в @userinfobot или используй getCustomEmojiStickers API
3. Вставь полученный ID в поле ниже

Если ID пустой (""), бот автоматически использует обычный emoji-символ.
Документация: https://core.telegram.org/bots/api#messageentity  (type=custom_emoji)
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmojiConfig:
    """Пара: fallback-символ + опциональный Premium Custom Emoji ID."""
    char: str          # обычный emoji — виден всем и используется в length/offset
    custom_id: str     # custom_emoji_id; "" → не используется


# ─── Набор эмодзи интерфейса ───────────────────────────────────────────────
# Заполни custom_id реальными ID из Telegram Premium стикер-пака.
# Все ID ниже — заглушки; бот работает с ними в fallback-режиме.
EMOJI = {
    # Главное меню
    "diamond":     EmojiConfig("💎", ""),   # подписка
    "gift":        EmojiConfig("🎁", ""),   # NFT-подарки
    "link":        EmojiConfig("🔗", ""),   # подключить аккаунт
    "cart":        EmojiConfig("🛒", ""),   # купить tdata
    "profile":     EmojiConfig("👤", ""),   # профиль
    "info":        EmojiConfig("ℹ️", ""),  # информация

    # Декоративные
    "shield":      EmojiConfig("🛡️", ""),  # щит — заголовок бота
    "crown":       EmojiConfig("👑", ""),   # premium
    "gem_blue":    EmojiConfig("🔷", ""),   # синий камень
    "gem_red":     EmojiConfig("🔴", ""),   # красный камень
    "star":        EmojiConfig("⭐", ""),   # звезда
    "fire":        EmojiConfig("🔥", ""),   # огонь
    "lock":        EmojiConfig("🔒", ""),   # заблокировано
    "check":       EmojiConfig("✅", ""),   # готово
    "cross":       EmojiConfig("❌", ""),   # нет
    "arrow_right": EmojiConfig("▶️", ""),  # стрелка
    "back":        EmojiConfig("◀️", ""),  # назад
    "nft":         EmojiConfig("🖼️", ""),  # NFT
    "wallet":      EmojiConfig("💼", ""),   # кошелёк
    "calendar":    EmojiConfig("📅", ""),   # дата
    "stats":       EmojiConfig("📊", ""),   # статистика
    "support":     EmojiConfig("🆘", ""),   # поддержка
    "warning":     EmojiConfig("⚠️", ""),  # предупреждение
    "sparkle":     EmojiConfig("✨", ""),   # блеск
    "rocket":      EmojiConfig("🚀", ""),   # ракета
}
