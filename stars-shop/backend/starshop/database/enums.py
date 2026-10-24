from __future__ import annotations

from enum import StrEnum


class OrderStatus(StrEnum):
    created = "created"
    pending_payment = "pending_payment"
    paid = "paid"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    refund_pending = "refund_pending"
    refunded = "refunded"
    # Not paid and closed: cancelled by the user/admin or the payment window expired.
    cancelled = "cancelled"
    # Lucky Buy attempt paid and drawn without a win: closed, nothing to deliver.
    lost = "lost"


class OrderKind(StrEnum):
    regular = "regular"
    # Pay a share of the package price for the same chance to receive the package.
    lucky = "lucky"
    # Referral bonuses paid out as Stars to the user's own account.
    withdrawal = "withdrawal"


class ShopMode(StrEnum):
    demo = "demo"
    production = "production"


class RecipientType(StrEnum):
    self = "self"
    username = "username"


class ProductKind(StrEnum):
    package = "package"
    custom = "custom"
    # Telegram Premium subscription for 3, 6 or 12 months.
    premium = "premium"


class WithdrawalStatus(StrEnum):
    pending = "pending"  # bonuses are held, waits for an administrator
    approved = "approved"  # a Stars order was created and is being delivered
    rejected = "rejected"  # bonuses returned
    returned = "returned"  # delivery failed, bonuses returned


class PaymentStatus(StrEnum):
    created = "created"
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    expired = "expired"
    cancelled = "cancelled"
    refund_pending = "refund_pending"
    refunded = "refunded"


class WebhookStatus(StrEnum):
    received = "received"
    processed = "processed"
    ignored = "ignored"
    rejected = "rejected"
    failed = "failed"


class DeliveryStatus(StrEnum):
    queued = "queued"
    in_progress = "in_progress"
    waiting_provider = "waiting_provider"
    needs_attention = "needs_attention"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class PromoKind(StrEnum):
    percent = "percent"
    fixed = "fixed"


class PromoUsageStatus(StrEnum):
    reserved = "reserved"
    applied = "applied"
    released = "released"


class ReferralStatus(StrEnum):
    pending = "pending"
    rewarded = "rewarded"
    rejected = "rejected"
    reversed = "reversed"


class AdminRole(StrEnum):
    owner = "owner"
    manager = "manager"
    support = "support"


class ActorType(StrEnum):
    system = "system"
    user = "user"
    admin = "admin"
    provider = "provider"


class TicketStatus(StrEnum):
    open = "open"
    answered = "answered"
    closed = "closed"


class NotificationStatus(StrEnum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class BotButtonAction(StrEnum):
    message = "message"  # send the configured text
    webapp = "webapp"  # open a page of the Mini App
    url = "url"  # open an external https link
    section = "section"  # a section of the bot (buy, profile, orders, referrals, support)
    product = "product"  # information about a package with a "buy" button


class ButtonStyle(StrEnum):
    """Telegram button styles (Bot API): blue, green, red."""

    primary = "primary"
    success = "success"
    danger = "danger"
