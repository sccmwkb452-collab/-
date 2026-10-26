"""PlayerOK in manual mode.

PlayerOK has no public API. The only known programmatic route (the unofficial
PlayerokAPI library) imitates a browser TLS fingerprint and reuses a
DDoS-Guard cookie, i.e. it works around the platform's protection, and the
platform's permission for automation is not confirmed (docs/RESEARCH.md).
So the system does not talk to playerok.com at all: listings are prepared
for copy-paste, orders/messages/reviews are entered by the operator or
imported from CSV, and automation degrades to hints for the operator.
"""

from __future__ import annotations

from .base import MarketplaceAdapter, MarketplaceCapabilities

REASON = (
    "У PlayerOK нет официального API. Единственный известный способ автоматизации обходит защиту DDoS-Guard, "
    "а разрешение площадки на автоматизацию не подтверждено — поэтому система не обращается к playerok.com. "
    "Действие выполняется вручную, система готовит текст и подсказки."
)

REASONS = {
    "fetch_orders": "Заказы вносятся вручную (бот, веб-панель) или импортом CSV: API заказов у PlayerOK нет.",
    "fetch_messages": "Сообщения покупателей не приходят автоматически: API чатов у PlayerOK нет. Записывайте их вручную — автоответчик подберёт ответ.",
    "send_messages": "Отправить сообщение покупателю на PlayerOK система не может. Готовый текст приходит вам в Telegram с кнопкой «Скопировать».",
    "publish_listings": "Публикация выполняется вами на PlayerOK. Система готовит название, описание, цену и изображения и фиксирует номер лота.",
    "update_listings": "Цену и описание на PlayerOK меняете вы. Система подскажет, что и где изменить.",
    "raise_listings": "Поднятие лотов на PlayerOK доступно только в интерфейсе площадки.",
    "confirm_deals": "Подтверждение сделок на PlayerOK выполняется только вручную.",
    "fetch_reviews": "Отзывы вносятся вручную.",
    "fetch_market": "Цены конкурентов вносит оператор (наблюдение с датой). Автоматический сбор потребовал бы обхода защиты сайта.",
    "presence": "Статус «в сети» на PlayerOK система не видит.",
}


class PlayerokManualAdapter(MarketplaceAdapter):
    code = "playerok_manual"
    title = "PlayerOK — ручной режим"
    capabilities = MarketplaceCapabilities()
    unavailable_reason = REASON

    def reason(self, capability: str) -> str:
        return REASONS.get(capability, REASON)


_adapter: MarketplaceAdapter = PlayerokManualAdapter()


def get_marketplace() -> MarketplaceAdapter:
    return _adapter


def set_marketplace(adapter: MarketplaceAdapter) -> None:
    """Tests and future official integrations plug in here."""
    global _adapter
    _adapter = adapter
