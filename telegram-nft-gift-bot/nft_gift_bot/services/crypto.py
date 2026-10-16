"""Encryption of sensitive values and masking helpers for logs/UI."""

from __future__ import annotations

import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken


class SecretBox:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())
        # Separate derived key for lookup hashes so they can't be used to decrypt anything.
        self._hmac_key = hashlib.sha256(b"nft-gift-bot/lookup/" + key.encode()).digest()

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Cannot decrypt value: wrong ENCRYPTION_KEY or corrupted data") from exc

    def lookup_hash(self, value: str) -> str:
        return hmac.new(self._hmac_key, value.encode(), hashlib.sha256).hexdigest()


def generate_key() -> str:
    return Fernet.generate_key().decode()


def mask(value: str | int | None, visible: int = 4) -> str:
    if value is None:
        return "—"
    text = str(value)
    if len(text) <= visible:
        return "•" * len(text)
    return "•" * min(len(text) - visible, 6) + text[-visible:]
