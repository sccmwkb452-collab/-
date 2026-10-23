import type { OrderStatus } from "./types";

export type StatusTone = "neutral" | "warning" | "info" | "success" | "danger" | "violet";

export const STATUS_META: Record<OrderStatus, { label: string; tone: StatusTone; hint: string }> = {
  created: { label: "Создан", tone: "neutral", hint: "Заказ оформлен, выберите способ оплаты" },
  pending_payment: { label: "Ожидает оплаты", tone: "warning", hint: "Ждём подтверждение оплаты от провайдера" },
  paid: { label: "Оплачен", tone: "info", hint: "Оплата подтверждена, заказ передаётся на доставку" },
  processing: { label: "В обработке", tone: "info", hint: "Звёзды отправляются получателю" },
  completed: { label: "Выполнен", tone: "success", hint: "Звёзды зачислены получателю" },
  failed: { label: "Требует внимания", tone: "danger", hint: "Мы разбираемся с заказом и свяжемся с вами" },
  refund_pending: { label: "Оформляется возврат", tone: "violet", hint: "Возврат передан платёжному провайдеру" },
  refunded: { label: "Возврат выполнен", tone: "violet", hint: "Деньги возвращены тем же способом оплаты" },
  cancelled: { label: "Отменён", tone: "neutral", hint: "Заказ не был оплачен" },
};

export const ORDER_FILTERS = [
  { id: "all", label: "Все" },
  { id: "pending", label: "Ожидают оплаты" },
  { id: "processing", label: "В обработке" },
  { id: "completed", label: "Выполнены" },
  { id: "closed", label: "Отменены и возвраты" },
] as const;

export type OrderFilter = (typeof ORDER_FILTERS)[number]["id"];

export const ACTIVE_STATUSES: OrderStatus[] = ["created", "pending_payment", "paid", "processing"];
