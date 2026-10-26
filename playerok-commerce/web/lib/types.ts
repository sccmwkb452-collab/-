export type Paged<T> = { items: T[]; total: number; page: number; per_page: number };

export type KillSwitch = { active: boolean; reason: string; at: string | null; by: string | null };

export type Metrics = {
  period: { code: string; label: string; from: string; to: string };
  include_test: boolean;
  orders: number;
  completed: number;
  cancelled: number;
  refunds: number;
  disputes: number;
  reviews: number;
  avg_review_rating: string | null;
  shop_rating: string | null;
  shop_rating_note: string;
  revenue: string;
  purchase_costs: string;
  fees: string;
  refunds_amount: string;
  net_profit: string;
  net_profit_known: string;
  orders_without_cost: number;
  margin_pct: string | null;
  avg_check: string | null;
  avg_processing_minutes: number | null;
  conversion: string | null;
  conversion_note: string;
  automation_ops: Record<string, number>;
  auto_ready_share: string | null;
  integration_errors: number;
};

export type SeriesPoint = { day: string; revenue: string; net_profit: string; orders: number };

export type SyncRow = {
  source: string;
  kind: string;
  status: string;
  received: number;
  saved: number;
  errors: number;
  errors_today: number;
  message: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type Capability = { label: string; available: boolean; reason: string };
export type Integration = { adapter: string; title: string; capabilities: Record<string, Capability> };

export type Category = {
  id: number;
  code: string;
  name: string;
  group: string;
  marketplace_commission_pct: string | null;
  commission_source: string | null;
  compliance_status: string;
  compliance_label: string;
  compliance_note: string | null;
  dispute_risk_pct: string | null;
  auto_delivery_possible: boolean;
};

export type Pricing = {
  status: string;
  status_label: string;
  current_price: string | null;
  min_price: string | null;
  recommended_price: string | null;
  full_cost: string | null;
  expected_profit: string | null;
  expected_margin_pct: string | null;
  notes: string[];
  priced_at: string | null;
};

export type Product = {
  id: number;
  sku: string;
  name: string;
  category: { id: number; code: string; name: string; group: string };
  description: string;
  region: string;
  face_value: string | null;
  face_currency: string | null;
  delivery_type: string;
  delivery_time: string;
  activation_notes: string;
  buyer_instructions: string;
  required_buyer_data: string;
  status: string;
  compliance_status: string;
  compliance_label: string;
  supplier_product_id: number | null;
  supplier_quantity: number;
  manual_unit_cost: string | null;
  auto_purchase_allowed: boolean;
  image_template: string | null;
  pricing: Pricing;
  stock: Record<string, number> | null;
  version: number;
  updated_at: string | null;
};

export type Evaluation = {
  price: string;
  marketplace_fee: string;
  payment_fee: string;
  refund_reserve: string;
  withdrawal_fee: string;
  sale_costs: string;
  gross_profit: string;
  net_profit: string;
  margin_pct: string;
  roi_pct: string;
  meets_guards: boolean;
  violations: string[];
};

export type Calculation = {
  status: string;
  can_sell: boolean;
  breakdown: {
    purchase_rub: string;
    supplier_fee_rub: string;
    conversion_rub: string;
    other_costs_rub: string;
    full_cost: string;
    sale_rate_pct: string;
  } | null;
  min_price: string | null;
  target_price: string | null;
  recommended_price: string | null;
  competitive_price: string | null;
  current: Evaluation | null;
  recommended: Evaluation | null;
  notes: string[];
};

export type SupplierProduct = {
  id: number;
  supplier_id: number;
  supplier: string;
  external_id: string;
  name: string;
  category: string | null;
  price: string | null;
  price_unit: number;
  currency: string;
  min_quantity: number | null;
  max_quantity: number | null;
  region: string | null;
  available: boolean;
  compliance_status: string;
  compliance_label: string;
  last_seen_at: string | null;
  price_changed_at: string | null;
};

export type Snapshot = {
  id: number;
  source: string;
  competitor_min: string | null;
  competitor_median: string | null;
  competitor_max: string | null;
  offers_count: number | null;
  note: string | null;
  observed_at: string;
  recorded_by: string | null;
};

export type ProductDetail = Product & {
  category_full: Category;
  calculation: Calculation;
  cost_source: string;
  cost_currency: string | null;
  fx_rate: string | null;
  policy: Record<string, string>;
  supplier_product: SupplierProduct | null;
  observations: Snapshot[];
  research: { total_score: string; confidence: string; factors: Record<string, unknown>; computed_at: string } | null;
  price_dynamics: {
    purchase: { at: string; price: string; currency: string; price_rub: string | null }[];
    sale: { at: string; price: string | null }[];
  };
};

export type OrderItem = {
  id: number;
  product_id: number;
  product: string;
  sku: string;
  delivery_type: string;
  quantity: number;
  unit_price: string;
  unit_cost: string | null;
  fulfilled_quantity: number;
  listing_id: number | null;
};

export type Order = {
  id: number;
  number: string;
  external_id: string | null;
  marketplace: string;
  source: string;
  buyer_name: string | null;
  status: string;
  status_label: string;
  status_reason: string | null;
  needs_attention: boolean;
  automation_paused: boolean;
  total_amount: string;
  marketplace_fee: string | null;
  cost_total: string | null;
  net_profit: string | null;
  is_test: boolean;
  placed_at: string | null;
  delivered_at: string | null;
  completed_at: string | null;
  items: OrderItem[];
  buyer_data?: Record<string, unknown>;
  notes?: string | null;
  review_received_at?: string | null;
  buyer_confirmed_at?: string | null;
};

export type Code = { id: number; mask: string; status: string; is_test: boolean; revealed_count: number; issued_at: string | null };

export type SupplierOrder = {
  id: number;
  supplier_id: number;
  status: string;
  external_id: string | null;
  quantity: number;
  cost: string | null;
  currency: string | null;
  cost_rub: string | null;
  is_test: boolean;
  last_error: string | null;
  message: string | null;
  created_at: string;
};

export type Message = {
  id: number;
  order_id: number | null;
  buyer_name: string | null;
  direction: string;
  text: string;
  status: string;
  source: string;
  suggested_reply: string | null;
  problem_hint: string | null;
  matched_rule_id: number | null;
  handled_by: string | null;
  handled_at: string | null;
  received_at: string;
};

export type Review = { id: number; order_id: number | null; rating: number | null; text: string; sentiment: string; created_at: string };

export type Listing = {
  id: number;
  product_id: number;
  product: string;
  marketplace: string;
  external_id: string | null;
  external_url: string | null;
  marketplace_category: string | null;
  title: string;
  description: string;
  price: string;
  quantity: number;
  status: string;
  status_label: string;
  status_reason: string | null;
  version: number;
  preview_confirmed_at: string | null;
  published_at: string | null;
  relist_on_complete: boolean;
  auto_created: boolean;
  min_price: string | null;
  recommended_price: string | null;
  updated_at: string | null;
};

export type ExportPayload = { title: string; description: string; price: string; quantity: number; category: string; image: string | null };

export type ListingDetail = Listing & {
  export: ExportPayload;
  images: { id: number; template: string; version: number; url: string }[];
  history: { version: number; action: string; actor: string | null; at: string; snapshot: Record<string, unknown> }[];
};

export type CredentialField = { name: string; label: string; secret: boolean; help: string; env: string; source: string | null; preview: string };

export type Supplier = {
  id: number;
  code: string;
  name: string;
  website: string | null;
  adapter: string;
  adapter_title: string;
  adapter_description: string;
  capabilities: Record<string, boolean>;
  categories: string[];
  integration_method: string | null;
  status: string;
  status_label: string;
  status_reason: string | null;
  purchase_mode: string;
  purchase_mode_label: string;
  currency: string;
  balance: string | null;
  balance_currency: string | null;
  balance_checked_at: string | null;
  max_single_purchase: string;
  daily_limit: string;
  max_operations_per_day: number;
  fee_pct: string;
  fee_fixed: string;
  refund_policy: string | null;
  policy_note: string | null;
  verification: { facts?: string[]; unverified?: string[]; sources?: string[]; checked_at?: string } | null;
  last_check_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  success_count: number;
  error_count: number;
  spent_today_rub?: string;
  operations_today?: number;
  products_count?: number;
  credentials?: CredentialField[];
  orders?: SupplierOrder[];
};

export type AuditEntry = {
  id: number;
  actor_type: string;
  actor: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  ip: string | null;
  details: Record<string, unknown>;
  created_at: string;
};

export type AutomationEntry = { id: number; feature: string; action: string; result: string; message: string | null; order_id: number | null; created_at: string };

export type Notification = {
  id: number;
  kind: string;
  severity: string;
  title: string;
  body: string;
  status: string;
  attempts: number;
  last_error: string | null;
  entity_type: string | null;
  entity_id: string | null;
  created_at: string;
  sent_at: string | null;
};

export type AutoIntegration = { state: "available" | "assist" | "unavailable"; label: string; reason: string; assist?: string; missing: string[] };

export type AutoItem = {
  code: string;
  label: string;
  emoji: string;
  title: string;
  enabled: boolean;
  stopped: boolean;
  integration: AutoIntegration;
  updated_at: string | null;
};

export type AutoField = {
  name: string;
  label: string;
  type: string;
  help: string;
  choices: [string, string][];
  min: number | null;
  max: number | null;
};

export type AutoDetail = Omit<AutoItem, "emoji"> & {
  description: string;
  safety: string;
  config: Record<string, unknown>;
  defaults: Record<string, unknown>;
  fields: AutoField[];
  variables: Record<string, string>;
  updated_by: string | null;
  last_run_at: string | null;
  last_error: string | null;
  history: { at: string; action: string; result: string; message: string | null; order_id: number | null }[];
};
