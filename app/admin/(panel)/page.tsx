import { ArrowRight, Calculator, Inbox, Percent, TrendingUp, Users } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { LeadStatusBadge } from "@/components/admin/lead-status-badge";
import { LeadsChart } from "@/components/admin/leads-chart";
import { AdminPageHeader } from "@/components/admin/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LEAD_STATUS_LABELS, LEAD_STATUS_ORDER } from "@/lib/constants";
import { prisma } from "@/lib/db";
import { formatDate, formatPhoneDisplay, formatPrice } from "@/lib/utils";

export const metadata: Metadata = { title: "Dashboard" };

function startOfDay(d: Date) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

export default async function DashboardPage() {
  const now = new Date();
  const today = startOfDay(now);
  const weekAgo = new Date(today.getTime() - 6 * 86400000);
  const monthAgo = new Date(today.getTime() - 29 * 86400000);
  const chartFrom = new Date(today.getTime() - 13 * 86400000);

  const [newCount, todayCount, weekCount, calcMonth, leadsFromCalcMonth, byStatus, latest, chartLeads, chartCalcs, pipeline] = await Promise.all([
    prisma.lead.count({ where: { status: "NEW" } }),
    prisma.lead.count({ where: { createdAt: { gte: today } } }),
    prisma.lead.count({ where: { createdAt: { gte: weekAgo } } }),
    prisma.calculation.count({ where: { createdAt: { gte: monthAgo } } }),
    prisma.lead.count({ where: { createdAt: { gte: monthAgo }, calculationId: { not: null } } }),
    prisma.lead.groupBy({ by: ["status"], _count: { _all: true } }),
    prisma.lead.findMany({ orderBy: { createdAt: "desc" }, take: 6, include: { project: { select: { title: true } } } }),
    prisma.lead.findMany({ where: { createdAt: { gte: chartFrom } }, select: { createdAt: true } }),
    prisma.calculation.findMany({ where: { createdAt: { gte: chartFrom } }, select: { createdAt: true } }),
    prisma.lead.aggregate({ where: { status: { in: ["NEW", "IN_PROGRESS", "CONTACTED", "CALCULATION"] } }, _sum: { estimatedPrice: true } }),
  ]);

  const conversion = calcMonth ? Math.round((leadsFromCalcMonth / calcMonth) * 1000) / 10 : 0;
  const days = Array.from({ length: 14 }, (_, i) => new Date(chartFrom.getTime() + i * 86400000));
  const key = (d: Date) => startOfDay(d).getTime();
  const count = (rows: { createdAt: Date }[]) => {
    const m = new Map<number, number>();
    rows.forEach((r) => m.set(key(r.createdAt), (m.get(key(r.createdAt)) ?? 0) + 1));
    return m;
  };
  const lm = count(chartLeads);
  const cm = count(chartCalcs);
  const chart = days.map((d) => ({
    date: d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" }),
    leads: lm.get(key(d)) ?? 0,
    calculations: cm.get(key(d)) ?? 0,
  }));
  const statusMap = new Map(byStatus.map((s) => [s.status, s._count._all]));
  const totalLeads = byStatus.reduce((s, x) => s + x._count._all, 0);

  const stats = [
    { label: "Новые заявки", value: newCount, icon: Inbox, href: "/admin/leads?status=NEW", accent: true },
    { label: "Заявки за сегодня", value: todayCount, icon: TrendingUp },
    { label: "Заявки за неделю", value: weekCount, icon: Users },
    { label: "Расчётов за 30 дней", value: calcMonth, icon: Calculator },
    { label: "Конверсия расчёт → заявка", value: `${String(conversion).replace(".", ",")}%`, icon: Percent },
  ];

  return (
    <>
      <AdminPageHeader
        title="Dashboard"
        description={`Сводка на ${formatDate(now, true)}`}
        actions={
          <Button asChild>
            <Link href="/admin/leads">Все заявки <ArrowRight /></Link>
          </Button>
        }
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        {stats.map((s) => {
          const body = (
            <Card className={s.accent ? "h-full border-transparent bg-primary text-primary-foreground" : "h-full"}>
              <CardContent className="flex h-full flex-col p-5 sm:p-5">
                <s.icon className={s.accent ? "size-5 text-accent" : "size-5 text-muted-foreground"} />
                <p className="mt-6 text-3xl font-semibold tracking-tight tabular">{s.value}</p>
                <p className={s.accent ? "mt-1 text-sm text-white/60" : "mt-1 text-sm text-muted-foreground"}>{s.label}</p>
              </CardContent>
            </Card>
          );
          return s.href ? <Link key={s.label} href={s.href} className="rounded-2xl">{body}</Link> : <div key={s.label}>{body}</div>;
        })}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Заявки и расчёты за 14 дней</CardTitle>
            <div className="flex gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-accent" />Заявки</span>
              <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-primary" />Расчёты</span>
            </div>
          </CardHeader>
          <CardContent>
            <LeadsChart data={chart} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Воронка</CardTitle>
            <p className="text-sm text-muted-foreground">В работе на сумму {formatPrice(pipeline._sum.estimatedPrice ?? 0)}</p>
          </CardHeader>
          <CardContent className="space-y-3">
            {LEAD_STATUS_ORDER.map((s) => {
              const c = statusMap.get(s) ?? 0;
              const pct = totalLeads ? (c / totalLeads) * 100 : 0;
              return (
                <Link key={s} href={`/admin/leads?status=${s}`} className="block rounded-lg p-1 hover:bg-secondary">
                  <div className="flex justify-between text-sm">
                    <span>{LEAD_STATUS_LABELS[s]}</span>
                    <span className="font-semibold tabular">{c}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-secondary">
                    <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
                  </div>
                </Link>
              );
            })}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Последние заявки</CardTitle>
          <Link href="/admin/leads" className="text-sm text-muted-foreground hover:text-foreground">Смотреть все →</Link>
        </CardHeader>
        <CardContent className="px-0 sm:px-0">
          {latest.length ? (
            <ul className="divide-y divide-border">
              {latest.map((l) => (
                <li key={l.id}>
                  <Link href={`/admin/leads/${l.id}`} className="flex flex-wrap items-center gap-x-6 gap-y-1 px-5 py-3.5 transition hover:bg-secondary/60 sm:px-6">
                    <span className="min-w-40 font-medium">{l.name}</span>
                    <span className="text-sm text-muted-foreground tabular">{formatPhoneDisplay(l.phone)}</span>
                    <span className="hidden text-sm text-muted-foreground md:inline">{l.project?.title ?? (l.area ? `${l.area} м²` : "—")}</span>
                    <span className="ml-auto text-sm font-medium tabular">{l.estimatedPrice ? formatPrice(l.estimatedPrice) : "—"}</span>
                    <LeadStatusBadge status={l.status} />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-6 py-10 text-center text-muted-foreground">Заявок пока нет. Они появятся после первых расчётов на сайте.</p>
          )}
        </CardContent>
      </Card>
    </>
  );
}
