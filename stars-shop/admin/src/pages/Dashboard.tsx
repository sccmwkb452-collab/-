import { formatMoney } from "@starshop/shared";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, Clover, Info, RotateCcw, ShieldAlert, Truck, Wallet } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { BarChart, type BarDatum } from "../components/BarChart";
import { Card, cn, ErrorBox, PageTitle, Skeleton, Tabs, Toggle } from "../components/ui";
import { api, errorMessage } from "../lib/api";

interface DashboardData {
  currency: string;
  users: { total: number; new: number; active: number; paying: number };
  orders: { created: number; paid: number; completed: number; in_processing: number; awaiting_payment: number };
  money: {
    turnover: string;
    refunds: string;
    net_turnover: string;
    average_check: string | null;
    profit: string | null;
    profit_orders_with_cost: number;
    profit_orders_total: number;
  };
  conversion: number | null;
  lucky: { attempts: number; wins: number; turnover: string; prizes_value: string; win_rate: number | null; expected_win_rate: number | null };
  problems: { delivery_needs_attention: number; delivery_failed: number; payment_errors: number; webhook_rejected: number; refund_pending: number };
  cash: { provider: string; title: string; balances?: { currency: string; available: string; onhold: string }[]; error?: string }[];
}

const PERIODS = [
  { id: "day", label: "Сегодня" },
  { id: "week", label: "7 дней" },
  { id: "month", label: "30 дней" },
  { id: "quarter", label: "90 дней" },
] as const;
type PeriodId = (typeof PERIODS)[number]["id"];

const GRANULARITY = [
  { id: "day", label: "По дням", points: 30 },
  { id: "week", label: "По неделям", points: 12 },
  { id: "month", label: "По месяцам", points: 12 },
] as const;
type Gran = (typeof GRANULARITY)[number]["id"];

function Tile({ label, value, hint, accent }: { label: string; value: ReactNode; hint?: ReactNode; accent?: boolean }) {
  return (
    <div className={cn("rounded-2xl p-4 ring-1 ring-inset ring-line", accent ? "bg-[linear-gradient(135deg,color-mix(in_oklab,var(--c-accent)_16%,var(--c-surface)),var(--c-surface))]" : "bg-surface")}>
      <div className="text-[12.5px] font-semibold text-text-3">{label}</div>
      <div className="mt-1.5 text-[24px] font-semibold tracking-[-0.03em]">{value}</div>
      {hint && <div className="mt-1 text-[12px] text-text-3">{hint}</div>}
    </div>
  );
}

function Problem({ icon, label, value, to }: { icon: ReactNode; label: string; value: number; to: string }) {
  const ok = value === 0;
  return (
    <Link to={to} className="flex items-center gap-3 px-5 py-3 text-[13.5px] transition hover:bg-surface-2/60">
      <span className={cn("flex size-8 items-center justify-center rounded-lg", ok ? "bg-success/12 text-success" : "bg-warning/14 text-warning")}>{ok ? <CircleCheck className="size-4" /> : icon}</span>
      <span className="flex-1 text-text-2">{label}</span>
      <span className={cn("font-semibold tabular", ok ? "text-text-3" : "text-text")}>{value}</span>
    </Link>
  );
}

function bucketLabels(iso: string, g: Gran): { label: string; tooltip: string } {
  const d = new Date(`${iso}T00:00:00`);
  if (g === "month") {
    return { label: d.toLocaleDateString("ru-RU", { month: "short" }), tooltip: d.toLocaleDateString("ru-RU", { month: "long", year: "numeric" }) };
  }
  const short = d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
  return { label: short, tooltip: g === "week" ? `Неделя с ${d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}` : d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", weekday: "short" }) };
}

export default function Dashboard() {
  const [period, setPeriod] = useState<PeriodId>("week");
  const [includeDemo, setIncludeDemo] = useState(false);
  const [gran, setGran] = useState<Gran>("day");
  const points = GRANULARITY.find((g) => g.id === gran)!.points;

  const data = useQuery({
    queryKey: ["dashboard", period, includeDemo],
    queryFn: () => api<DashboardData>(`/dashboard?period=${period}&include_demo=${includeDemo}`),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });
  const series = useQuery({
    queryKey: ["series", gran, includeDemo],
    queryFn: () => api<{ items: { bucket: string; orders: number; turnover: string }[] }>(`/dashboard/series?granularity=${gran}&points=${points}&include_demo=${includeDemo}`),
    placeholderData: keepPreviousData,
  });

  const d = data.data;
  const c = d?.currency ?? "RUB";
  const turnoverSeries: BarDatum[] = (series.data?.items ?? []).map((p) => ({ key: p.bucket, ...bucketLabels(p.bucket, gran), value: Number(p.turnover) }));
  const orderSeries: BarDatum[] = (series.data?.items ?? []).map((p) => ({ key: p.bucket, ...bucketLabels(p.bucket, gran), value: p.orders }));

  return (
    <>
      <PageTitle title="Обзор" subtitle="Оборот, прибыль и денежный остаток считаются отдельно — см. пояснения ниже." />
      {/* Filters: one row above everything they scope */}
      <div className="mb-6 flex flex-wrap items-center gap-4">
        <Tabs value={period} onChange={setPeriod} items={[...PERIODS]} />
        <Toggle checked={includeDemo} onChange={setIncludeDemo} label="Учитывать DEMO-заказы" />
      </div>

      {data.isError && <ErrorBox text={errorMessage(data.error)} onRetry={() => data.refetch()} />}
      {!d ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-[104px]" />
          ))}
        </div>
      ) : (
        <div className={cn("space-y-6 transition-opacity", data.isFetching && "opacity-70")}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Tile accent label="Оборот" value={formatMoney(d.money.turnover, c)} hint={`Возвраты: ${formatMoney(d.money.refunds, c)} · чистый ${formatMoney(d.money.net_turnover, c)}`} />
            <Tile
              label="Прибыль"
              value={d.money.profit !== null ? formatMoney(d.money.profit, c) : "Нет данных"}
              hint={d.money.profit_orders_total ? `по ${d.money.profit_orders_with_cost} из ${d.money.profit_orders_total} выполненных заказов с себестоимостью` : "Нет выполненных заказов"}
            />
            <Tile label="Средний чек" value={d.money.average_check ? formatMoney(d.money.average_check, c) : "—"} hint={`Оплачено заказов: ${d.orders.paid}`} />
            <Tile label="Конверсия в покупку" value={d.conversion !== null ? `${d.conversion}%` : "—"} hint={`${d.users.paying} покупателей из ${d.users.active} активных`} />
            <Tile label="Пользователи" value={new Intl.NumberFormat("ru-RU").format(d.users.total)} hint={`Новых за период: ${d.users.new}`} />
            <Tile label="Заказы за период" value={d.orders.created} hint={`Выполнено: ${d.orders.completed}`} />
            <Tile label="В обработке" value={d.orders.in_processing} hint="Оплачены, ждут доставки" />
            <Tile label="Ожидают оплаты" value={d.orders.awaiting_payment} hint="Открытые заказы" />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card title="Оборот" action={<Tabs value={gran} onChange={setGran} items={GRANULARITY.map((g) => ({ id: g.id, label: g.label }))} />}>
              <div className="p-5 pt-3">
                {series.data ? <BarChart title="Оборот" data={turnoverSeries} format={(v) => formatMoney(v, c)} dimmed={series.isFetching} /> : <Skeleton className="h-[220px]" />}
              </div>
            </Card>
            <Card title="Оплаченные заказы">
              <div className="p-5 pt-3">
                {series.data ? <BarChart title="Заказы" data={orderSeries} format={(v) => `${v} шт.`} dimmed={series.isFetching} integer /> : <Skeleton className="h-[220px]" />}
              </div>
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Требует внимания">
              <div className="divide-y divide-line">
                <Problem icon={<Truck className="size-4" />} label="Доставка ждёт оператора" value={d.problems.delivery_needs_attention} to="/orders?status=processing" />
                <Problem icon={<CircleAlert className="size-4" />} label="Ошибки доставки" value={d.problems.delivery_failed} to="/orders?status=failed" />
                <Problem icon={<RotateCcw className="size-4" />} label="Возвраты в процессе" value={d.problems.refund_pending} to="/orders?status=refund_pending" />
                <Problem icon={<CircleAlert className="size-4" />} label="Ошибки платежей за период" value={d.problems.payment_errors} to="/orders?status=pending_payment" />
                <Problem icon={<ShieldAlert className="size-4" />} label="Отклонённые webhook-и" value={d.problems.webhook_rejected} to="/settings?tab=webhooks" />
              </div>
            </Card>
            <Card title="Денежный остаток у провайдеров">
              <div className="p-5">
                {d.cash.length === 0 ? (
                  <p className="flex gap-2 text-[13.5px] text-text-2">
                    <Wallet className="size-4 shrink-0 text-text-3" /> Подключённые провайдеры не сообщают баланс (или работает только DEMO).
                  </p>
                ) : (
                  <ul className="space-y-3">
                    {d.cash.map((p) => (
                      <li key={p.provider}>
                        <div className="text-[13px] font-semibold">{p.title}</div>
                        {p.error ? (
                          <div className="text-[12.5px] text-danger">{p.error}</div>
                        ) : p.balances && p.balances.length ? (
                          <div className="mt-1 flex flex-wrap gap-2">
                            {p.balances.map((b) => (
                              <span key={b.currency} className="rounded-lg bg-surface-2 px-2.5 py-1 text-[12.5px] font-semibold tabular ring-1 ring-line">
                                {b.available} {b.currency}
                                {Number(b.onhold) > 0 && <span className="text-text-3"> · hold {b.onhold}</span>}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <div className="text-[12.5px] text-text-3">Пусто</div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Card>
          </div>

          {d.lucky.attempts > 0 && (
            <Card title="Lucky Buy">
              <div className="grid grid-cols-2 gap-3 p-5 pt-3 lg:grid-cols-4">
                <Tile label="Попыток" value={d.lucky.attempts} hint={`Выигрышей: ${d.lucky.wins}`} />
                <Tile label="Оборот попыток" value={formatMoney(d.lucky.turnover, "XTR")} hint="В Telegram Stars, отдельно от оборота в деньгах" />
                <Tile label="Выиграно звёзд" value={formatMoney(d.lucky.prizes_value, "XTR")} hint="Сумма выигранных пакетов" />
                <Tile
                  label="Доля выигрышей"
                  value={d.lucky.win_rate !== null ? `${d.lucky.win_rate.toLocaleString("ru-RU")}%` : "—"}
                  hint={d.lucky.expected_win_rate !== null ? `Средний выбранный шанс: ${d.lucky.expected_win_rate.toLocaleString("ru-RU")}%` : undefined}
                />
              </div>
              <p className="flex gap-2 px-5 pb-5 text-[12.5px] leading-relaxed text-text-3">
                <Clover className="mt-0.5 size-4 shrink-0" /> На малом числе попыток доля выигрышей может заметно отличаться от среднего шанса — это нормально для случайных розыгрышей.
              </p>
            </Card>
          )}

          <Card>
            <div className="flex gap-3 p-5 text-[13px] leading-relaxed text-text-2">
              <Info className="mt-0.5 size-4 shrink-0 text-accent" />
              <p>
                <b className="text-text">Оборот</b> — сумма оплаченных за период заказов (без вычета возвратов и себестоимости). <b className="text-text">Прибыль</b> — оборот выполненных заказов минус их себестоимость (попытки Lucky Buy без выигрыша — с нулевой себестоимостью); заказы без
                данных о себестоимости не учитываются, комиссии провайдеров учитываются только если включены в себестоимость. <b className="text-text">Денежный остаток</b> — баланс, который сообщает платёжный провайдер, а
                не расчёт по заказам. DEMO-заказы не входят в денежные показатели, пока не включён переключатель выше.
              </p>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
