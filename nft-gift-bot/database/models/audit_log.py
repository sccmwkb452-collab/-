"""Audit log — records all admin actions. Never stores sensitive data."""
from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"AuditLog(id={self.id}, admin={self.admin_telegram_id}, "
            f"action={self.action!r})"
        )
