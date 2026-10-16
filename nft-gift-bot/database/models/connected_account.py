"""Connected Telegram account — stores MTProto session encrypted at rest."""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class AccountStatus(str, enum.Enum):
    PENDING_CODE = "pending_code"
    PENDING_2FA = "pending_2fa"
    CONNECTED = "connected"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus),
        default=AccountStatus.PENDING_CODE,
        nullable=False,
        index=True,
    )
    # Fernet-encrypted Telethon StringSession — NULL when not connected
    encrypted_session: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(256), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"ConnectedAccount(id={self.id}, user_id={self.user_id}, "
            f"status={self.status.value})"
        )
