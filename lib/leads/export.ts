import "server-only";
import type { Lead, Project } from "@prisma/client";
import { budgetLabel, LEAD_SOURCE_LABELS, LEAD_STATUS_LABELS, periodLabel } from "@/lib/constants";
import { formatDate } from "@/lib/utils";

type LeadRow = Lead & { project: Pick<Project, "title"> | null };

/** Экранирование CSV + защита от CSV-инъекций (формулы в Excel). */
function cell(value: unknown) {
  let s = value === null || value === undefined ? "" : String(value);
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return `"${s.replace(/"/g, '""')}"`;
}

const COLUMNS: [string, (l: LeadRow) => unknown][] = [
  ["ID", (l) => l.id],
  ["Дата", (l) => formatDate(l.createdAt, true)],
  ["Статус", (l) => LEAD_STATUS_LABELS[l.status]],
  ["Источник", (l) => LEAD_SOURCE_LABELS[l.source]],
  ["Имя", (l) => l.name],
  ["Телефон", (l) => l.phone],
  ["Email", (l) => l.email],
  ["Telegram", (l) => l.telegram],
  ["Проект", (l) => l.project?.title],
  ["Тип дома", (l) => l.houseType],
  ["Площадь, м²", (l) => l.area],
  ["Спальни", (l) => l.bedrooms],
  ["Технология", (l) => l.technology],
  ["Комплектация", (l) => l.package],
  ["Опции", (l) => l.options.join(", ")],
  ["Стоимость, ₽", (l) => l.estimatedPrice],
  ["Сроки", (l) => (l.constructionPeriod ? periodLabel(l.constructionPeriod) : "")],
  ["Бюджет", (l) => (l.budget ? budgetLabel(l.budget) : "")],
  ["Регион", (l) => l.region],
  ["Комментарий клиента", (l) => l.comment],
  ["Комментарий менеджера", (l) => l.managerComment],
];

export function leadsToCsv(leads: LeadRow[]) {
  const header = COLUMNS.map(([name]) => cell(name)).join(";");
  const rows = leads.map((l) => COLUMNS.map(([, get]) => cell(get(l))).join(";"));
  return `﻿${[header, ...rows].join("\r\n")}`;
}

export function csvResponse(csv: string, filename: string) {
  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "no-store",
    },
  });
}
