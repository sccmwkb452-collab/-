from __future__ import annotations

import hashlib
import secrets

# Crockford base32 without ambiguous characters (I, L, O, U).
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def order_number() -> str:
    """Short public order number, e.g. ``7KQ2M9XD``. Random, not sequential,
    so it does not reveal sales volume."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


def referral_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(7))


def token_urlsafe(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
