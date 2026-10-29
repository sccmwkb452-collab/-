"""Адаптер Crypto Pay API (@CryptoBot / @CryptoTestnetBot).

Официальный публичный API: https://help.crypt.bot/crypto-pay-api
Токен приложения создаётся в @CryptoBot → Crypto Pay → Create App и задаётся
только через переменную окружения CRYPTO_PAY_API_TOKEN.

Поддерживается:
- createInvoice / getInvoices — когда владелец продаёт (счёт покупателю);
- transfer / getTransfers — когда владелец покупает (перевод продавцу). Получатель должен
  хотя бы раз запустить @CryptoBot. transfer идемпотентен по spend_id.
Эскроу-сделок в Crypto Pay нет: перевод — это прямой платёж, а не «гарант».
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import aiohttp

from app.trading.base import AvailabilityResult, Capability, DealRequest, OpResult, OpStatus, TradeBotAdapter

logger = logging.getLogger(__name__)

NETWORKS = {
    "mainnet": ("https://pay.crypt.bot", "cryptobot"),
    "testnet": ("https://testnet-pay.crypt.bot", "cryptotestnetbot"),
}


class CryptoPayError(Exception):
    def __init__(self, name: str, code: int | None = None) -> None:
        super().__init__(name)
        self.name = name
        self.code = code


class _Unknown(Exception):
    """Ответ не получен (таймаут, обрыв, 5xx) — результат операции неизвестен."""


class CryptoPayAdapter(TradeBotAdapter):
    key = "cryptopay"
    title = "Crypto Pay (@CryptoBot)"

    def __init__(self, token: str, network: str = "mainnet", *, base_url: str | None = None,
                 session: aiohttp.ClientSession | None = None, timeout: float = 15) -> None:
        if network not in NETWORKS:
            raise ValueError(f"Неизвестная сеть Crypto Pay: {network}")
        self.token = token
        self.network = network
        self.base_url = (base_url or NETWORKS[network][0]).rstrip("/")
        self.official_usernames = {NETWORKS[network][1]}
        self._session = session
        self._own_session = session is None
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    def static_capabilities(self) -> list[Capability]:
        return [Capability.CHECK, Capability.CREATE_INVOICE, Capability.DEAL_STATUS, Capability.PAY,
                Capability.PAYMENT_STATUS, Capability.BALANCE, Capability.EXCHANGE_RATES,
                Capability.IDEMPOTENT_PAYMENTS]

    async def _call(self, method: str, **params: Any) -> Any:
        if not self.token:
            raise CryptoPayError("CRYPTO_PAY_API_TOKEN не задан")
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        clean = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in params.items() if v is not None}
        try:
            async with self._session.post(
                f"{self.base_url}/api/{method}", json=clean, headers={"Crypto-Pay-API-Token": self.token}
            ) as resp:
                if resp.status >= 500:
                    raise _Unknown(f"HTTP {resp.status}")
                payload = await resp.json(content_type=None)
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError, aiohttp.ServerTimeoutError) as exc:
            raise _Unknown(str(exc) or type(exc).__name__) from exc
        except aiohttp.ContentTypeError as exc:
            raise _Unknown("некорректный ответ сервера") from exc
        if not isinstance(payload, dict):
            raise _Unknown("некорректный ответ сервера")
        if not payload.get("ok"):
            err = payload.get("error") or {}
            raise CryptoPayError(str(err.get("name") or err or "UNKNOWN_ERROR"), err.get("code"))
        return payload.get("result")

    async def check(self) -> AvailabilityResult:
        try:
            me = await self._call("getMe")
            currencies = await self._call("getCurrencies")
        except (CryptoPayError, _Unknown) as exc:
            return AvailabilityResult(False, [], [], error=str(exc))
        codes = sorted({c["code"] for c in currencies or [] if c.get("code") and not c.get("is_fiat")})
        return AvailabilityResult(True, self.static_capabilities(), codes, info={"app": me})

    # ── Продажа: счёт ─────────────────────────────────────────────────────

    def _invoice_url_ok(self, url: str | None) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        user = parsed.path.strip("/").split("/")[0].lower() if parsed.netloc in ("t.me", "telegram.me") else ""
        return user in self.official_usernames

    async def create_invoice(self, req: DealRequest) -> OpResult:
        try:
            inv = await self._call(
                "createInvoice", asset=req.currency, amount=_amount(req.amount), description=req.description[:1024],
                payload=req.idempotency_key, expires_in=86400, allow_anonymous=False,
            )
        except _Unknown as exc:
            return OpResult(OpStatus.UNKNOWN, error=f"нет ответа Crypto Pay: {exc}")
        except CryptoPayError as exc:
            return OpResult(OpStatus.FAILED, error=exc.name)
        url = inv.get("bot_invoice_url") or inv.get("pay_url")
        if not self._invoice_url_ok(url):
            return OpResult(OpStatus.FAILED, external_id=str(inv.get("invoice_id")),
                            error=f"ссылка на оплату ведёт не на официального бота: {url}")
        return OpResult(OpStatus.SUCCESS, external_id=str(inv["invoice_id"]), url=url, data={"invoice": inv})

    async def find_invoice_by_payload(self, payload: str) -> OpResult:
        try:
            res = await self._call("getInvoices", count=100)
        except (_Unknown, CryptoPayError) as exc:
            return OpResult(OpStatus.UNKNOWN, error=str(exc))
        for inv in (res or {}).get("items", []):
            if inv.get("payload") == payload:
                return OpResult(OpStatus.SUCCESS, external_id=str(inv["invoice_id"]),
                                url=inv.get("bot_invoice_url") or inv.get("pay_url"), data={"invoice": inv})
        return OpResult(OpStatus.NOT_FOUND)

    async def deal_status(self, external_id: str) -> OpResult:
        try:
            res = await self._call("getInvoices", invoice_ids=external_id)
        except _Unknown as exc:
            return OpResult(OpStatus.UNKNOWN, error=str(exc))
        except CryptoPayError as exc:
            return OpResult(OpStatus.FAILED, error=exc.name)
        items = (res or {}).get("items", [])
        if not items:
            return OpResult(OpStatus.NOT_FOUND)
        status = items[0].get("status")
        mapped = {"paid": OpStatus.SUCCESS, "active": OpStatus.PENDING, "expired": OpStatus.FAILED}.get(status, OpStatus.UNKNOWN)
        return OpResult(mapped, external_id=external_id, data={"invoice": items[0], "raw_status": status})

    # ── Покупка: перевод продавцу ─────────────────────────────────────────

    async def pay(self, req: DealRequest, spend_id: str) -> OpResult:
        if not req.counterparty_telegram_id:
            return OpResult(OpStatus.FAILED, error="неизвестен Telegram ID получателя")
        try:
            tr = await self._call(
                "transfer", user_id=req.counterparty_telegram_id, asset=req.currency, amount=_amount(req.amount),
                spend_id=spend_id, comment=req.description[:1024],
            )
        except _Unknown as exc:
            return OpResult(OpStatus.UNKNOWN, error=f"нет ответа Crypto Pay: {exc}")
        except CryptoPayError as exc:
            # Повторный spend_id может означать, что перевод уже прошёл — только сверка.
            if "SPEND" in exc.name.upper():
                return OpResult(OpStatus.UNKNOWN, error=exc.name)
            return OpResult(OpStatus.FAILED, error=exc.name)
        status = OpStatus.SUCCESS if tr.get("status") == "completed" else OpStatus.UNKNOWN
        return OpResult(status, external_id=str(tr.get("transfer_id")), data={"transfer": tr})

    async def payment_status(self, spend_id: str, external_id: str | None) -> OpResult:
        try:
            res = await self._call("getTransfers", spend_id=spend_id, transfer_ids=external_id, count=100)
        except _Unknown as exc:
            return OpResult(OpStatus.UNKNOWN, error=str(exc))
        except CryptoPayError as exc:
            return OpResult(OpStatus.UNKNOWN, error=exc.name)
        items = (res or {}).get("items", [])
        if items and any("spend_id" in t for t in items):
            matches = [t for t in items if t.get("spend_id") == spend_id]
        elif external_id:
            matches = [t for t in items if str(t.get("transfer_id")) == str(external_id)]
        elif items:
            # Сервер не вернул spend_id — подтвердить отсутствие платежа нельзя.
            return OpResult(OpStatus.UNKNOWN, error="Crypto Pay не вернул spend_id, сверка невозможна")
        else:
            matches = []
        if not matches:
            return OpResult(OpStatus.NOT_FOUND)
        tr = matches[0]
        status = OpStatus.SUCCESS if tr.get("status") == "completed" else OpStatus.PENDING
        return OpResult(status, external_id=str(tr.get("transfer_id")), data={"transfer": tr})

    async def exchange_rates(self) -> dict[tuple[str, str], Decimal]:
        try:
            items = await self._call("getExchangeRates")
        except (_Unknown, CryptoPayError):
            return {}
        rates: dict[tuple[str, str], Decimal] = {}
        for r in items or []:
            if not r.get("is_valid"):
                continue
            try:
                rates[(r["source"], r["target"])] = Decimal(str(r["rate"]))
            except (KeyError, InvalidOperation):
                continue
        return rates

    async def close(self) -> None:
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None


def _amount(value: Decimal) -> str:
    return format(value.normalize(), "f")
