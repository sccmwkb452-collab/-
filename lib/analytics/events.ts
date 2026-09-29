"use client";

export type AnalyticsEvent =
  | "calculator_start"
  | "calculator_step"
  | "calculator_complete"
  | "lead_form_open"
  | "lead_submitted"
  | "project_view"
  | "calculator_project_selected";

type Params = Record<string, string | number | boolean | undefined>;

declare global {
  interface Window {
    ym?: (id: number, method: string, ...args: unknown[]) => void;
    gtag?: (...args: unknown[]) => void;
    dataLayer?: unknown[];
  }
}

/**
 * Единая точка отправки событий. Отправляет цель в Яндекс Метрику и событие в GA4,
 * если соответствующие счётчики подключены через переменные окружения.
 */
export function trackEvent(event: AnalyticsEvent, params: Params = {}) {
  if (typeof window === "undefined") return;
  const ymId = Number(process.env.NEXT_PUBLIC_YANDEX_METRIKA_ID);
  if (ymId && typeof window.ym === "function") window.ym(ymId, "reachGoal", event, params);
  if (typeof window.gtag === "function") window.gtag("event", event, params);
  window.dispatchEvent(new CustomEvent("forma:analytics", { detail: { event, params } }));
}
