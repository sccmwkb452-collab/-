/** API contract shared by the Mini App and the admin panel. Money values
 * are decimal strings ("169.00") — never parse them into floats for math. */

export type OrderStatus =
  | "created"
  | "pending_payment"
  | "paid"
  | "processing"
  | "completed"
  | "failed"
  | "refund_pending"
  | "refunded"
  | "cancelled"
  | "lost";

export type OrderKind = "regular" | "lucky";

export type ShopMode = "demo" | "production";

export interface Brand {
  name: string;
  tagline: string;
  logo_url: string | null;
  accent_primary: string;
  accent_secondary: string;
  accent_tertiary: string;
}

export interface InfoItem {
  icon: string;
  title: string;
  text: string;
}

export interface FaqItem {
  q: string;
  a: string;
}

export interface Announcement {
  id: string;
  text: string;
  tone: "info" | "success" | "warning";
  link: string | null;
  active: boolean;
}

export interface PromoBanner {
  id: string;
  title: string;
  subtitle: string;
  cta_label: string | null;
  link: string | null;
  accent: string;
  active: boolean;
}

export interface Content {
  hero: { eyebrow: string; title: string; subtitle: string; cta_label: string; benefits: string[] };
  catalog_title: string;
  catalog_subtitle: string;
  how_it_works: InfoItem[];
  why_us: InfoItem[];
  faq: FaqItem[];
  support: { telegram: string; email: string; hours: string; response_time: string };
  legal: { terms: string; refund_policy: string; payment_info: string };
  announcements: Announcement[];
  promo_banners: PromoBanner[];
}

export interface Product {
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
}

export interface PaymentMethod {
  id: string;
  title: string;
  description: string;
  is_demo: boolean;
  fee_percent: string;
}

export interface Bootstrap {
  brand: Brand;
  mode: ShopMode;
  maintenance: { enabled: boolean; message: string };
  currency: string;
  timezone: string;
  content: Content;
  payment_methods: PaymentMethod[];
  delivery: {
    provider: string;
    is_demo: boolean;
    min_stars: number;
    max_stars: number;
    gifts_enabled: boolean;
    requires_username: boolean;
  };
  referral: { enabled: boolean; max_bonus_spend_percent: string };
  /** Lucky Buy: whole-percent chance range and the extra fee, percent. */
  lucky: { available: boolean; min_chance: number; max_chance: number; fee_percent: string };
  bot_username: string | null;
  catalog: Product[];
}

export interface OrderSummary {
  id: string;
  number: string;
  kind: OrderKind;
  status: OrderStatus;
  status_label: string;
  created_at: string;
  stars_amount: number;
  total: string;
  currency: string;
  recipient: { type: "self" | "username"; masked: string; username?: string | null; name?: string | null };
  payment_provider: string;
  payment_method: string;
  mode: ShopMode;
}

export interface PaymentInfo {
  id: string;
  provider: string;
  status: string;
  amount: string;
  currency: string;
  pay_url: string | null;
  pay_url_kind: "telegram" | "external" | "internal" | null;
  expires_at: string | null;
  is_demo: boolean;
}

export interface OrderDetail extends OrderSummary {
  updated_at: string;
  paid_at: string | null;
  completed_at: string | null;
  expires_at: string | null;
  amounts: {
    unit_price: string;
    subtotal: string;
    discount: string;
    bonus_spent: string;
    fee: string;
    total: string;
    currency: string;
  };
  can_pay: boolean;
  can_cancel: boolean;
  payment: PaymentInfo | null;
  timeline: { type: string; status: OrderStatus | null; message: string | null; at: string }[];
  delivery: { status: "in_progress" | "delivered" | "failed" | "cancelled" } | null;
  problem: boolean;
  lucky: LuckyDraw | null;
}

/** Lucky Buy attempt. ``server_seed``, ``roll`` and ``won`` stay null until the draw. */
export interface LuckyDraw {
  chance: string;
  chance_bp: number;
  prize_value: string;
  server_seed_hash: string;
  client_seed: string | null;
  nonce: string;
  server_seed: string | null;
  roll: string | null;
  roll_bp: number | null;
  won: boolean | null;
  drawn_at: string | null;
}

export interface Quote {
  product_id: number;
  stars_amount: number;
  unit_price: string;
  subtotal: string;
  discount: string;
  bonus_spent: string;
  bonus_available: string;
  fee: string;
  total: string;
  currency: string;
  promo: { code: string; valid: boolean; error?: string; message?: string } | null;
  lucky?: { chance: string; chance_bp: number; prize_value: string; fee_percent: string };
}

export interface Me {
  user: {
    telegram_id: number;
    username: string | null;
    first_name: string;
    last_name: string | null;
    photo_url: string | null;
    is_premium: boolean;
    first_seen_at: string;
    is_blocked: boolean;
  };
  stats: { orders_count: number; completed_count: number; total_spent: string; last_order: OrderSummary | null };
  bonus: {
    balance: string;
    referral_enabled: boolean;
    referral_code: string | null;
    referral_link: string | null;
    invited: number;
    rewarded: number;
    reward_kind: "percent" | "fixed";
    reward_value: string;
  };
}

export interface Ticket {
  id: number;
  subject: string;
  status: "open" | "answered" | "closed";
  order_id: string | null;
  created_at: string;
  last_message_at: string;
  messages?: { id: number; author: "user" | "admin" | "system"; text: string; at: string }[];
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown; request_id?: string };
}
