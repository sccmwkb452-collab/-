"""TradeGuard — единственная точка, через которую проходят все торговые операции.

Строгие правила:
- сделка возможна только через АКТИВНОГО торгового бота владельца;
- идентичность проверяется по сохранённому числовому Telegram ID, а не по имени;
- ID в снимке сделки должен совпадать с текущим активным ботом (смена бота останавливает сделку);
- недоступность или отсутствие операции = остановка; запасных ботов нет.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TradeBotConfig, utcnow
from app.trading.base import Capability, TradeBotAdapter
from app.trading.registry import AdapterFactory

# Не настраивается: посторонние боты не допускаются никогда.
ALLOW_UNLISTED_BOTS = False


class TradeBlocked(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class GuardedBot:
    config: TradeBotConfig
    adapter: TradeBotAdapter


async def get_active_trade_bot(session: AsyncSession, owner_id: int) -> TradeBotConfig | None:
    return await session.scalar(
        select(TradeBotConfig).where(TradeBotConfig.owner_id == owner_id, TradeBotConfig.is_active.is_(True))
    )


async def allowed_usernames(session: AsyncSession, owner_id: int) -> set[str]:
    """Username ботов, которые агенту можно упоминать в переписке: только активный."""
    cfg = await get_active_trade_bot(session, owner_id)
    return {cfg.bot_username} if cfg else set()


async def require_trade_bot(
    session: AsyncSession,
    owner_id: int,
    factory: AdapterFactory,
    *,
    operation: Capability | None = None,
    expected_bot_user_id: int | None = None,
    check_availability: bool = True,
) -> GuardedBot:
    cfg = await get_active_trade_bot(session, owner_id)
    if cfg is None:
        raise TradeBlocked("no_trade_bot", "Торговый бот не выбран — создавать сделки нельзя.")
    if not cfg.bot_user_id or cfg.verified_at is None:
        raise TradeBlocked("not_verified", f"Торговый бот @{cfg.bot_username} не прошёл проверку идентичности.")
    if expected_bot_user_id is not None and expected_bot_user_id != cfg.bot_user_id:
        raise TradeBlocked(
            "identity_mismatch",
            "Сделка была подготовлена для другого торгового бота. Активный бот изменился — операция остановлена.",
        )
    adapter = factory.for_config(cfg)
    if adapter.official_usernames is not None and cfg.bot_username not in adapter.official_usernames:
        raise TradeBlocked(
            "identity_mismatch",
            f"@{cfg.bot_username} не является официальным ботом интеграции «{adapter.title}».",
        )
    if operation is not None and operation not in adapter.static_capabilities():
        raise TradeBlocked("not_supported", f"@{cfg.bot_username} не поддерживает операцию «{operation}».")
    if check_availability:
        result = await adapter.check()
        cfg.last_check_at = utcnow()
        cfg.status = "ok" if result.ok else "unavailable"
        cfg.last_error = result.error
        if result.ok and result.currencies:
            cfg.supported_currencies = result.currencies
        if not result.ok:
            raise TradeBlocked("unavailable", f"Торговый бот @{cfg.bot_username} недоступен: {result.error}")
    return GuardedBot(cfg, adapter)


def verify_shared_bot(adapter_key: str, user_id: int, username: str | None, official: str | None) -> str | None:
    """Проверка бота, выбранного через кнопку request_users. None — всё в порядке, иначе текст ошибки."""
    if not username:
        return "У выбранного бота нет username — его нельзя надёжно указать собеседнику."
    if not user_id:
        return "Telegram не передал ID бота."
    if official and username.lower() != official:
        return f"Для интеграции «{adapter_key}» нужен официальный бот @{official}, а выбран @{username}."
    return None
