"""Read-only TON blockchain client (toncenter.com HTTP API v2).

Only reads transactions of our own receiver wallet: no private keys are needed
or stored anywhere in this project.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Protocol

import httpx

from nft_gift_bot.payments.verifier import IncomingTransfer

logger = logging.getLogger(__name__)


class ChainUnavailableError(RuntimeError):
    pass


class ChainClient(Protocol):
    async def get_incoming_transfers(self, address: str, limit: int = 100) -> list[IncomingTransfer]: ...


def _comment_from_msg(in_msg: dict[str, Any]) -> str:
    message = in_msg.get("message")
    if isinstance(message, str) and message:
        return message
    msg_data = in_msg.get("msg_data") or {}
    if msg_data.get("@type") == "msg.dataText" and msg_data.get("text"):
        try:
            return base64.b64decode(msg_data["text"]).decode("utf-8", errors="replace")
        except ValueError:
            return ""
    return ""


def parse_transactions(payload: dict[str, Any]) -> list[IncomingTransfer]:
    if not payload.get("ok"):
        raise ChainUnavailableError(f"toncenter error: {payload.get('error', 'unknown')}")
    transfers: list[IncomingTransfer] = []
    for tx in payload.get("result") or []:
        in_msg = tx.get("in_msg") or {}
        sender = in_msg.get("source") or ""
        if not sender:  # external message, not a transfer from a wallet
            continue
        try:
            value = int(in_msg.get("value") or 0)
        except (TypeError, ValueError):
            continue
        tx_hash = (tx.get("transaction_id") or {}).get("hash")
        if not tx_hash or value <= 0:
            continue
        transfers.append(
            IncomingTransfer(
                tx_hash=tx_hash,
                sender=sender,
                value_nano=value,
                comment=_comment_from_msg(in_msg),
                utime=int(tx.get("utime") or 0),
            )
        )
    return transfers


class TonCenterClient:
    def __init__(self, base_url: str, api_key: str = "", http: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        headers = {"X-API-Key": api_key} if api_key else {}
        self._http = http or httpx.AsyncClient(timeout=15.0, headers=headers)

    async def get_incoming_transfers(self, address: str, limit: int = 100) -> list[IncomingTransfer]:
        try:
            response = await self._http.get(
                f"{self._base_url}/getTransactions",
                params={"address": address, "limit": limit, "archival": "true"},
            )
        except httpx.HTTPError as exc:
            raise ChainUnavailableError(f"toncenter request failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise ChainUnavailableError(f"toncenter HTTP {response.status_code}")
        return parse_transactions(response.json())

    async def close(self) -> None:
        await self._http.aclose()
