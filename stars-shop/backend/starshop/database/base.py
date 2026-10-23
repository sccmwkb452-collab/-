from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..shared.timeutil import utcnow

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

MONEY = sa.Numeric(14, 2)
RATE = sa.Numeric(14, 4)


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        datetime: sa.DateTime(timezone=True),
        dict: JSONB,
        dict[str, Any]: JSONB,
        list: JSONB,
        uuid.UUID: UUID(as_uuid=True),
    }


def str_enum(enum_cls: type[StrEnum], name: str) -> sa.Enum:
    """Store enums as VARCHAR + CHECK constraint (no native PG enum), so adding
    a status later is a plain migration."""
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now(), onupdate=utcnow, nullable=False)
