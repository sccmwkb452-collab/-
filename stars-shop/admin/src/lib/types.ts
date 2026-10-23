import type { LuckyDraw, OrderKind, OrderStatus } from "@starshop/shared";

export type Role = "owner" | "manager" | "support";

export interface Admin {
  id: number;
  telegram_id: number;
  username: string | null;
  display_name: string | null;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
}

export interface AdminOrder {
  id: string;
  number: string;
  kind: OrderKind;
  status: OrderStatus;
  status_label: string;
  created_at: string;
  stars_amount: number;
  total: string;
  currency: string;
  mode: "demo" | "production";
  payment_provider: string;
  payment_method: string;
  user_id: number;
  user: { telegram_id: number; username: string | null; display_name: string } | null;
  recipient: { type: "self" | "username"; username: string | null; telegram_id: number | null; name: string | null };
  product_id: number | null;
  product_kind: string;
  unit_price: string;
  subtotal: string;
  discount: string;
  bonus_spent: string;
  fee: string;
  cost: string | null;
  delivery_provider: string;
  promo_code_id: number | null;
  failure_reason: string | null;
  paid_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  refunded_at: string | null;
  expires_at: string | null;
}

export interface AdminPayment {
  id: string;
  provider: string;
  status: string;
  amount: string;
  currency: string;
  provider_payment_id: string | null;
  paid_amount: string | null;
  paid_asset: string | null;
  is_duplicate: boolean;
  is_demo: boolean;
  confirmed_at: string | null;
  refunded_at: string | null;
  refund_reference: string | null;
  refund_reason: string | null;
  refund_attempts: number;
  last_error: string | null;
  created_at: string;
  pay_url: string | null;
}

export interface AdminTask {
  id: string;
  provider: string;
  status: string;
  attempts: number;
  max_attempts: number;
  external_id: string | null;
  next_attempt_at: string | null;
  last_error: string | null;
  result: Record<string, unknown> | null;
  completed_at: string | null;
}

export interface AdminEvent {
  id: number;
  type: string;
  from_status: string | null;
  to_status: string | null;
  message: string | null;
  actor_type: string;
  actor_id: string | null;
  is_public: boolean;
  data: Record<string, unknown> | null;
  at: string;
}

export interface OrderView {
  order: AdminOrder;
  payments: AdminPayment[];
  delivery: AdminTask | null;
  lucky: LuckyDraw | null;
  events: AdminEvent[];
  webhooks: { id: number; provider: string; event_id: string | null; type: string | null; status: string; error: string | null; received_at: string }[];
  actions: string[];
}

export interface AdminProduct {
  id: number;
  kind: "package" | "custom";
  title: string | null;
  badge: string | null;
  stars_amount: number | null;
  price: string | null;
  price_per_star: string | null;
  min_stars: number | null;
  max_stars: number | null;
  is_popular: boolean;
  is_active: boolean;
  is_archived: boolean;
  sort_order: number;
  cost_per_star: string | null;
  cost_source: string | null;
  cost_updated_at: string | null;
}

export interface AdminUserRow {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string;
  last_name: string | null;
  display_name: string;
  photo_url: string | null;
  is_premium: boolean;
  bot_started: boolean;
  is_blocked: boolean;
  blocked_reason: string | null;
  bonus_balance: string;
  referral_code: string;
  referred_by_id: number | null;
  first_seen_at: string;
  last_seen_at: string;
}

export interface Promo {
  id: number;
  code: string;
  description: string | null;
  kind: "percent" | "fixed";
  value: string;
  max_discount: string | null;
  min_order_amount: string | null;
  starts_at: string | null;
  expires_at: string | null;
  max_uses: number | null;
  per_user_limit: number;
  first_order_only: boolean;
  is_active: boolean;
  used: number;
}

export interface AuditRow {
  id: number;
  admin_id: number | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  summary: string | null;
  before: unknown;
  after: unknown;
  ip: string | null;
  at: string;
}
