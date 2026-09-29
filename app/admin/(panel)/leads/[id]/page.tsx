import { ArrowLeft, Download, Mail, Phone, Send } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { DeleteLeadButton, LeadCommentForm, LeadStatusSelect } from "@/components/admin/lead-actions";
import { LeadStatusBadge } from "@/components/admin/lead-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { budgetLabel, LEAD_SOURCE_LABELS, LEAD_STATUS_LABELS, periodLabel } from "@/lib/constants";
import { prisma } from "@/lib/db";
import type { EstimateResult } from "@/lib/pricing/types";
import { formatArea, formatDate, formatPhoneDisplay, formatPrice, phoneHref } from "@/lib/utils";

export const metadata: Metadata = { title: "Заявка" };

function isEstimate(value: unknown): value is EstimateResult {
  return typeof value === "object" && value !== null && "total" in value && "base" in value;
}

export default async function LeadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const lead = await prisma.lead.findUnique({
    where: { id },
    include: {
      project: { select: { title: true, slug: true, id: true } },
      events: { orderBy: { createdAt: "desc" }, include: { admin: { select: { name: true } } } },
    },
  });
  if (!lead) notFound();
  const breakdown = isEstimate(lead.breakdown) ? lead.breakdown : null;

  const contact = [
    { label: "Телефон", value: formatPhoneDisplay(lead.phone) },
    { label: "Email", value: lead.email },
    { label: "Telegram", value: lead.telegram },
    { label: "Регион участка", value: lead.region },
    { label: "Бюджет", value: lead.budget ? budgetLabel(lead.budget) : null },
    { label: "Сроки", value: lead.constructionPeriod ? periodLabel(lead.constructionPeriod) : null },
    { label: "Источник", value: LEAD_SOURCE_LABELS[lead.source] },
    { label: "Согласие на обработку", value: formatDate(lead.consentAt, true) },
  ];
  const params_ = [
    { label: "Проект", value: lead.project?.title ?? "Индивидуальный" },
    { label: "Тип дома", value: lead.houseType },
    { label: "Площадь", value: lead.area ? formatArea(lead.area) : null },
    { label: "Спальни", value: lead.bedrooms ? String(lead.bedrooms) : null },
    { label: "Технология", value: lead.technology },
    { label: "Комплектация", value: lead.package },
  ];

  return (
    <>
      <Link href="/admin/leads" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" />
        Все заявки
      </Link>
      <div className="mt-4 mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{lead.name}</h1>
            <LeadStatusBadge status={lead.status} />
          </div>
          <p className="mt-1.5 text-sm text-muted-foreground">Заявка от {formatDate(lead.createdAt, true)} · #{lead.id.slice(-8)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <LeadStatusSelect leadId={lead.id} status={lead.status} />
          <Button asChild variant="outline">
            <a href={`/api/admin/leads/${lead.id}/export`}><Download />Экспорт</a>
          </Button>
          <DeleteLeadButton leadId={lead.id} />
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card>
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
              <CardTitle>Клиент</CardTitle>
              <div className="flex gap-2">
                <Button asChild size="sm"><a href={phoneHref(lead.phone)}><Phone />Позвонить</a></Button>
                {lead.telegram && <Button asChild size="sm" variant="outline"><a href={`https://t.me/${lead.telegram.replace("@", "")}`} target="_blank" rel="noopener noreferrer"><Send />Telegram</a></Button>}
                {lead.email && <Button asChild size="sm" variant="outline"><a href={`mailto:${lead.email}`}><Mail />Email</a></Button>}
              </div>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
                {contact.map((c) => (
                  <div key={c.label}>
                    <dt className="text-xs text-muted-foreground">{c.label}</dt>
                    <dd className="mt-0.5 font-medium break-words">{c.value || "—"}</dd>
                  </div>
                ))}
              </dl>
              {lead.comment && (
                <div className="mt-6 rounded-xl bg-secondary p-4">
                  <p className="text-xs text-muted-foreground">Комментарий клиента</p>
                  <p className="mt-1 text-[15px] whitespace-pre-line">{lead.comment}</p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Параметры расчёта</CardTitle>
              {lead.project && <Link href={`/projects/${lead.project.slug}`} target="_blank" className="text-sm text-muted-foreground hover:text-foreground">Открыть проект ↗</Link>}
            </CardHeader>
            <CardContent>
              <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-3">
                {params_.map((c) => (
                  <div key={c.label}>
                    <dt className="text-xs text-muted-foreground">{c.label}</dt>
                    <dd className="mt-0.5 font-medium">{c.value || "—"}</dd>
                  </div>
                ))}
              </dl>
              {lead.options.length > 0 && (
                <div className="mt-6">
                  <p className="text-xs text-muted-foreground">Дополнительные опции</p>
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {lead.options.map((o) => (
                      <li key={o} className="rounded-full bg-secondary px-3 py-1 text-sm">{o}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="mt-6 rounded-2xl bg-primary p-5 text-primary-foreground">
                <p className="text-sm text-white/55">Предварительная стоимость</p>
                <p className="mt-1 text-3xl font-semibold tracking-tight tabular">{lead.estimatedPrice ? formatPrice(lead.estimatedPrice) : "—"}</p>
                {breakdown && (
                  <dl className="mt-4 space-y-1.5 border-t border-white/10 pt-4 text-sm">
                    {[
                      ["Базовая стоимость", breakdown.base],
                      ["Тип дома", breakdown.houseTypeAdjustment],
                      ["Комплектация", breakdown.packageAdjustment],
                      ["Доп. спальни", breakdown.bedroomsAdjustment],
                      ["Опции", breakdown.optionsTotal],
                    ]
                      .filter(([, v]) => v !== 0)
                      .map(([k, v]) => (
                        <div key={k as string} className="flex justify-between">
                          <dt className="text-white/60">{k}</dt>
                          <dd className="tabular">{(v as number) < 0 ? "−" : ""}{formatPrice(Math.abs(v as number))}</dd>
                        </div>
                      ))}
                  </dl>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Комментарий менеджера</CardTitle></CardHeader>
            <CardContent>
              <LeadCommentForm leadId={lead.id} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>История</CardTitle></CardHeader>
            <CardContent>
              <ol className="relative space-y-5 border-l border-border pl-5">
                {lead.events.map((e) => (
                  <li key={e.id} className="relative">
                    <span className="absolute top-1.5 -left-[1.4rem] size-2.5 rounded-full border-2 border-white bg-accent" />
                    <p className="text-xs text-muted-foreground">
                      {formatDate(e.createdAt, true)}
                      {e.admin && ` · ${e.admin.name}`}
                    </p>
                    <p className="mt-0.5 text-sm">
                      {e.type === "STATUS_CHANGED" && e.toStatus
                        ? `Статус: ${e.fromStatus ? LEAD_STATUS_LABELS[e.fromStatus] : "—"} → ${LEAD_STATUS_LABELS[e.toStatus]}`
                        : e.message}
                    </p>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
