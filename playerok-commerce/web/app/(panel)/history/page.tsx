"use client";

import { ScrollText, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Async, Empty, PageHeader, Pager } from "@/components/app/blocks";
import { StatusBadge } from "@/components/app/status";
import { Card } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/lib/api";
import { dt } from "@/lib/format";
import { useDebounced, usePage } from "@/lib/hooks";
import { LOG_RESULT } from "@/lib/status";
import type { AuditEntry, AutomationEntry, AutoItem, Paged } from "@/lib/types";

const ACTOR: Record<string, string> = { web: "панель", telegram: "бот", cli: "консоль", system: "система", worker: "воркер" };

function details(d: Record<string, unknown>) {
  const entries = Object.entries(d ?? {});
  if (!entries.length) return "";
  return entries
    .slice(0, 6)
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}

function AuditTab() {
  const [q, setQ] = React.useState("");
  const query = useDebounced(q);
  const [page, setPage] = usePage(query);
  const state = useApi<Paged<AuditEntry>>(`/audit?page=${page}&per_page=50&q=${encodeURIComponent(query)}`);
  return (
    <Card>
      <div className="flex items-center gap-3 border-b border-border px-5 py-3">
        <div className="relative max-w-md flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Действие, пользователь или ID объекта" className="pl-9" />
        </div>
      </div>
      <Async state={state} rows={10}>
        {(d) =>
          d.items.length ? (
            <>
              <Table>
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH>Когда</TH>
                    <TH>Кто</TH>
                    <TH>Действие</TH>
                    <TH>Объект</TH>
                    <TH>Подробности</TH>
                  </TR>
                </THead>
                <TBody>
                  {d.items.map((a) => (
                    <TR key={a.id}>
                      <TD className="whitespace-nowrap text-muted-foreground">{dt(a.created_at)}</TD>
                      <TD className="whitespace-nowrap">
                        {a.actor ?? "—"} <span className="text-xs text-muted-foreground">({ACTOR[a.actor_type] ?? a.actor_type})</span>
                        {a.ip && <span className="block text-xs text-subtle">{a.ip}</span>}
                      </TD>
                      <TD className="font-mono text-[12.5px]">{a.action}</TD>
                      <TD className="whitespace-nowrap text-muted-foreground">
                        {a.entity_type === "order" && a.entity_id ? (
                          <Link href={`/orders/${a.entity_id}`} className="text-highlight hover:underline">
                            заказ #{a.entity_id}
                          </Link>
                        ) : a.entity_type === "product" && a.entity_id ? (
                          <Link href={`/products/${a.entity_id}`} className="text-highlight hover:underline">
                            товар #{a.entity_id}
                          </Link>
                        ) : a.entity_type ? (
                          `${a.entity_type} #${a.entity_id ?? ""}`
                        ) : (
                          "—"
                        )}
                      </TD>
                      <TD className="max-w-96 truncate text-xs text-muted-foreground" title={details(a.details)}>
                        {details(a.details)}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <Pager page={d.page} total={d.total} perPage={d.per_page} onPage={setPage} />
            </>
          ) : (
            <Empty title="Записей нет" icon={ScrollText} />
          )
        }
      </Async>
    </Card>
  );
}

function AutomationTab() {
  const features = useApi<{ items: AutoItem[] }>("/autosettings");
  const [feature, setFeature] = React.useState("");
  const [result, setResult] = React.useState("");
  const [page, setPage] = usePage(feature + result);
  const qs = new URLSearchParams({ page: String(page), per_page: "50" });
  if (feature) qs.set("feature", feature);
  if (result) qs.set("result", result);
  const state = useApi<Paged<AutomationEntry>>(`/automation-logs?${qs}`);
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3">
        <NativeSelect value={feature} onChange={(e) => setFeature(e.target.value)} className="w-64" aria-label="Функция">
          <option value="">Все функции</option>
          {features.data?.items.map((f) => (
            <option key={f.code} value={f.code}>
              {f.title}
            </option>
          ))}
          <option value="orders">Обработка заказов</option>
        </NativeSelect>
        <NativeSelect value={result} onChange={(e) => setResult(e.target.value)} className="w-56" aria-label="Результат">
          <option value="">Любой результат</option>
          {Object.entries(LOG_RESULT).map(([k, s]) => (
            <option key={k} value={k}>
              {s.label}
            </option>
          ))}
        </NativeSelect>
      </div>
      <Async state={state} rows={10}>
        {(d) =>
          d.items.length ? (
            <>
              <Table>
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH>Когда</TH>
                    <TH>Функция</TH>
                    <TH>Результат</TH>
                    <TH>Что произошло</TH>
                  </TR>
                </THead>
                <TBody>
                  {d.items.map((a) => (
                    <TR key={a.id}>
                      <TD className="whitespace-nowrap text-muted-foreground">{dt(a.created_at)}</TD>
                      <TD className="whitespace-nowrap">
                        {features.data?.items.find((f) => f.code === a.feature)?.title ?? a.feature}
                        <span className="block font-mono text-[11px] text-subtle">{a.action}</span>
                      </TD>
                      <TD>
                        <StatusBadge map={LOG_RESULT} value={a.result} />
                      </TD>
                      <TD className="max-w-xl text-[13px]">
                        {a.message}
                        {a.order_id && (
                          <Link href={`/orders/${a.order_id}`} className="ml-2 text-xs text-highlight hover:underline">
                            заказ
                          </Link>
                        )}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <Pager page={d.page} total={d.total} perPage={d.per_page} onPage={setPage} />
            </>
          ) : (
            <Empty title="Записей нет" icon={ScrollText} />
          )
        }
      </Async>
    </Card>
  );
}

export default function HistoryPage() {
  return (
    <>
      <PageHeader
        title="Журнал операций"
        description="Кто, когда и что сделал: действия сотрудников и все шаги автоматизации. Секреты и полные коды в журнал не записываются."
      />
      <Tabs defaultValue="audit">
        <TabsList>
          <TabsTrigger value="audit">Действия пользователей</TabsTrigger>
          <TabsTrigger value="automation">Автоматизация</TabsTrigger>
        </TabsList>
        <TabsContent value="audit">
          <AuditTab />
        </TabsContent>
        <TabsContent value="automation">
          <AutomationTab />
        </TabsContent>
      </Tabs>
    </>
  );
}
