import enum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class GiftRarity(str, enum.Enum):
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class GiftStatus(str, enum.Enum):
    OWNED = "owned"
    TRANSFERRED = "transferred"
    BURNED = "burned"


class Gift(Base):
    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Telegram NFT Gift данные
    telegram_gift_id: Mapped[str | None] = mapped_column(String(256), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(512))
    sticker_file_id: Mapped[str | None] = mapped_column(String(256))

    rarity: Mapped[GiftRarity] = mapped_column(
        Enum(GiftRarity), default=GiftRarity.COMMON, nullable=False
    )
    status: Mapped[GiftStatus] = mapped_column(
        Enum(GiftStatus), default=GiftStatus.OWNED, nullable=False, index=True
    )

    is_transferable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_limited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_supply: Mapped[int | None] = mapped_column(Integer)
    serial_number: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    owner: Mapped["User | None"] = relationship(back_populates="gifts")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"Gift(id={self.id}, name={self.name!r}, "
            f"rarity={self.rarity.value}, status={self.status.value})"
        )
