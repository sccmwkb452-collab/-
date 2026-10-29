"""Модели базы данных.

Типы подобраны так, чтобы схема работала и в PostgreSQL (прод), и в SQLite (тесты).
Деньги — только Numeric/Decimal, никаких float.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

MONEY = Numeric(36, 9)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Всегда отдаёт aware-UTC datetime (SQLite хранит без зоны, PostgreSQL — с зоной)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )


# ─── Владельцы и настройки ────────────────────────────────────────────────────


class Owner(TimestampMixin, Base):
    """Пользователь панели — владелец бизнес-аккаунта."""

    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64))

    agent_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(16), default="ru")
    ai_effort: Mapped[str | None] = mapped_column(String(16))
    style_notes: Mapped[str] = mapped_column(Text, default="")
    # Сколько минут агент молчит в диалоге после ручного сообщения владельца.
    owner_pause_minutes: Mapped[int] = mapped_column(Integer, default=30)

    # Приватность
    store_history: Mapped[bool] = mapped_column(Boolean, default=True)
    history_retention_days: Mapped[int] = mapped_column(Integer, default=90)
    store_media_files: Mapped[bool] = mapped_column(Boolean, default=False)

    # Обращения
    outreach_requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    outreach_daily_limit: Mapped[int] = mapped_column(Integer, default=20)
    outreach_min_interval_seconds: Mapped[int] = mapped_column(Integer, default=120)
    recontact_cooldown_days: Mapped[int] = mapped_column(Integer, default=30)

    takeover_command: Mapped[str] = mapped_column(String(64), default="сутпасмотри")


class BusinessConnectionRecord(TimestampMixin, Base):
    __tablename__ = "business_connections"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # business_connection_id
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_chat_id: Mapped[int] = mapped_column(BigInteger)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False)  # владелец есть в списке допуска
    rights: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def right(self, name: str) -> bool:
        return bool((self.rights or {}).get(name))


# ─── Контакты и диалоги ───────────────────────────────────────────────────────


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("owner_id", "telegram_user_id", name="uq_contact_tg"),
        UniqueConstraint("owner_id", "username", name="uq_contact_username"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(64))  # в нижнем регистре, без @
    display_name: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(64), default="incoming")
    # Только то, что пришло из источника (парсер/импорт/Telegram), без домыслов.
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    opted_out_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    first_contacted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_contacted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    contact_attempts: Mapped[int] = mapped_column(Integer, default=0)
    has_replied: Mapped[bool] = mapped_column(Boolean, default=False)


class ConversationMode(StrEnum):
    AUTO = "auto"  # агент отвечает сам
    MANUAL = "manual"  # «сутпасмотри»: только человек
    REVIEW = "review"  # агент передал диалог человеку и ждёт


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("business_connection_id", "chat_id", name="uq_conv_chat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    business_connection_id: Mapped[str] = mapped_column(String(128), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)

    mode: Mapped[str] = mapped_column(String(16), default=ConversationMode.AUTO)
    mode_reason: Mapped[str | None] = mapped_column(Text)
    # Структурированное состояние сделки (см. app.ai.state.DealState).
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    initial_message_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    last_inbound_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_outbound_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_owner_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    contact: Mapped[Contact] = relationship(lazy="joined")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    # contact — собеседник, owner — владелец вручную, agent — наш бот
    sender: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text, default="")
    media: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)


# ─── Шаблоны первого сообщения ────────────────────────────────────────────────


class InitialTemplate(TimestampMixin, Base):
    __tablename__ = "initial_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(128), default="Основной")
    text: Mapped[str] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    # Можно ли агенту адаптировать текст под доступный контекст контакта.
    allow_adaptation: Mapped[bool] = mapped_column(Boolean, default=True)


# ─── Парсеры и обращения ──────────────────────────────────────────────────────


class ParserConfig(TimestampMixin, Base):
    __tablename__ = "parsers"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_parser_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    adapter: Mapped[str] = mapped_column(String(32))  # ключ из app.parsers.registry
    resource: Mapped[str] = mapped_column(Text, default="")  # username / ссылка / URL API
    target_role: Mapped[str] = mapped_column(String(16), default="seller")  # seller|buyer|any
    keywords: Mapped[list[Any]] = mapped_column(JSON, default=list)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    geo: Mapped[str | None] = mapped_column(String(128))
    # {"price": {"min": "1", "max": "100"}, "rarity": {"max": "1.5"}, ...}
    ranges: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    daily_contact_limit: Mapped[int] = mapped_column(Integer, default=10)
    total_contact_limit: Mapped[int] = mapped_column(Integer, default=100)
    # {"max_results": 200, "stop_after_matches": 50}
    stop_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="new")
    last_error: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Данные файла импорта (для file_import), уже разобранные в строки.
    import_rows: Mapped[list[Any] | None] = mapped_column(JSON)


class SearchResult(Base):
    __tablename__ = "search_results"
    __table_args__ = (UniqueConstraint("parser_id", "external_id", name="uq_result_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    parser_id: Mapped[int] = mapped_column(ForeignKey("parsers.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    decision: Mapped[str] = mapped_column(String(32))  # queued | rejected | duplicate | opted_out | limit
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class OutreachStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    MANUAL_REQUIRED = "manual_required"  # Telegram не даёт написать первым — нужен человек
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutreachTask(TimestampMixin, Base):
    __tablename__ = "outreach_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    parser_id: Mapped[int | None] = mapped_column(ForeignKey("parsers.id", ondelete="SET NULL"))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("initial_templates.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(32), default=OutreachStatus.PENDING_APPROVAL, index=True)
    prepared_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    sent_message_id: Mapped[int | None] = mapped_column(BigInteger)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    contact: Mapped[Contact] = relationship(lazy="joined")


# ─── Торговые боты, политика и сделки ─────────────────────────────────────────


class TradeBotConfig(TimestampMixin, Base):
    """Разрешённая торговая интеграция. Активной может быть только одна на владельца."""

    __tablename__ = "trade_bots"
    __table_args__ = (UniqueConstraint("owner_id", "bot_user_id", name="uq_trade_bot_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    adapter: Mapped[str] = mapped_column(String(32))  # cryptopay | manual
    bot_username: Mapped[str] = mapped_column(String(64))  # без @, нижний регистр
    # Числовой ID бота, полученный через официальную кнопку выбора бота (request_users).
    bot_user_id: Mapped[int] = mapped_column(BigInteger)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    currencies: Mapped[list[Any]] = mapped_column(JSON, default=list)  # разрешённые владельцем
    payment_methods: Mapped[list[Any]] = mapped_column(JSON, default=list)
    capabilities: Mapped[list[Any]] = mapped_column(JSON, default=list)  # результат последней проверки
    supported_currencies: Mapped[list[Any]] = mapped_column(JSON, default=list)
    fee_percent: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    fee_fixed: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))

    status: Mapped[str] = mapped_column(String(32), default="unchecked")  # ok | unavailable | unchecked
    last_check_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)


class TradingPolicy(TimestampMixin, Base):
    __tablename__ = "trading_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), unique=True)

    require_user_confirmation: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_mode_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_pay_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_categories: Mapped[list[Any]] = mapped_column(JSON, default=list)
    auto_currencies: Mapped[list[Any]] = mapped_column(JSON, default=list)
    auto_allowed_sellers: Mapped[list[Any]] = mapped_column(JSON, default=list)  # telegram id
    auto_max_price: Mapped[Decimal | None] = mapped_column(MONEY)
    max_deal_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    daily_budget: Mapped[Decimal | None] = mapped_column(MONEY)
    budget_currency: Mapped[str | None] = mapped_column(String(16))
    max_concurrent_deals: Mapped[int] = mapped_column(Integer, default=3)
    repeat_purchase_cooldown_hours: Mapped[int] = mapped_column(Integer, default=24)


class DealStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    CREATING = "creating"
    CREATED = "created"  # сделка/счёт создан в торговом боте
    USER_ACTION_REQUIRED = "user_action_required"  # шаг нужно сделать человеку в торговом боте
    PAYING = "paying"
    PAID = "paid"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    UNKNOWN = "unknown"  # результат операции неизвестен — нужна сверка, не повтор


ACTIVE_DEAL_STATUSES = {
    DealStatus.AWAITING_CONFIRMATION,
    DealStatus.CONFIRMED,
    DealStatus.CREATING,
    DealStatus.CREATED,
    DealStatus.USER_ACTION_REQUIRED,
    DealStatus.PAYING,
    DealStatus.PAID,
    DealStatus.UNKNOWN,
}
# Сделки, деньги по которым считаются потраченными (или могли быть потрачены).
BUDGET_DEAL_STATUSES = {DealStatus.PAYING, DealStatus.PAID, DealStatus.COMPLETED, DealStatus.UNKNOWN}


class Deal(TimestampMixin, Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    trade_bot_id: Mapped[int | None] = mapped_column(ForeignKey("trade_bots.id", ondelete="SET NULL"))
    # Снимок идентичности торгового бота на момент создания — сверяется перед каждым шагом.
    trade_bot_user_id: Mapped[int | None] = mapped_column(BigInteger)
    trade_bot_username: Mapped[str | None] = mapped_column(String(64))

    side: Mapped[str] = mapped_column(String(8), default="buy")  # buy — платим продавцу, sell — выставляем счёт
    product_type: Mapped[str | None] = mapped_column(String(64))
    item: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(16))
    fees: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(MONEY)
    counterparty_telegram_id: Mapped[int | None] = mapped_column(BigInteger)

    status: Mapped[str] = mapped_column(String(32), default=DealStatus.DRAFT, index=True)
    created_by: Mapped[str] = mapped_column(String(8), default="user")  # user | auto
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    payment_spend_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    external_deal_id: Mapped[str | None] = mapped_column(String(128))
    external_url: Mapped[str | None] = mapped_column(Text)
    # Когда деньги начали списываться (вход в PAYING) — по нему считается дневной бюджет.
    funds_committed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)


class DealEvent(Base):
    __tablename__ = "deal_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


# ─── Рынок NFT / подарков ─────────────────────────────────────────────────────


class MarketPrice(Base):
    """Наблюдение цены: floor, продажа или листинг. Только реальные данные с источником и временем."""

    __tablename__ = "market_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    collection: Mapped[str] = mapped_column(String(128), index=True)  # slug, напр. PlushPepe
    kind: Mapped[str] = mapped_column(String(16))  # floor | sale | listing
    model: Mapped[str | None] = mapped_column(String(128))
    backdrop: Mapped[str | None] = mapped_column(String(128))
    symbol: Mapped[str | None] = mapped_column(String(128))
    price: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(128))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("source_currency", "target_currency", "provider", name="uq_rate"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_currency: Mapped[str] = mapped_column(String(16))
    target_currency: Mapped[str] = mapped_column(String(16))
    rate: Mapped[Decimal] = mapped_column(MONEY)
    provider: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


# ─── Медиа-библиотека ─────────────────────────────────────────────────────────


class MediaItem(TimestampMixin, Base):
    """Стикеры/GIF/фото, которые агенту разрешено отправлять, и образцы для сравнения."""

    __tablename__ = "media_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # sticker | animation | photo | video
    file_id: Mapped[str] = mapped_column(Text)
    file_unique_id: Mapped[str] = mapped_column(String(128))
    # mood — когда уместно отправить: greeting | thanks | agree | thinking | deal_done | none
    mood: Mapped[str] = mapped_column(String(32), default="none")
    purpose: Mapped[str] = mapped_column(String(16), default="send")  # send | reference
    description: Mapped[str] = mapped_column(Text, default="")
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    stored_path: Mapped[str | None] = mapped_column(Text)


# ─── Память ИИ: глобальные инструкции администратора ──────────────────────────


class AIConfigVersion(Base):
    """Версия глобальной конфигурации ИИ. Активна ровно одна; откат создаёт новую версию."""

    __tablename__ = "ai_config_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    instructions: Mapped[str] = mapped_column(Text, default="")
    style: Mapped[str] = mapped_column(Text, default="")
    negotiation_rules: Mapped[str] = mapped_column(Text, default="")
    trading_rules: Mapped[str] = mapped_column(Text, default="")
    # [{"situation": ..., "good": ..., "bad": ...}]
    examples: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_by: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str] = mapped_column(Text, default="")
    based_on_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class PendingInstruction(Base):
    __tablename__ = "pending_instructions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger)
    source_kinds: Mapped[list[Any]] = mapped_column(JSON, default=list)
    analysis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | applied | rejected
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AdminMaterial(Base):
    __tablename__ = "admin_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger)
    pending_instruction_id: Mapped[int | None] = mapped_column(ForeignKey("pending_instructions.id"))
    kind: Mapped[str] = mapped_column(String(16))
    file_id: Mapped[str | None] = mapped_column(Text)
    file_unique_id: Mapped[str | None] = mapped_column(String(128))
    stored_path: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, default="")
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


# ─── Журнал и служебное ───────────────────────────────────────────────────────


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, index=True)
    actor: Mapped[str] = mapped_column(String(32), default="agent")  # agent | user | admin | system
    action: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer)
    parser: Mapped[str | None] = mapped_column(String(64))
    trade_bot: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(16))  # ok | error | blocked | skipped | unknown
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ProcessedUpdate(Base):
    """Защита от повторной обработки одного и того же обновления Telegram."""

    __tablename__ = "processed_updates"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
