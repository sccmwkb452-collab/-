from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nft_gift_bot.database.base import Base, TimestampMixin


class ConnectionStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"  # turned off in Telegram (may be re-enabled there)
    REVOKED = "revoked"  # owner disconnected in the bot; encrypted ID is wiped


class ConnectedAccount(Base, TimestampMixin):
    """A Telegram Business connection made by the account owner.

    The Business connection ID is sensitive (it authorises bot actions on the
    owner's account), so it is stored Fernet-encrypted. ``connection_lookup_hash``
    is a keyed HMAC used to find the row when Telegram sends an update.
    """

    __tablename__ = "connected_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connection_lookup_hash: Mapped[str] = mapped_column(String(64), unique=True)
    connection_id_encrypted: Mapped[str] = mapped_column(Text)
    telegram_account_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default=ConnectionStatus.ACTIVE)
    can_transfer_gifts: Mapped[bool] = mapped_column(default=False)
    can_view_gifts: Mapped[bool] = mapped_column(default=False)
    can_transfer_stars: Mapped[bool] = mapped_column(default=False)
    notify_new_gifts: Mapped[bool] = mapped_column(default=True)
    connected_at: Mapped[datetime]
    disconnected_at: Mapped[datetime | None] = mapped_column(default=None)
