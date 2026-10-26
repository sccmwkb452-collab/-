from __future__ import annotations

from enum import StrEnum


class RoleCode(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class ComplianceStatus(StrEnum):
    APPROVED = "approved"  # the owner confirmed the platform rules allow it
    NEEDS_REVIEW = "needs_review"  # automation and publishing are blocked until reviewed
    BLOCKED = "blocked"  # prohibited by the rules of the product's platform
    NO_LEGAL_SOURCE = "no_legal_source"  # no verified legal purchasing channel


class DeliveryType(StrEnum):
    CODE = "code"  # digital code / key / voucher from inventory or supplier
    SERVICE = "service"  # supplier performs a service (SMM order, top-up)
    MANUAL = "manual"  # operator delivers by hand


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class SupplierStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    CONNECTED = "connected"
    ERROR = "error"
    MONITOR_ONLY = "monitor_only"  # public prices only, no purchasing API
    BLOCKED_BY_POLICY = "blocked_by_policy"
    DISABLED = "disabled"


class PurchaseMode(StrEnum):
    MONITOR = "monitor"  # 1. price monitoring only
    MANUAL = "manual"  # 2. manual purchase from the panel
    CONFIRM = "confirm"  # 3. automatic after the owner confirms
    AUTO = "auto"  # 4. fully automatic for allowed products, within limits


class SupplierOrderStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"  # accepted by the supplier, in progress
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"  # timeout / unclear answer: never retried blindly
    CANCELLED = "cancelled"


class ListingStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"  # passed the checks, waiting for publication
    PUBLISHED = "published"
    PAUSED = "paused"
    ARCHIVED = "archived"
    ERROR = "error"
    BLOCKED = "blocked"  # stopped by a guard (margin, stale price, policy)


class OrderStatus(StrEnum):
    NEW = "new"
    PENDING_REVIEW = "pending_review"
    PENDING_PURCHASE = "pending_purchase"
    PENDING_CONFIRMATION = "pending_confirmation"
    PROCESSING = "processing"
    READY_FOR_DELIVERY = "ready_for_delivery"
    DELIVERED = "delivered"  # handed to the buyer, waiting for the buyer's confirmation
    COMPLETED = "completed"
    ERROR = "error"
    REFUND = "refund"
    DISPUTE = "dispute"
    CANCELLED = "cancelled"


class CodeStatus(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    ISSUED = "issued"
    VOID = "void"


class MessageDirection(StrEnum):
    INCOMING = "in"
    OUTGOING = "out"


class MessageStatus(StrEnum):
    NEW = "new"
    HANDLED = "handled"
    ESCALATED = "escalated"
    AUTO_REPLIED = "auto_replied"
    SUGGESTED = "suggested"  # a reply was prepared for the operator to send


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class TransactionKind(StrEnum):
    SALE = "sale"
    MARKETPLACE_FEE = "marketplace_fee"
    PURCHASE = "purchase"
    SUPPLIER_FEE = "supplier_fee"
    PAYMENT_FEE = "payment_fee"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"
    WITHDRAWAL = "withdrawal"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LogResult(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    ERROR = "error"
    SUGGESTED = "suggested"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SUPPRESSED = "suppressed"


class Severity(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    CRITICAL = "critical"


class SyncStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


ORDER_STATUS_LABELS: dict[OrderStatus, str] = {
    OrderStatus.NEW: "🆕 Новый",
    OrderStatus.PENDING_REVIEW: "🔍 Ожидает проверки",
    OrderStatus.PENDING_PURCHASE: "🛒 Ожидает закупки",
    OrderStatus.PENDING_CONFIRMATION: "✋ Ожидает подтверждения",
    OrderStatus.PROCESSING: "⚙️ В обработке",
    OrderStatus.READY_FOR_DELIVERY: "📦 Готов к выдаче",
    OrderStatus.DELIVERED: "📤 Выдан, ждёт подтверждения",
    OrderStatus.COMPLETED: "✅ Завершён",
    OrderStatus.ERROR: "⛔ Ошибка",
    OrderStatus.REFUND: "↩️ Возврат",
    OrderStatus.DISPUTE: "⚖️ Спор",
    OrderStatus.CANCELLED: "✖️ Отменён",
}

LISTING_STATUS_LABELS: dict[ListingStatus, str] = {
    ListingStatus.DRAFT: "📝 Черновик",
    ListingStatus.READY: "🟦 Готово к публикации",
    ListingStatus.PUBLISHED: "🟢 Опубликовано",
    ListingStatus.PAUSED: "⏸ Приостановлено",
    ListingStatus.ARCHIVED: "🗄 В архиве",
    ListingStatus.ERROR: "⛔ Ошибка",
    ListingStatus.BLOCKED: "🛑 Заблокировано",
}

SUPPLIER_STATUS_LABELS: dict[SupplierStatus, str] = {
    SupplierStatus.NOT_CONFIGURED: "⚪️ Не подключён",
    SupplierStatus.CONNECTED: "🟢 Подключён",
    SupplierStatus.ERROR: "🔴 Ошибка",
    SupplierStatus.MONITOR_ONLY: "👁 Только мониторинг цен",
    SupplierStatus.BLOCKED_BY_POLICY: "🛑 Заблокирован политикой",
    SupplierStatus.DISABLED: "⏸ Выключен",
}

PURCHASE_MODE_LABELS: dict[PurchaseMode, str] = {
    PurchaseMode.MONITOR: "Только мониторинг цен",
    PurchaseMode.MANUAL: "Ручная закупка",
    PurchaseMode.CONFIRM: "Авто после подтверждения",
    PurchaseMode.AUTO: "Полностью автоматически",
}

COMPLIANCE_LABELS: dict[ComplianceStatus, str] = {
    ComplianceStatus.APPROVED: "✅ Разрешено",
    ComplianceStatus.NEEDS_REVIEW: "🟡 Нужна проверка правил",
    ComplianceStatus.BLOCKED: "🛑 Запрещено правилами",
    ComplianceStatus.NO_LEGAL_SOURCE: "⛔ Нет легального канала",
}

CONFIDENCE_LABELS: dict[Confidence, str] = {
    Confidence.HIGH: "высокая",
    Confidence.MEDIUM: "средняя",
    Confidence.LOW: "низкая (косвенные признаки)",
    Confidence.NONE: "нет данных",
}
