"use client";

import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import Link from "next/link";

import { Async, Empty, PageHeader } from "@/components/app/blocks";
import { StatusBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { dt, money } from "@/lib/format";
import { useSession } from "@/lib/session";
import { LOG_RESULT, NOTIFICATION_STATUS, SUPPLIER_ORDER_STATUS, SUPPLIER_STATUS, SYNC_STATUS } from "@/lib/status";
import type { AutomationEntry, Integration, Notification, Supplier, SupplierOrder } from "@/lib/types";

type Errors = {
  sync_runs: { id: number; source: string; kind: string; status: string; message: string | null; errors_count: number; started_at: string }[];
  suppliers: Supplier[];
  supplier_orders: SupplierOrder[];
  jobs: { id: number; kind: string; attempts: number; last_error: string | null; payload: Record<string, unknown>; finished_at: string | null }[];
  notifications: Notification[];
  automation: AutomationEntry[];
  integration: Integration;
};

function Section({ title, description, count, children }: { title: string; description?: string; count: number; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            {title}
            <span className={`rounded-full px-2 py-0.5 text-xs ${count ? "bg-danger/15 text-red-300" : "bg-surface-3 text-muted-foreground"}`}>{count}</span>
          </span>
        }
        description={description}
      />
      {count ? children : <Empty title="Ошибок нет" icon={CheckCircle2} className="py-8" />}
    </Card>
  );
}

export default function ErrorsPage() {
  const { can } = useSession();
  const state = useApi<Errors>("/errors");
  const { busy, run } = useAction();
  return (
    <>
      <PageHeader
        title="Ошибки интеграций"
        description="Всё, что требует внимания: недоступные функции площадки, сбои синхронизации, закупки с неизвестным результатом, упавшие задачи."
        actions={
          <Button size="sm" onClick={state.reload}>
            <RefreshCw /> Обновить
          </Button>
        }
      />
      <Async state={state} rows={10}>
        {(d) => (
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader title={`${d.integration.title}: возможности интеграции`} description="Почему часть функций работает в режиме подсказок" />
              <ul className="divide-y divide-border">
                {Object.entries(d.integration.capabilities).map(([key, c]) => (
                  <li key={key} className="flex items-start gap-3 px-5 py-3">
                    {c.available ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-subtle" />}
                    <div className="min-w-0">
                      <p className="text-sm font-medium">
                        {c.label} <span className="font-normal text-muted-foreground">— {c.available ? "доступно через API" : "интеграция недоступна"}</span>
                      </p>
                      {c.reason && <p className="mt-0.5 text-[13px] text-muted-foreground">{c.reason}</p>}
                    </div>
                  </li>
                ))}
              </ul>
            </Card>

            <Section title="Закупки с ошибкой или неизвестным результатом" description="Неизвестный результат не повторяется автоматически: сверьте у поставщика" count={d.supplier_orders.length}>
              <Table>
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH>Закупка</TH>
                    <TH>Статус</TH>
                    <TH className="text-right">Сумма</TH>
                    <TH>Ошибка</TH>
                    <TH>Когда</TH>
                  </TR>
                </THead>
                <TBody>
                  {d.supplier_orders.map((o) => (
                    <TR key={o.id}>
                      <TD>
                        <Link href={`/suppliers/${o.supplier_id}`} className="hover:text-highlight">
                          #{o.id}
                        </Link>
                        {o.external_id && <span className="block text-xs text-muted-foreground">ID {o.external_id}</span>}
                      </TD>
                      <TD>
                        <StatusBadge map={SUPPLIER_ORDER_STATUS} value={o.status} />
                      </TD>
                      <TD className="text-right tabular-nums">{money(o.cost_rub)}</TD>
                      <TD className="max-w-md text-[13px] text-muted-foreground">{o.last_error || o.message}</TD>
                      <TD className="whitespace-nowrap text-muted-foreground">{dt(o.created_at)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </Section>

            <div className="grid gap-6 xl:grid-cols-2">
              <Section title="Синхронизация" count={d.sync_runs.length}>
                <ul className="divide-y divide-border">
                  {d.sync_runs.map((r) => (
                    <li key={r.id} className="px-5 py-3">
                      <div className="flex items-center justify-between gap-2 text-[13px]">
                        <span>
                          {r.source} · {r.kind}
                        </span>
                        <StatusBadge map={SYNC_STATUS} value={r.status} />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {dt(r.started_at)} · {r.message}
                      </p>
                    </li>
                  ))}
                </ul>
              </Section>
              <Section title="Поставщики с ошибкой" count={d.suppliers.length}>
                <ul className="divide-y divide-border">
                  {d.suppliers.map((s) => (
                    <li key={s.id} className="px-5 py-3">
                      <div className="flex items-center justify-between gap-2">
                        <Link href={`/suppliers/${s.id}`} className="text-sm hover:text-highlight">
                          {s.name}
                        </Link>
                        <StatusBadge map={SUPPLIER_STATUS} value={s.status} />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{s.last_error}</p>
                    </li>
                  ))}
                </ul>
              </Section>
            </div>

            <Section title="Фоновые задачи с ошибкой" description="После исчерпания попыток задача останавливается — повторите вручную, когда причина устранена" count={d.jobs.length}>
              <Table>
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH>Задача</TH>
                    <TH>Попыток</TH>
                    <TH>Ошибка</TH>
                    <TH>Когда</TH>
                    <TH />
                  </TR>
                </THead>
                <TBody>
                  {d.jobs.map((j) => (
                    <TR key={j.id}>
                      <TD className="font-mono text-[12.5px]">
                        {j.kind}
                        <span className="block text-[11px] text-subtle">{JSON.stringify(j.payload)}</span>
                      </TD>
                      <TD>{j.attempts}</TD>
                      <TD className="max-w-md text-[13px] text-muted-foreground">{j.last_error}</TD>
                      <TD className="whitespace-nowrap text-muted-foreground">{dt(j.finished_at)}</TD>
                      <TD className="text-right">
                        {can("settings.manage") && (
                          <Button
                            size="sm"
                            loading={busy === `j${j.id}`}
                            onClick={async () => {
                              const r = await run(`j${j.id}`, () => api.post(`/jobs/${j.id}/retry`), "Задача поставлена в очередь");
                              if (r) state.reload();
                            }}
                          >
                            <RefreshCw /> Повторить
                          </Button>
                        )}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </Section>

            <div className="grid gap-6 xl:grid-cols-2">
              <Section title="Ошибки автоматизации" count={d.automation.length}>
                <ul className="divide-y divide-border">
                  {d.automation.map((a) => (
                    <li key={a.id} className="px-5 py-3 text-[13px]">
                      <div className="flex items-center justify-between gap-2">
                        <span>
                          {a.feature} · <span className="text-muted-foreground">{a.action}</span>
                        </span>
                        <StatusBadge map={LOG_RESULT} value={a.result} />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {dt(a.created_at)} · {a.message}
                      </p>
                    </li>
                  ))}
                </ul>
              </Section>
              <Section title="Неотправленные уведомления" count={d.notifications.length}>
                <ul className="divide-y divide-border">
                  {d.notifications.map((n) => (
                    <li key={n.id} className="px-5 py-3 text-[13px]">
                      <div className="flex items-center justify-between gap-2">
                        <span>{n.title}</span>
                        <StatusBadge map={NOTIFICATION_STATUS} value={n.status} />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {dt(n.created_at)} · попыток {n.attempts} · {n.last_error}
                      </p>
                    </li>
                  ))}
                </ul>
              </Section>
            </div>
          </div>
        )}
      </Async>
    </>
  );
}
