"""Реестр адаптеров торговых ботов."""
from app.config import Settings
from app.db.models import TradeBotConfig
from app.trading.base import TradeBotAdapter
from app.trading.cryptopay import NETWORKS, CryptoPayAdapter
from app.trading.manual import ManualTradeBotAdapter

ADAPTERS = {
    "cryptopay": "Crypto Pay API (@CryptoBot) — автоматические счета и переводы",
    "manual": "Любой другой бот (без API) — агент готовит сделку, шаги выполняет человек",
}


def official_username_for(adapter_key: str, settings: Settings) -> str | None:
    if adapter_key == "cryptopay":
        return NETWORKS[settings.crypto_pay_network][1]
    return None


class AdapterFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: dict[int, TradeBotAdapter] = {}

    def for_config(self, cfg: TradeBotConfig) -> TradeBotAdapter:
        cached = self._cache.get(cfg.id)
        if cached is not None:
            return cached
        if cfg.adapter == "cryptopay":
            adapter: TradeBotAdapter = CryptoPayAdapter(self.settings.crypto_pay_api_token, self.settings.crypto_pay_network)
        elif cfg.adapter == "manual":
            adapter = ManualTradeBotAdapter(cfg.bot_username)
        else:
            raise ValueError(f"Неизвестный адаптер торгового бота: {cfg.adapter}")
        self._cache[cfg.id] = adapter
        return adapter

    def forget(self, cfg_id: int) -> None:
        self._cache.pop(cfg_id, None)

    async def close(self) -> None:
        for adapter in self._cache.values():
            await adapter.close()
        self._cache.clear()
