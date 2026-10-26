"use client";

import { Activity, AlertTriangle, Bot, CircleDollarSign, Database, Package, Server, ShoppingCart, TrendingUp } from "lucide-react";
import Link from "next/link";

import { Async, Empty, Notice, PageHeader, Stat } from "@/components/app/blocks";
import { OrderTable } from "@/components/app/order-table";
import { StatusBadge, ToneBadge } from "@/components/app/status";
import { MoneyChart, OrdersChart } from "@/components/charts/charts";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { useApi } from "@/lib/api";
import { ago, cn, money, num, pct } from "@/lib/format";
import { CONFIDENCE, INTEGRATION_STATE, ORDER_STATUS, SUPPLIER_STATUS, SYNC_STATUS } from "@/lib/status";
import type { AutoItem, Integration, KillSwitch, Metrics, Notification, Order, Product, SeriesPoint, SyncRow } from "@/lib/types";

type HealthPart = { ok: boolean; last_seen_at?: string | null; message?: string };

type Dashboard = {
  mode: "test" | "live";
  live_allowed: boolean;
  kill_switch: KillSwitch;
  health: { database: HealthPart; worker: HealthPart; bot: HealthPart; queue: Record<string, number> };
  today: Metrics;
  week: Metrics;
  series: SeriesPoint[];
  attention: Order[];
  recent: Order[];
  open_by_status: Record<string, number>;
  suppliers: { id: number; name: string; status: string; status_label: string; last_error: string | null }[];
  notifications: Notification[];
  integration: Integration;
  sync: SyncRow[];
  totals: { deals: number; deals_by_source: Record<string, number>; reviews: number; transactions: number; last_update: string | null };
  research_top: { product: Product; score: string; confidence: string }[];
  autosettings: AutoItem[];
};

function HealthRow({ icon: Icon, label, part, okText, badText }: { icon: typeof Server; label: string; part: HealthPart; okText: string; badText: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="flex items-center gap-2 text-sm">
        <Icon className="size-4 text-subtle" /> {label}
      </span>
      <span className="flex items-center gap-2 text-[13px]">
        <span className={cn("size-2 rounded-full", part.ok ? "bg-success" : "bg-danger")} aria-hidden />
        {part.ok ? okText : badText}
        {part.last_seen_at !== undefined && <span className="text-muted-foreground">· {ago(part.last_seen_at)}</span>}
      </span>
    </div>
  );
}

export default function DashboardPage() {
  const state = useApi<Dashboard>("/dashboard");
  return (
    <>
      <PageHeader title="Главная панель" description="Сводка магазина по реальным данным системы: заказы, деньги, поставщики и автоматизация." />
      <Async state={state} rows={8}>
        {(d) => {
          const available = Object.values(d.integration.capabilities).filter((c) => c.available).length;
          const enabledAuto = d.autosettings.filter((a) => a.enabled).length;
          const openTotal = Object.values(d.open_by_status).reduce((a, b) => a + b, 0);
          const noData = d.week.orders === 0;
          return (
            <div className="flex flex-col gap-6">
              <div className="grid gap-3 lg:grid-cols-2">
                {d.mode === "test" ? (
                  <Notice tone="warning" title="Тестовый режим">
                    Закупки у поставщиков и публикации не выполняются по-настоящему: система показывает, что сделала бы. Боевой режим включается в разделе{" "}
                    <Link href="/security" className="text-highlight hover:underline">
                      «Безопасность»
                    </Link>
                    {d.live_allowed ? "." : " и только после ALLOW_LIVE_OPERATIONS=true на сервере."}
                  </Notice>
                ) : (
                  <Notice tone="success" title="Боевой режим">
                    Закупки выполняются в пределах лимитов поставщиков. Аварийная остановка — в разделе «Безопасность».
                  </Notice>
                )}
                {d.kill_switch.active ? (
                  <Notice tone="danger" title="Вся автоматизация остановлена">
                    {d.kill_switch.reason || "Причина не указана"} · {d.kill_switch.by ?? ""} {ago(d.kill_switch.at)}
                  </Notice>
                ) : (
                  <Notice tone="info" title={`${d.integration.title}: ${available} из ${Object.keys(d.integration.capabilities).length} функций через API`}>
                    У PlayerOK нет открытого API — заказы и сообщения вносятся вручную или из CSV, а бот готовит тексты для отправки.{" "}
                    <Link href="/errors" className="text-highlight hover:underline">
                      Подробнее
                    </Link>
                  </Notice>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                <Stat label="Выручка сегодня" value={money(d.today.revenue)} hint={`${num(d.today.orders)} заказов`} icon={CircleDollarSign} />
                <Stat
                  label="Чистая прибыль сегодня"
                  value={money(d.today.net_profit)}
                  tone={Number(d.today.net_profit) < 0 ? "danger" : Number(d.today.net_profit) > 0 ? "success" : undefined}
                  hint={d.today.orders_without_cost ? `${d.today.orders_without_cost} заказов без закупочной цены` : "после комиссий и закупки"}
                  icon={TrendingUp}
                />
                <Stat
                  label="За 7 дней"
                  value={money(d.week.revenue)}
                  hint={`прибыль ${money(d.week.net_profit)} · маржа ${pct(d.week.margin_pct)}`}
                  icon={Activity}
                />
                <Stat
                  label="Открытые заказы"
                  value={num(openTotal)}
                  tone={d.attention.length ? "warning" : undefined}
                  hint={d.attention.length ? `${d.attention.length} требуют внимания` : "ничего не требует внимания"}
                  icon={ShoppingCart}
                />
              </div>

              <div className="grid gap-6 xl:grid-cols-3">
                <Card className="xl:col-span-2">
                  <CardHeader title="Выручка и чистая прибыль, 7 дней" description="По проведённым транзакциям, без тестовых заказов" />
                  <CardBody>
                    {noData ? (
                      <Empty title="Продаж за 7 дней нет" icon={TrendingUp}>
                        График появится после первых завершённых заказов. Заказы вносятся в разделе «Заказы» или в боте.
                      </Empty>
                    ) : (
                      <>
                        <MoneyChart data={d.series} />
                        <p className="mt-5 mb-2 text-xs text-muted-foreground">Заказы по дням</p>
                        <OrdersChart data={d.series} height={120} />
                      </>
                    )}
                  </CardBody>
                </Card>

                <Card>
                  <CardHeader title="Состояние системы" />
                  <CardBody className="divide-y divide-border py-2">
                    <HealthRow icon={Database} label="База данных" part={d.health.database} okText="работает" badText="недоступна" />
                    <HealthRow icon={Server} label="Воркер" part={d.health.worker} okText="работает" badText="не отвечает" />
                    <HealthRow icon={Bot} label="Telegram-бот" part={d.health.bot} okText="работает" badText="не отвечает" />
                    <div className="flex items-center justify-between py-2 text-sm">
                      <span className="text-muted-foreground">Очередь задач</span>
                      <span className="text-[13px] tabular-nums">
                        {d.health.queue.queued ?? 0} в очереди · {d.health.queue.running ?? 0} выполняется
                        {d.health.queue.failed ? <span className="text-red-300"> · {d.health.queue.failed} с ошибкой</span> : null}
                      </span>
                    </div>
                    <div className="flex items-center justify-between py-2 text-sm">
                      <span className="text-muted-foreground">Автонастройки</span>
                      <Link href="/autosettings" className="text-[13px] hover:text-highlight">
                        включено {enabledAuto} из {d.autosettings.length}
                      </Link>
                    </div>
                    <div className="flex items-center justify-between py-2 text-sm">
                      <span className="text-muted-foreground">Данные в системе</span>
                      <span className="text-[13px] tabular-nums">
                        {num(d.totals.deals)} сделок · {num(d.totals.reviews)} отзывов
                      </span>
                    </div>
                  </CardBody>
                </Card>
              </div>

              <div className="grid gap-6 xl:grid-cols-2">
                <Card>
                  <CardHeader
                    title="Требуют внимания"
                    description="Заказы, где автоматика остановилась и ждёт решения"
                    actions={
                      <Button size="sm" asChild>
                        <Link href="/orders?attention=1">Все</Link>
                      </Button>
                    }
                  />
                  {d.attention.length ? (
                    <OrderTable orders={d.attention} compact />
                  ) : (
                    <Empty title="Всё в порядке" icon={AlertTriangle}>
                      Заказов, требующих решения, нет.
                    </Empty>
                  )}
                </Card>
                <Card>
                  <CardHeader
                    title="Последние заказы"
                    actions={
                      <Button size="sm" asChild>
                        <Link href="/orders">Все заказы</Link>
                      </Button>
                    }
                  />
                  {d.recent.length ? (
                    <OrderTable orders={d.recent} compact />
                  ) : (
                    <Empty title="Заказов пока нет" icon={ShoppingCart}>
                      Внесите заказ PlayerOK вручную или импортируйте CSV в разделе «Заказы».
                    </Empty>
                  )}
                </Card>
              </div>

              <div className="grid gap-6 xl:grid-cols-3">
                <Card>
                  <CardHeader title="Поставщики" actions={<Button size="sm" asChild><Link href="/suppliers">Открыть</Link></Button>} />
                  <CardBody className="divide-y divide-border py-1">
                    {d.suppliers.map((s) => (
                      <Link key={s.id} href={`/suppliers/${s.id}`} className="flex items-center justify-between gap-3 py-2.5 hover:text-highlight">
                        <span className="text-sm">{s.name}</span>
                        <StatusBadge map={SUPPLIER_STATUS} value={s.status} />
                      </Link>
                    ))}
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="Синхронизация" description="Последний запуск по каждому источнику" />
                  <CardBody className="divide-y divide-border py-1">
                    {d.sync.map((r) => (
                      <div key={`${r.source}-${r.kind}`} className="py-2.5">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-sm">
                            {r.source} <span className="text-muted-foreground">· {r.kind}</span>
                          </span>
                          <StatusBadge map={SYNC_STATUS} value={r.status} />
                        </div>
                        <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                          {r.finished_at ? `${ago(r.finished_at)} · получено ${r.received}, сохранено ${r.saved}` : r.message}
                        </p>
                      </div>
                    ))}
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="Лучшие товары по исследованию" actions={<Button size="sm" asChild><Link href="/research">Рейтинг</Link></Button>} />
                  {d.research_top.length ? (
                    <CardBody className="divide-y divide-border py-1">
                      {d.research_top.map((r) => (
                        <Link key={r.product.id} href={`/products/${r.product.id}`} className="flex items-center justify-between gap-3 py-2.5 hover:text-highlight">
                          <span className="min-w-0">
                            <span className="block truncate text-sm">{r.product.name}</span>
                            <span className="text-xs text-muted-foreground">{CONFIDENCE[r.confidence]?.label}</span>
                          </span>
                          <span className="text-sm font-semibold tabular-nums">{Number(r.score).toFixed(0)}</span>
                        </Link>
                      ))}
                    </CardBody>
                  ) : (
                    <Empty title="Рейтинг пока пуст" icon={Package}>
                      Добавьте товары и цены поставщиков — система посчитает оценку и покажет, на чём основан расчёт.
                    </Empty>
                  )}
                </Card>
              </div>

              <Card>
                <CardHeader title="Автонастройки" actions={<Button size="sm" asChild><Link href="/autosettings">Настроить</Link></Button>} />
                <CardBody className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                  {d.autosettings.map((a) => (
                    <Link
                      key={a.code}
                      href={`/autosettings/${a.code}`}
                      className="flex min-w-0 items-center justify-between gap-3 rounded-md border border-border px-3 py-2 hover:border-border-strong hover:bg-surface-2"
                    >
                      <span className="min-w-0 truncate text-[13px]">{a.title}</span>
                      {a.integration.state === "unavailable" ? (
                        <StatusBadge map={INTEGRATION_STATE} value="unavailable" />
                      ) : a.enabled && !a.stopped ? (
                        <ToneBadge tone="success">Включено</ToneBadge>
                      ) : (
                        <ToneBadge tone="neutral">{a.stopped ? "Остановлено" : "Выключено"}</ToneBadge>
                      )}
                    </Link>
                  ))}
                </CardBody>
              </Card>

              {Object.keys(d.open_by_status).length > 0 && (
                <Card>
                  <CardHeader title="Открытые заказы по статусам" />
                  <CardBody className="flex flex-wrap gap-2">
                    {Object.entries(d.open_by_status).map(([status, count]) => (
                      <Link key={status} href={`/orders?status=${status}`}>
                        <StatusBadge map={ORDER_STATUS} value={status} label={`${ORDER_STATUS[status]?.label ?? status}: ${count}`} />
                      </Link>
                    ))}
                  </CardBody>
                </Card>
              )}
            </div>
          );
        }}
      </Async>
    </>
  );
}
