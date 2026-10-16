from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(8))

    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships — импорты строкой, чтобы избежать циклов
    subscriptions: Mapped[list["Subscription"]] = relationship(  # noqa: F821
        back_populates="user", lazy="noload"
    )
    gifts: Mapped[list["Gift"]] = relationship(  # noqa: F821
        back_populates="owner", lazy="noload"
    )
    transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        back_populates="user", lazy="noload"
    )

    # ── Helpers ───────────────────────────────────────────────────────────────
    @property
    def full_name(self) -> str:
        parts = [self.first_name]
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts)

    @property
    def mention_html(self) -> str:
        return f'<a href="tg://user?id={self.telegram_id}">{self.full_name}</a>'

    @property
    def at_username(self) -> str:
        return f"@{self.username}" if self.username else self.full_name

    def __repr__(self) -> str:
        return f"User(id={self.id}, telegram_id={self.telegram_id}, username={self.username!r})"
