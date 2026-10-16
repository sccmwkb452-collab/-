"""Admin-configurable key-value settings stored in the database."""
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class BotSetting(Base):
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"BotSetting(key={self.key!r}, value={self.value!r})"
