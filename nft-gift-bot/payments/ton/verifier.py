"""Server-side verification: checks real blockchain tx before crediting subscription.

NEVER activates a subscription based on a screenshot, user message, or button press
alone. Only a transaction verified here — correct network, recipient, amount and unique
comment — triggers activation.
"""
import logging
from dataclasses import dataclass

from payments.ton.client import NANOTON_PER_TON, TonCenterClient, TonTransaction

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    ok: bool
    tx: TonTransaction | None = None
    reason: str = ""


class TonPaymentVerifier:
    def __init__(
        self,
        client: TonCenterClient,
        recipient_address: str,
        required_ton: float,
    ) -> None:
        self._client = client
        # Normalise to lower-case for comparison; real addresses are case-insensitive
        self._recipient = recipient_address.strip().lower()
        self._required_nanoton = int(required_ton * NANOTON_PER_TON)

    async def verify(self, payment_comment: str) -> VerificationResult:
        """
        Fetch the last 100 incoming transactions for our address and look for a tx
        whose comment matches `payment_comment`, destination is our address, and
        value >= required amount.

        Returns VerificationResult(ok=True, tx=...) on success.
        Subscription activation must ONLY happen when ok is True AND the tx_hash
        has not been credited before (checked in payment_service).
        """
        if not self._recipient:
            return VerificationResult(ok=False, reason="Recipient address not configured")

        try:
            txs = await self._client.get_transactions(self._recipient, limit=100)
        except Exception as exc:
            logger.warning("TonCenter fetch failed: %s", exc)
            return VerificationResult(ok=False, reason=f"Blockchain query failed: {exc}")

        for tx in txs:
            if tx.comment.strip() != payment_comment:
                continue
            if tx.dst_address.lower() != self._recipient:
                logger.warning(
                    "comment=%r matched but destination mismatch: got=%s expected=%s",
                    payment_comment,
                    tx.dst_address,
                    self._recipient,
                )
                return VerificationResult(ok=False, reason="Wrong recipient address in tx")

            if tx.amount_nanoton < self._required_nanoton:
                logger.warning(
                    "comment=%r matched but amount too low: got=%d expected>=%d nanoton",
                    payment_comment,
                    tx.amount_nanoton,
                    self._required_nanoton,
                )
                return VerificationResult(ok=False, reason="Insufficient amount in tx")

            logger.info(
                "TON tx verified: comment=%r hash=%s amount=%d nanoton",
                payment_comment,
                tx.tx_hash,
                tx.amount_nanoton,
            )
            return VerificationResult(ok=True, tx=tx)

        return VerificationResult(ok=False, reason="Transaction not found on blockchain")
