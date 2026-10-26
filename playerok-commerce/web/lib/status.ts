import type { Tone } from "@/components/ui/badge";

type StatusInfo = { label: string; tone: Tone };

/** Web labels for backend enums (the bot labels carry emoji; the panel uses icons). */
export const ORDER_STATUS: Record<string, StatusInfo> = {
  new: { label: "Новый", tone: "info" },
  pending_review: { label: "Ожидает проверки", tone: "warning" },
  pending_purchase: { label: "Ожидает закупки", tone: "warning" },
  pending_confirmation: { label: "Ожидает подтверждения", tone: "warning" },
  processing: { label: "В обработке", tone: "accent" },
  ready_for_delivery: { label: "Готов к выдаче", tone: "info" },
  delivered: { label: "Выдан, ждёт подтверждения", tone: "accent" },
  completed: { label: "Завершён", tone: "success" },
  error: { label: "Ошибка", tone: "danger" },
  refund: { label: "Возврат", tone: "neutral" },
  dispute: { label: "Спор", tone: "danger" },
  cancelled: { label: "Отменён", tone: "neutral" },
};

export const LISTING_STATUS: Record<string, StatusInfo> = {
  draft: { label: "Черновик", tone: "neutral" },
  ready: { label: "Готово к публикации", tone: "info" },
  published: { label: "Опубликовано", tone: "success" },
  paused: { label: "Приостановлено", tone: "warning" },
  archived: { label: "В архиве", tone: "neutral" },
  error: { label: "Ошибка", tone: "danger" },
  blocked: { label: "Заблокировано", tone: "danger" },
};

export const PRODUCT_STATUS: Record<string, StatusInfo> = {
  draft: { label: "Черновик", tone: "neutral" },
  active: { label: "Активен", tone: "success" },
  paused: { label: "Пауза", tone: "warning" },
  archived: { label: "Архив", tone: "neutral" },
};

export const COMPLIANCE: Record<string, StatusInfo> = {
  approved: { label: "Разрешено", tone: "success" },
  needs_review: { label: "Нужна проверка", tone: "warning" },
  blocked: { label: "Запрещено правилами", tone: "danger" },
  no_legal_source: { label: "Нет легального источника", tone: "danger" },
};

export const SUPPLIER_STATUS: Record<string, StatusInfo> = {
  not_configured: { label: "Не подключён", tone: "neutral" },
  connected: { label: "Подключён", tone: "success" },
  error: { label: "Ошибка", tone: "danger" },
  monitor_only: { label: "Только мониторинг цен", tone: "info" },
  blocked_by_policy: { label: "Заблокирован правилами", tone: "danger" },
  disabled: { label: "Отключён", tone: "neutral" },
};

export const SUPPLIER_ORDER_STATUS: Record<string, StatusInfo> = {
  created: { label: "Создан", tone: "info" },
  pending: { label: "Выполняется", tone: "accent" },
  succeeded: { label: "Выполнен", tone: "success" },
  failed: { label: "Ошибка", tone: "danger" },
  unknown: { label: "Неизвестно — сверьте вручную", tone: "warning" },
  cancelled: { label: "Отменён", tone: "neutral" },
};

export const MESSAGE_STATUS: Record<string, StatusInfo> = {
  new: { label: "Новое", tone: "info" },
  handled: { label: "Обработано", tone: "success" },
  escalated: { label: "Нужен оператор", tone: "warning" },
  auto_replied: { label: "Отвечено автоматически", tone: "success" },
  suggested: { label: "Ответ подготовлен", tone: "accent" },
};

export const SYNC_STATUS: Record<string, StatusInfo> = {
  running: { label: "Выполняется", tone: "accent" },
  succeeded: { label: "Успешно", tone: "success" },
  partial: { label: "Частично", tone: "warning" },
  failed: { label: "Ошибка", tone: "danger" },
  unavailable: { label: "Интеграция недоступна", tone: "neutral" },
  unknown: { label: "Нет данных", tone: "neutral" },
};

export const LOG_RESULT: Record<string, StatusInfo> = {
  ok: { label: "Выполнено", tone: "success" },
  skipped: { label: "Пропущено", tone: "neutral" },
  blocked: { label: "Заблокировано", tone: "warning" },
  error: { label: "Ошибка", tone: "danger" },
  suggested: { label: "Подсказка оператору", tone: "accent" },
};

export const NOTIFICATION_STATUS: Record<string, StatusInfo> = {
  pending: { label: "В очереди", tone: "info" },
  sent: { label: "Отправлено", tone: "success" },
  failed: { label: "Ошибка", tone: "danger" },
  suppressed: { label: "Не отправлено (выключено)", tone: "neutral" },
};

export const CODE_STATUS: Record<string, StatusInfo> = {
  available: { label: "Доступен", tone: "success" },
  reserved: { label: "Зарезервирован", tone: "warning" },
  issued: { label: "Выдан", tone: "info" },
  void: { label: "Аннулирован", tone: "neutral" },
};

export const PRICING_STATUS: Record<string, StatusInfo> = {
  ok: { label: "Цена проходит ограничения", tone: "success" },
  below_min: { label: "Цена ниже минимальной", tone: "danger" },
  stale_price: { label: "Цена поставщика устарела", tone: "warning" },
  no_cost: { label: "Нет закупочной цены", tone: "neutral" },
  no_fx: { label: "Нет курса валюты", tone: "warning" },
  impossible: { label: "Комиссии съедают маржу", tone: "danger" },
  market_below_min: { label: "Конкуренты дешевле минимума", tone: "warning" },
  not_calculated: { label: "Не рассчитано", tone: "neutral" },
};

export const CONFIDENCE: Record<string, StatusInfo> = {
  high: { label: "Высокая достоверность", tone: "success" },
  medium: { label: "Средняя достоверность", tone: "info" },
  low: { label: "Низкая достоверность", tone: "warning" },
  none: { label: "Нет данных", tone: "neutral" },
};

export const INTEGRATION_STATE: Record<string, StatusInfo> = {
  available: { label: "Работает через API", tone: "success" },
  assist: { label: "Режим подсказок оператору", tone: "warning" },
  unavailable: { label: "Интеграция недоступна", tone: "neutral" },
};

export const DELIVERY_TYPE: Record<string, string> = {
  code: "Цифровой код",
  service: "Услуга поставщика",
  manual: "Ручная выдача",
};

export const PURCHASE_MODE: Record<string, { label: string; hint: string }> = {
  monitor: { label: "Только мониторинг цен", hint: "Система следит за ценами и ничего не покупает" },
  manual: { label: "Ручная закупка", hint: "Вы покупаете сами, система подсказывает и учитывает" },
  confirm: { label: "После подтверждения", hint: "Покупка через API только после вашего подтверждения" },
  auto: { label: "Автоматически в лимитах", hint: "Для разрешённых товаров в пределах дневного лимита и лимита на операцию" },
};

export function info(map: Record<string, StatusInfo>, value: string | null | undefined): StatusInfo {
  if (!value) return { label: "—", tone: "neutral" };
  return map[value] ?? { label: value, tone: "neutral" };
}
