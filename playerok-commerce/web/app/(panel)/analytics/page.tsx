"use client";

import { BarChart3, CircleDollarSign, Clock, Download, FileSpreadsheet, Percent, Receipt, RotateCcw, ShoppingCart, Star, TrendingUp } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Async, Empty, Notice, PageHeader, Stat } from "@/components/app/blocks";
import { StatusBadge } from "@/components/app/status";
import { MoneyChart, OrdersChart } from "@/components/charts/charts";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useAction } from "@/lib/actions";
import { download, useApi } from "@/lib/api";
import { ago, cn, dt, money, num, pct } from "@/lib/format";
import { useSession } from "@/lib/session";
import { SYNC_STATUS } from "@/lib/status";
import type { Metrics, SeriesPoint, SyncRow } from "@/lib/types";

type ProductRow = { product_id: number; name: string; category: string; quantity: number; revenue: string; profit_before_withdrawal: string | null };

type Analytics = {
  metrics: Metrics;
  series: SeriesPoint[];
  breakdown: {
    products: ProductRow[];
    top_profit: ProductRow[];
    top_revenue: ProductRow[];
    categories: { category: string; quantity: number; revenue: string; profit: string }[];
    suppliers: { supplier: string; orders: number; succeeded: number; failed: number; spend_rub: string; success_rate: number | null }[];
  };
  sync: SyncRow[];
  totals: { deals: number; deals_by_source: Record<string, number>; reviews: number; transactions: number; last_update: string | null };
  generated_at: string;
};

const PERIODS = [
  ["today", "Сегодня"],
  ["yesterday", "Вчера"],
  ["7d", "7 дней"],
  ["30d", "30 дней"],
  ["90d", "90 дней"],
  ["custom", "Период"],
] as const;

const SOURCE: Record<string, string> = { manual: "вручную", import: "импорт CSV", bot: "бот", api: "API" };

function TopTable({ rows, by }: { rows: ProductRow[]; by: "revenue" | "profit" }) {
  if (!rows.length) return <Empty title="Нет завершённых продаж за период" />;
  const max = Math.max(...rows.map((r) => Math.abs(Number(by === "revenue" ? r.revenue : r.profit_before_withdrawal ?? 0))), 1);
  return (
    <ul className="flex flex-col gap-3 px-5 py-4">
      {rows.map((r) => {
        const value = Number(by === "revenue" ? r.revenue : r.profit_before_withdrawal ?? 0);
        return (
          <li key={r.product_id}>
            <div className="flex items-center justify-between gap-3 text-[13px]">
              <Link href={`/products/${r.product_id}`} className="truncate hover:text-highlight">
                {r.name}
              </Link>
              <span className="shrink-0 tabular-nums">
                {money(value)} <span className="text-muted-foreground">· {r.quantity} шт.</span>
              </span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-3">
              <div
                className={cn("h-full rounded-r-[4px]", value < 0 ? "bg-danger" : by === "revenue" ? "bg-[#3987e5]" : "bg-[#199e70]")}
                style={{ width: `${(Math.abs(value) / max) * 100}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export default function AnalyticsPage() {
  const { can } = useSession();
  const [period, setPeriod] = React.useState<string>("30d");
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [includeTest, setIncludeTest] = React.useState(false);
  const { busy, run } = useAction();

  const qs = new URLSearchParams({ period, include_test: String(includeTest) });
  if (period === "custom") {
    if (from) qs.set("from", from);
    if (to) qs.set("to", to);
  }
  const ready = period !== "custom" || (from && to);
  const state = useApi<Analytics>(ready ? `/analytics?${qs}` : null);

  return (
    <>
      <PageHeader
        title="Аналитика и отчёты"
        description="Только реальные данные системы: заказы, транзакции, закупки. Если данных нет — это видно, а не заполнено нулями «для красоты»."
        actions={
          can("analytics.export") && (
            <>
              <Button disabled={!ready} loading={busy === "csv"} onClick={() => run("csv", () => download(`/analytics/export?format=csv&${qs}`, "analytics.csv"))}>
                <Download /> CSV
              </Button>
              <Button disabled={!ready} loading={busy === "xlsx"} onClick={() => run("xlsx", () => download(`/analytics/export?format=xlsx&${qs}`, "analytics.xlsx"))}>
                <FileSpreadsheet /> Excel
              </Button>
            </>
          )
        }
      >
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex flex-wrap rounded-lg border border-border bg-surface p-1" role="tablist" aria-label="Период">
            {PERIODS.map(([code, label]) => (
              <button
                key={code}
                role="tab"
                aria-selected={period === code}
                onClick={() => setPeriod(code)}
                className={cn(
                  "h-8 rounded-md px-3 text-[13px] font-medium transition-colors",
                  period === code ? "bg-surface-3 text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          {period === "custom" && (
            <div className="flex items-center gap-2">
              <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-40" aria-label="С даты" />
              <span className="text-muted-foreground">—</span>
              <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-40" aria-label="По дату" />
            </div>
          )}
          <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <Switch checked={includeTest} onCheckedChange={setIncludeTest} /> Учитывать тестовые заказы
          </label>
        </div>
      </PageHeader>

      {!ready ? (
        <Notice>Выберите начальную и конечную дату.</Notice>
      ) : (
        <Async state={state} rows={10}>
          {(d) => {
            const m = d.metrics;
            return (
              <div className="flex flex-col gap-6">
                <p className="text-xs text-muted-foreground">
                  {m.period.label}: {dt(m.period.from, false)} — {dt(m.period.to, false)} · данные на {dt(d.generated_at)}
                  {d.totals.last_update ? ` · последнее изменение ${ago(d.totals.last_update)}` : ""}
                </p>
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                  <Stat label="Выручка" value={money(m.revenue)} icon={CircleDollarSign} hint={`средний чек ${money(m.avg_check)}`} />
                  <Stat
                    label="Чистая прибыль"
                    value={money(m.net_profit)}
                    tone={Number(m.net_profit) < 0 ? "danger" : Number(m.net_profit) > 0 ? "success" : undefined}
                    icon={TrendingUp}
                    hint={m.orders_without_cost ? `${m.orders_without_cost} заказов без себестоимости — прибыль по ним не учтена` : `маржа ${pct(m.margin_pct)}`}
                  />
                  <Stat label="Заказы" value={num(m.orders)} icon={ShoppingCart} hint={`завершено ${m.completed} · отменено ${m.cancelled}`} />
                  <Stat label="Расходы" value={money(Number(m.purchase_costs) + Number(m.fees))} icon={Receipt} hint={`закупка ${money(m.purchase_costs)} · комиссии ${money(m.fees)}`} />
                  <Stat label="Возвраты и споры" value={`${m.refunds} / ${m.disputes}`} icon={RotateCcw} hint={`сумма возвратов ${money(m.refunds_amount)}`} />
                  <Stat
                    label="Отзывы"
                    value={num(m.reviews)}
                    icon={Star}
                    hint={m.avg_review_rating ? `средняя оценка ${Number(m.avg_review_rating).toFixed(2)}` : m.shop_rating_note}
                  />
                  <Stat
                    label="Время обработки"
                    value={m.avg_processing_minutes !== null ? `${num(Math.round(m.avg_processing_minutes))} мин` : "—"}
                    icon={Clock}
                    hint="от создания до выдачи"
                  />
                  <Stat label="Конверсия" value={m.conversion !== null ? pct(m.conversion) : "—"} icon={Percent} hint={m.conversion_note} />
                </div>

                <Card>
                  <CardHeader title="Выручка и чистая прибыль по дням" description="Одна шкала в рублях; заказы — отдельным графиком ниже" />
                  <CardBody>
                    {m.orders === 0 && Number(m.revenue) === 0 ? (
                      <Empty title="За период нет продаж" icon={BarChart3}>
                        Графики строятся по завершённым заказам и транзакциям.
                      </Empty>
                    ) : (
                      <>
                        <MoneyChart data={d.series} height={280} />
                        <p className="mt-6 mb-2 text-xs text-muted-foreground">Заказы по дням</p>
                        <OrdersChart data={d.series} height={150} />
                      </>
                    )}
                  </CardBody>
                </Card>

                <div className="grid gap-6 xl:grid-cols-2">
                  <Card>
                    <CardHeader title="Товары по прибыли" description="До комиссии вывода; только заказы с известной себестоимостью" />
                    <TopTable rows={d.breakdown.top_profit} by="profit" />
                  </Card>
                  <Card>
                    <CardHeader title="Товары по выручке" />
                    <TopTable rows={d.breakdown.top_revenue} by="revenue" />
                  </Card>
                </div>

                <div className="grid gap-6 xl:grid-cols-2">
                  <Card>
                    <CardHeader title="Категории" />
                    {d.breakdown.categories.length ? (
                      <Table>
                        <THead>
                          <TR className="hover:bg-transparent">
                            <TH>Категория</TH>
                            <TH className="text-right">Продано</TH>
                            <TH className="text-right">Выручка</TH>
                            <TH className="text-right">Прибыль</TH>
                          </TR>
                        </THead>
                        <TBody>
                          {d.breakdown.categories.map((c) => (
                            <TR key={c.category}>
                              <TD>{c.category}</TD>
                              <TD className="text-right tabular-nums">{c.quantity}</TD>
                              <TD className="text-right tabular-nums">{money(c.revenue)}</TD>
                              <TD className="text-right tabular-nums">{money(c.profit)}</TD>
                            </TR>
                          ))}
                        </TBody>
                      </Table>
                    ) : (
                      <Empty title="Нет данных за период" />
                    )}
                  </Card>
                  <Card>
                    <CardHeader title="Поставщики" description="Закупки за период" />
                    {d.breakdown.suppliers.length ? (
                      <Table>
                        <THead>
                          <TR className="hover:bg-transparent">
                            <TH>Поставщик</TH>
                            <TH className="text-right">Закупок</TH>
                            <TH className="text-right">Успешно</TH>
                            <TH className="text-right">Сумма</TH>
                          </TR>
                        </THead>
                        <TBody>
                          {d.breakdown.suppliers.map((s) => (
                            <TR key={s.supplier}>
                              <TD>{s.supplier}</TD>
                              <TD className="text-right tabular-nums">{s.orders}</TD>
                              <TD className="text-right tabular-nums">
                                {s.success_rate !== null ? pct(s.success_rate) : "—"}
                                {s.failed > 0 && <span className="block text-xs text-red-300">ошибок {s.failed}</span>}
                              </TD>
                              <TD className="text-right tabular-nums">{money(s.spend_rub)}</TD>
                            </TR>
                          ))}
                        </TBody>
                      </Table>
                    ) : (
                      <Empty title="Закупок за период не было" />
                    )}
                  </Card>
                </div>

                <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
                  <Card>
                    <CardHeader title="Синхронизация данных" description="Откуда система получает данные и когда последний раз обновлялась" />
                    <Table>
                      <THead>
                        <TR className="hover:bg-transparent">
                          <TH>Источник</TH>
                          <TH>Статус</TH>
                          <TH className="text-right">Получено / сохранено</TH>
                          <TH className="text-right">Ошибок сегодня</TH>
                          <TH>Когда</TH>
                        </TR>
                      </THead>
                      <TBody>
                        {d.sync.map((r) => (
                          <TR key={`${r.source}-${r.kind}`}>
                            <TD>
                              {r.source} <span className="text-muted-foreground">· {r.kind}</span>
                              {r.message && <p className="max-w-80 truncate text-xs text-muted-foreground">{r.message}</p>}
                            </TD>
                            <TD>
                              <StatusBadge map={SYNC_STATUS} value={r.status} />
                            </TD>
                            <TD className="text-right tabular-nums">
                              {r.received} / {r.saved}
                            </TD>
                            <TD className={cn("text-right tabular-nums", r.errors_today > 0 && "text-red-300")}>{r.errors_today}</TD>
                            <TD className="whitespace-nowrap text-muted-foreground">{r.finished_at ? ago(r.finished_at) : "—"}</TD>
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                  </Card>
                  <Card>
                    <CardHeader title="Данные загружены" />
                    <CardBody className="flex flex-col gap-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Сделок (без тестовых)</span>
                        <span className="tabular-nums">{num(d.totals.deals)}</span>
                      </div>
                      {Object.entries(d.totals.deals_by_source).map(([k, v]) => (
                        <div key={k} className="flex justify-between pl-3 text-[13px]">
                          <span className="text-muted-foreground">{SOURCE[k] ?? k}</span>
                          <span className="tabular-nums">{num(v)}</span>
                        </div>
                      ))}
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Отзывов</span>
                        <span className="tabular-nums">{num(d.totals.reviews)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Транзакций</span>
                        <span className="tabular-nums">{num(d.totals.transactions)}</span>
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground">
                        Историю сделок PlayerOK можно загрузить из CSV в разделе «Заказы» — повторная загрузка не создаёт дублей.
                      </p>
                    </CardBody>
                  </Card>
                </div>
              </div>
            );
          }}
        </Async>
      )}
    </>
  );
}
