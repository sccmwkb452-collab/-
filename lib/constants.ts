import type { LeadSource, LeadStatus } from "@prisma/client";

export const CONSTRUCTION_PERIODS = [
  { code: "3m", label: "В ближайшие 3 месяца", hint: "Участок готов, хочу начать в этом сезоне" },
  { code: "3-6m", label: "Через 3–6 месяцев", hint: "Готовлюсь, собираю информацию" },
  { code: "6-12m", label: "Через 6–12 месяцев", hint: "Планирую на следующий сезон" },
  { code: "research", label: "Пока изучаю варианты", hint: "Хочу понять бюджет и возможности" },
] as const;

export type ConstructionPeriodCode = (typeof CONSTRUCTION_PERIODS)[number]["code"];

export const BUDGET_RANGES = [
  { code: "lt5", label: "до 5 млн ₽" },
  { code: "5-10", label: "5–10 млн ₽" },
  { code: "10-15", label: "10–15 млн ₽" },
  { code: "15-25", label: "15–25 млн ₽" },
  { code: "gt25", label: "более 25 млн ₽" },
] as const;

export const BEDROOM_CHOICES = [2, 3, 4, 5] as const;

export const LEAD_STATUS_LABELS: Record<LeadStatus, string> = {
  NEW: "Новая",
  IN_PROGRESS: "В работе",
  CONTACTED: "Контакт установлен",
  CALCULATION: "Расчёт",
  CONTRACT: "Договор",
  COMPLETED: "Завершена",
  REJECTED: "Отказ",
};

export const LEAD_STATUS_ORDER: LeadStatus[] = [
  "NEW",
  "IN_PROGRESS",
  "CONTACTED",
  "CALCULATION",
  "CONTRACT",
  "COMPLETED",
  "REJECTED",
];

export const LEAD_SOURCE_LABELS: Record<LeadSource, string> = {
  CALCULATOR: "Калькулятор",
  PROJECT: "Страница проекта",
  CONTACT_FORM: "Форма контактов",
};

export function periodLabel(code: string | null | undefined) {
  return CONSTRUCTION_PERIODS.find((p) => p.code === code)?.label ?? code ?? "—";
}

export function budgetLabel(code: string | null | undefined) {
  return BUDGET_RANGES.find((b) => b.code === code)?.label ?? code ?? "—";
}
