"""Fernet-based symmetric encryption for Telethon session strings.

The key must be a URL-safe base64-encoded 32-byte value stored in
ACCOUNT_ENCRYPTION_KEY. Generate with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import logging

logger = logging.getLogger(__name__)


def _get_fernet(key: str):
    from cryptography.fernet import Fernet  # noqa: F401
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_session(session_string: str, key: str) -> str:
    """Returns a base64-encoded ciphertext string safe for TEXT column storage."""
    f = _get_fernet(key)
    return f.encrypt(session_string.encode()).decode()


def decrypt_session(encrypted: str, key: str) -> str:
    """Raises cryptography.fernet.InvalidToken on tamper / wrong key."""
    f = _get_fernet(key)
    return f.decrypt(encrypted.encode()).decode()
