"""Encryption of stored secrets (supplier credentials, digital codes).

Fernet (AES-128-CBC + HMAC-SHA256) with a key from ``CREDENTIALS_KEY``. Key
rotation: put the new key first and the old ones after it, separated by
commas — values encrypted with any listed key are readable, new values use the
first one, and ``python -m autocommerce.cli rotate-keys`` re-encrypts the rest.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from ..config import get_settings

log = logging.getLogger(__name__)
_warned = False


def _keys() -> list[bytes]:
    global _warned
    settings = get_settings()
    raw = settings.credentials_key.get_secret_value().strip()
    if raw:
        return [k.strip().encode() for k in raw.split(",") if k.strip()]
    if settings.is_production:
        raise RuntimeError("CREDENTIALS_KEY is required in production")
    # Development and tests: a deterministic key derived from SECRET_KEY.
    if not _warned:
        log.warning("CREDENTIALS_KEY is not set: using a key derived from SECRET_KEY (development only)")
        _warned = True
    digest = hashlib.sha256(b"pac-credentials:" + settings.secret_key.get_secret_value().encode()).digest()
    return [base64.urlsafe_b64encode(digest)]


def _fernet() -> MultiFernet:
    return MultiFernet([Fernet(k) for k in _keys()])


def generate_key() -> str:
    return Fernet.generate_key().decode()


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("cannot decrypt value: wrong CREDENTIALS_KEY?") from exc


def rotate(token: str) -> str:
    return _fernet().rotate(token.encode()).decode()


def fingerprint(value: str, purpose: str) -> str:
    """Keyed hash used to detect duplicates without storing the value in clear."""
    secret = get_settings().secret_key.get_secret_value().encode()
    return hmac.new(secret, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def token_hash(token: str) -> str:
    """Hash of a session or one-time token as stored in the database."""
    return fingerprint(token, "token")
