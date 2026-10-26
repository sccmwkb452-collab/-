"""Supplier without an API: prices are entered by the operator, purchases are
made by hand and confirmed in the panel."""

from __future__ import annotations

from .base import ConnectionCheck, SupplierAdapter, SupplierCapabilities


class ManualAdapter(SupplierAdapter):
    code = "manual"
    title = "Ручной поставщик"
    capabilities = SupplierCapabilities()
    description = "Цены вносятся вручную, закупка выполняется оператором и подтверждается в панели."

    def configured(self) -> bool:
        return True

    async def check(self) -> ConnectionCheck:
        return ConnectionCheck(True, "API нет: цены и закупки вносятся вручную")


class PolicyBlockedAdapter(SupplierAdapter):
    """Placeholder for suppliers whose goods may not be resold (see docs/RESEARCH.md)."""

    code = "none"
    title = "Заблокирован политикой"
    capabilities = SupplierCapabilities()
    description = "Интеграция не создана: перепродажа товаров этого поставщика нарушает правила платформы."

    def configured(self) -> bool:
        return False

    async def check(self) -> ConnectionCheck:
        return ConnectionCheck(False, "Заблокировано политикой: перепродажа нарушает правила платформы")
