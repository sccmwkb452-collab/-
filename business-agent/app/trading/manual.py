"""Адаптер для торговых ботов без публичного API (гаранты, маркеты, эскроу-боты).

Telegram не позволяет одному боту управлять другим через Bot API, поэтому здесь нет
автоматического создания сделки. Агент готовит все данные, проверенную ссылку на
выбранного бота и инструкцию; шаги в торговом боте выполняет человек, а статусы
отмечаются в панели. Ничего не помечается выполненным без подтверждения человека.
"""
from app.trading.base import AvailabilityResult, Capability, DealRequest, OpResult, OpStatus, TradeBotAdapter


class ManualTradeBotAdapter(TradeBotAdapter):
    key = "manual"
    title = "Ручной режим (бот без API)"
    official_usernames = None
    # Операции создания/оплаты существуют, но выполняются человеком в выбранном боте.
    manual_only = True

    def __init__(self, bot_username: str) -> None:
        self.bot_username = bot_username.lstrip("@").lower()

    def static_capabilities(self) -> list[Capability]:
        return [Capability.CHECK, Capability.CREATE_DEAL, Capability.CREATE_INVOICE, Capability.PAY]

    async def check(self) -> AvailabilityResult:
        # Проверить «работоспособность» чужого бота без API нельзя; доступна только
        # проверка идентичности (числовой ID), которую делает TradeGuard.
        return AvailabilityResult(True, self.static_capabilities(), [],
                                  info={"note": "публичного API нет — операции выполняет человек"})

    def _instructions(self, req: DealRequest) -> str:
        action = "создайте сделку и оплатите" if req.side == "buy" else "создайте сделку на продажу"
        return (
            f"Откройте https://t.me/{self.bot_username} и {action}:\n"
            f"• {req.description}\n• Сумма: {req.amount} {req.currency}\n"
            f"• Номер сделки в панели: #{req.deal_id}\n"
            "Затем отметьте результат в панели «🤝 Управление сделками»."
        )

    async def create_deal(self, req: DealRequest) -> OpResult:
        return OpResult(OpStatus.REQUIRES_USER_ACTION, url=f"https://t.me/{self.bot_username}",
                        instructions=self._instructions(req))

    async def create_invoice(self, req: DealRequest) -> OpResult:
        return await self.create_deal(req)

    async def pay(self, req: DealRequest, spend_id: str) -> OpResult:
        return OpResult(OpStatus.REQUIRES_USER_ACTION, url=f"https://t.me/{self.bot_username}",
                        instructions=self._instructions(req))
