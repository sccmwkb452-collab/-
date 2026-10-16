"""Thin async wrapper around TonCenter API v2."""
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

MAINNET_URL = "https://toncenter.com/api/v2"
TESTNET_URL = "https://testnet.toncenter.com/api/v2"

NANOTON_PER_TON = 1_000_000_000


@dataclass
class TonTransaction:
    tx_hash: str
    lt: str                  # logical time
    src_address: str
    dst_address: str
    amount_nanoton: int
    comment: str             # decoded text from in_msg body


class TonCenterError(Exception):
    pass


class TonCenterClient:
    def __init__(self, api_key: str, network: str = "mainnet") -> None:
        self._base = MAINNET_URL if network == "mainnet" else TESTNET_URL
        self._headers = {"X-API-Key": api_key} if api_key else {}

    async def get_transactions(
        self, address: str, limit: int = 100
    ) -> list[TonTransaction]:
        url = f"{self._base}/getTransactions"
        params: dict[str, Any] = {
            "address": address,
            "limit": limit,
            "archival": "false",
        }
        async with aiohttp.ClientSession(headers=self._headers) as http:
            async with http.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise TonCenterError(f"TonCenter HTTP {resp.status}: {text[:200]}")
                data = await resp.json()

        if not data.get("ok"):
            raise TonCenterError(f"TonCenter error: {data}")

        txs: list[TonTransaction] = []
        for raw in data.get("result", []):
            parsed = _parse_tx(raw)
            if parsed is not None:
                txs.append(parsed)
        return txs


def _parse_tx(raw: dict) -> TonTransaction | None:
    try:
        in_msg = raw.get("in_msg", {})
        source = in_msg.get("source", "")
        destination = in_msg.get("destination", "")
        value = int(in_msg.get("value", 0))
        msg_data = in_msg.get("msg_data", {})

        comment = ""
        if msg_data.get("@type") == "msg.dataText":
            comment = msg_data.get("text", "")

        tx_id = raw.get("transaction_id", {})
        tx_hash = tx_id.get("hash", "")
        lt = tx_id.get("lt", "")

        if not tx_hash or not destination:
            return None

        return TonTransaction(
            tx_hash=tx_hash,
            lt=lt,
            src_address=source,
            dst_address=destination,
            amount_nanoton=value,
            comment=comment,
        )
    except Exception:
        logger.debug("Failed to parse tx: %s", raw, exc_info=True)
        return None
