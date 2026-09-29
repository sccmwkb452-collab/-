import { formatArea, formatPrice } from "@/lib/utils";
import type { LeadNotification } from "./types";

export function leadLines(lead: LeadNotification) {
  const rows: [string, string | null | undefined][] = [
    ["Имя", lead.name],
    ["Телефон", lead.phone],
    ["Email", lead.email],
    ["Telegram", lead.telegram],
    ["Проект", lead.project],
    ["Тип дома", lead.houseType],
    ["Площадь", lead.area ? formatArea(lead.area) : null],
    ["Спальни", lead.bedrooms ? String(lead.bedrooms) : null],
    ["Технология", lead.technology],
    ["Комплектация", lead.package],
    ["Опции", lead.options.length ? lead.options.join(", ") : null],
    ["Стоимость", lead.estimatedPrice ? formatPrice(lead.estimatedPrice) : null],
    ["Сроки", lead.period],
    ["Бюджет", lead.budget],
    ["Регион", lead.region],
    ["Комментарий", lead.comment],
    ["Источник", lead.source],
  ];
  return rows.filter((r): r is [string, string] => Boolean(r[1]));
}

export function escapeHtml(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export function leadAdminUrl(id: string) {
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  return `${base.replace(/\/$/, "")}/admin/leads/${id}`;
}
