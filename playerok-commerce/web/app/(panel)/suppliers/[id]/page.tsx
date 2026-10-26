"use client";

import { ArrowLeft, KeyRound, PackagePlus, PlugZap, RefreshCw, Save, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";

import { Async, Empty, KV, Notice, PageHeader, Pager } from "@/components/app/blocks";
import { ConfirmAction } from "@/components/app/confirm";
import { StatusBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { ago, dt, money, num } from "@/lib/format";
import { useDebounced, useDraft, usePage } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { COMPLIANCE, PURCHASE_MODE, SUPPLIER_ORDER_STATUS, SUPPLIER_STATUS } from "@/lib/status";
import type { Category, Paged, Product, Supplier, SupplierProduct } from "@/lib/types";

function toLimits(s: Supplier) {
  return {
    purchase_mode: s.purchase_mode,
    max_single_purchase: s.max_single_purchase,
    daily_limit: s.daily_limit,
    max_operations_per_day: String(s.max_operations_per_day),
    fee_pct: s.fee_pct,
    fee_fixed: s.fee_fixed,
  };
}

function Credentials({ s, onDone }: { s: Supplier; onDone: () => void }) {
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [result, setResult] = React.useState<{ ok: boolean; message: string }>();
  const { busy, run } = useAction();
  const fields = s.credentials ?? [];
  if (!fields.length) {
    return <p className="text-sm text-muted-foreground">Ключи доступа не нужны: адаптер работает с публичными данными или вручную.</p>;
  }
  return (
    <div className="flex flex-col gap-4">
      <Notice>
        Значения шифруются на сервере и больше нигде не показываются — только последние символы. Переменная окружения на сервере имеет приоритет
        над значением из панели.
      </Notice>
      {fields.map((f) => (
        <Field
          key={f.name}
          label={f.label}
          hint={
            f.source
              ? `Задано: ${f.source === "env" ? `переменной ${f.env}` : "в панели"}${f.preview ? ` (${f.preview})` : ""}. ${f.help}`
              : `Не задано. ${f.help} Переменная окружения: ${f.env}`
          }
        >
          <Input
            type={f.secret ? "password" : "text"}
            autoComplete="off"
            value={values[f.name] ?? ""}
            onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
            placeholder={f.source ? "Оставьте пустым, чтобы не менять" : ""}
          />
        </Field>
      ))}
      {result && <Notice tone={result.ok ? "success" : "danger"}>{result.message}</Notice>}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="primary"
          disabled={!Object.values(values).some((v) => v.trim())}
          loading={busy === "save"}
          onClick={async () => {
            const clean = Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim()));
            const r = await run("save", () => api.put<{ ok: boolean; message: string }>(`/suppliers/${s.id}/credentials`, { values: clean }));
            if (r) {
              setResult(r);
              setValues({});
              onDone();
            }
          }}
        >
          <KeyRound /> Сохранить и проверить
        </Button>
        {fields.some((f) => f.source === "db") && (
          <ConfirmAction
            label="Удалить ключи из панели"
            icon={<Trash2 />}
            variant="danger-soft"
            title="Удалить сохранённые ключи?"
            description="Закупки через API этого поставщика станут невозможны, пока ключи не будут заданы снова."
            confirmVariant="danger"
            confirmLabel="Удалить"
            onConfirm={async () => {
              const r = await run("del", () => api.del(`/suppliers/${s.id}/credentials`), "Ключи удалены");
              if (r) onDone();
              return r;
            }}
          />
        )}
      </div>
    </div>
  );
}

function CreateProduct({ sp }: { sp: SupplierProduct }) {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const categories = useApi<{ items: Category[] }>(open ? "/categories" : null);
  const [category, setCategory] = React.useState("");
  const { busy, run } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="ghost">
          <PackagePlus /> Товар
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Создать товар из позиции"
        description={`${sp.name} — ${sp.price} ${sp.currency}`}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              disabled={!category}
              loading={busy === "c"}
              onClick={async () => {
                const p = await run("c", () => api.post<Product>("/products/from-supplier", { supplier_product_id: sp.id, category_code: category }), "Товар создан");
                if (p) router.push(`/products/${p.id}`);
              }}
            >
              Создать черновик
            </Button>
          </>
        }
      >
        <Field label="Категория PlayerOK" hint="Цена будет рассчитана сразу; товар создаётся черновиком">
          <NativeSelect value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Выберите…</option>
            {categories.data?.items.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </DialogContent>
    </Dialog>
  );
}

function Catalog({ s }: { s: Supplier }) {
  const { can } = useSession();
  const [q, setQ] = React.useState("");
  const query = useDebounced(q);
  const [page, setPage] = usePage(query);
  const state = useApi<Paged<SupplierProduct>>(`/suppliers/${s.id}/products?page=${page}&per_page=50&q=${encodeURIComponent(query)}`);
  const { run } = useAction();
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по каталогу" className="pl-9" />
        </div>
      </div>
      <Async state={state} rows={8}>
        {(d) =>
          d.items.length ? (
            <>
              <Table>
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH>Позиция</TH>
                    <TH className="text-right">Цена</TH>
                    <TH>Допустимость</TH>
                    <TH>Обновлена</TH>
                    <TH />
                  </TR>
                </THead>
                <TBody>
                  {d.items.map((sp) => (
                    <TR key={sp.id}>
                      <TD className="max-w-96">
                        <p className="truncate">{sp.name}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {sp.external_id}
                          {sp.category ? ` · ${sp.category}` : ""}
                          {sp.min_quantity ? ` · от ${num(sp.min_quantity)}` : ""}
                          {!sp.available ? " · недоступна" : ""}
                        </p>
                      </TD>
                      <TD className="text-right whitespace-nowrap tabular-nums">
                        {sp.price} {sp.currency}
                        {sp.price_unit > 1 && <span className="block text-xs text-muted-foreground">за {num(sp.price_unit)}</span>}
                      </TD>
                      <TD>
                        {can("suppliers.manage") ? (
                          <NativeSelect
                            value={sp.compliance_status}
                            className="h-8 w-52 text-[13px]"
                            aria-label="Допустимость"
                            onChange={async (e) => {
                              const r = await run("c", () => api.patch(`/supplier-products/${sp.id}`, { compliance_status: e.target.value }), "Сохранено");
                              if (r) state.reload();
                            }}
                          >
                            {Object.entries(COMPLIANCE).map(([k, c]) => (
                              <option key={k} value={k}>
                                {c.label}
                              </option>
                            ))}
                          </NativeSelect>
                        ) : (
                          <StatusBadge map={COMPLIANCE} value={sp.compliance_status} />
                        )}
                      </TD>
                      <TD className="whitespace-nowrap text-muted-foreground">{ago(sp.last_seen_at)}</TD>
                      <TD className="text-right">{can("products.manage") && sp.compliance_status === "approved" && <CreateProduct sp={sp} />}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <Pager page={d.page} total={d.total} perPage={d.per_page} onPage={setPage} />
            </>
          ) : (
            <Empty title={query ? "Ничего не найдено" : "Каталог пуст"}>
              {query ? "Измените запрос." : "Нажмите «Синхронизировать каталог». Для поставщиков без API позиции не загружаются."}
            </Empty>
          )
        }
      </Async>
    </Card>
  );
}

export default function SupplierPage() {
  const { id } = useParams<{ id: string }>();
  const state = useApi<Supplier>(`/suppliers/${id}`);
  const { can } = useSession();
  const { busy, run } = useAction();
  const [limits, setLimits] = useDraft(state.data, toLimits);

  return (
    <Async state={state} rows={10}>
      {(s) => {
        const manage = can("suppliers.manage");
        const blocked = s.status === "blocked_by_policy";
        return (
          <>
            <Link href="/suppliers" className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground">
              <ArrowLeft className="size-4" /> Все поставщики
            </Link>
            <PageHeader
              title={s.name}
              description={s.adapter_description}
              actions={
                manage &&
                !blocked && (
                  <>
                    <Button
                      size="sm"
                      loading={busy === "check"}
                      onClick={async () => {
                        const r = await run("check", () => api.post<{ ok: boolean; message: string }>(`/suppliers/${id}/check`), (x) => (x.ok ? x.message : undefined));
                        if (r && !r.ok) {
                          const { toast } = await import("sonner");
                          toast.error(r.message);
                        }
                        state.reload();
                      }}
                    >
                      <PlugZap /> Проверить подключение
                    </Button>
                    {s.capabilities.price_list && (
                      <Button
                        size="sm"
                        variant="primary"
                        loading={busy === "sync"}
                        onClick={async () => {
                          const r = await run(
                            "sync",
                            () => api.post<{ run: { status: string; message: string } | null }>(`/suppliers/${id}/sync`),
                            (x) => x.run?.message ?? "Синхронизация пропущена: слишком рано после предыдущей",
                          );
                          if (r) state.reload();
                        }}
                      >
                        <RefreshCw /> Синхронизировать каталог
                      </Button>
                    )}
                  </>
                )
              }
            >
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge map={SUPPLIER_STATUS} value={s.status} />
                <span className="text-[13px] text-muted-foreground">
                  проверка {ago(s.last_check_at)} · синхронизация {ago(s.last_sync_at)}
                </span>
              </div>
            </PageHeader>

            {s.status_reason && (
              <Notice tone={blocked ? "danger" : "info"} className="mb-5">
                {s.status_reason}
              </Notice>
            )}
            {s.last_error && (
              <Notice tone="danger" title="Последняя ошибка" className="mb-5">
                {s.last_error}
              </Notice>
            )}

            <Tabs defaultValue="settings">
              <TabsList>
                <TabsTrigger value="settings">Режим и лимиты</TabsTrigger>
                <TabsTrigger value="catalog">Каталог</TabsTrigger>
                <TabsTrigger value="orders">Закупки</TabsTrigger>
                <TabsTrigger value="about">Проверка поставщика</TabsTrigger>
              </TabsList>

              <TabsContent value="settings" className="grid gap-6 xl:grid-cols-2">
                <Card>
                  <CardHeader title="Режим закупки и лимиты" description={`Сегодня: ${money(s.spent_today_rub)}, операций ${s.operations_today ?? 0}`} />
                  <CardBody>
                    {limits && (
                      <div className="grid gap-4 sm:grid-cols-2">
                        <Field label="Режим" hint={PURCHASE_MODE[limits.purchase_mode]?.hint} className="sm:col-span-2">
                          <NativeSelect
                            value={limits.purchase_mode}
                            onChange={(e) => setLimits({ ...limits, purchase_mode: e.target.value })}
                            disabled={!manage || blocked}
                          >
                            {Object.entries(PURCHASE_MODE).map(([k, m]) => (
                              <option key={k} value={k} disabled={(k === "confirm" || k === "auto") && !s.capabilities.purchase}>
                                {m.label}
                                {(k === "confirm" || k === "auto") && !s.capabilities.purchase ? " — нет API закупки" : ""}
                              </option>
                            ))}
                          </NativeSelect>
                        </Field>
                        <Field label="Лимит одной закупки, ₽" hint="0 — запрет автоматических закупок">
                          <Input inputMode="decimal" value={limits.max_single_purchase} onChange={(e) => setLimits({ ...limits, max_single_purchase: e.target.value })} disabled={!manage || blocked} />
                        </Field>
                        <Field label="Суточный лимит, ₽">
                          <Input inputMode="decimal" value={limits.daily_limit} onChange={(e) => setLimits({ ...limits, daily_limit: e.target.value })} disabled={!manage || blocked} />
                        </Field>
                        <Field label="Операций в сутки, не больше">
                          <Input
                            inputMode="numeric"
                            value={limits.max_operations_per_day}
                            onChange={(e) => setLimits({ ...limits, max_operations_per_day: e.target.value.replace(/\D/g, "") })}
                            disabled={!manage || blocked}
                          />
                        </Field>
                        <Field label="Комиссия поставщика, %">
                          <Input inputMode="decimal" value={limits.fee_pct} onChange={(e) => setLimits({ ...limits, fee_pct: e.target.value })} disabled={!manage || blocked} />
                        </Field>
                        <Field label="Фиксированная комиссия, ₽">
                          <Input inputMode="decimal" value={limits.fee_fixed} onChange={(e) => setLimits({ ...limits, fee_fixed: e.target.value })} disabled={!manage || blocked} />
                        </Field>
                        {manage && !blocked && (
                          <div className="flex gap-2 sm:col-span-2">
                            <Button
                              variant="primary"
                              loading={busy === "limits"}
                              onClick={async () => {
                                const body = {
                                  ...limits,
                                  max_single_purchase: limits.max_single_purchase.replace(",", "."),
                                  daily_limit: limits.daily_limit.replace(",", "."),
                                  fee_pct: limits.fee_pct.replace(",", "."),
                                  fee_fixed: limits.fee_fixed.replace(",", "."),
                                  max_operations_per_day: Number(limits.max_operations_per_day) || 0,
                                };
                                const r = await run("limits", () => api.patch(`/suppliers/${id}`, body), "Настройки поставщика сохранены");
                                if (r) state.reload();
                              }}
                            >
                              <Save /> Сохранить
                            </Button>
                            <Button onClick={() => setLimits(toLimits(s))}>Сбросить</Button>
                          </div>
                        )}
                      </div>
                    )}
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="Ключи доступа" />
                  <CardBody>{manage ? <Credentials s={s} onDone={state.reload} /> : <p className="text-sm text-muted-foreground">Нет прав на изменение.</p>}</CardBody>
                </Card>
              </TabsContent>

              <TabsContent value="catalog">
                <Catalog s={s} />
              </TabsContent>

              <TabsContent value="orders">
                <Card>
                  <CardHeader title="Последние закупки" description="Неизвестный результат (тайм-аут) никогда не повторяется автоматически — его нужно сверить" />
                  {s.orders?.length ? (
                    <Table>
                      <THead>
                        <TR className="hover:bg-transparent">
                          <TH>№</TH>
                          <TH>Статус</TH>
                          <TH className="text-right">Стоимость</TH>
                          <TH>ID у поставщика</TH>
                          <TH>Создана</TH>
                        </TR>
                      </THead>
                      <TBody>
                        {s.orders.map((o) => (
                          <TR key={o.id}>
                            <TD>
                              #{o.id} {o.is_test && <span className="text-xs text-yellow-300">имитация</span>}
                            </TD>
                            <TD>
                              <StatusBadge map={SUPPLIER_ORDER_STATUS} value={o.status} />
                              {(o.last_error || o.message) && <p className="mt-1 max-w-80 truncate text-xs text-muted-foreground">{o.last_error || o.message}</p>}
                            </TD>
                            <TD className="text-right tabular-nums">{o.cost_rub ? money(o.cost_rub) : o.cost ? `${o.cost} ${o.currency}` : "—"}</TD>
                            <TD className="text-muted-foreground">{o.external_id ?? "—"}</TD>
                            <TD className="whitespace-nowrap text-muted-foreground">{dt(o.created_at)}</TD>
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                  ) : (
                    <Empty title="Закупок не было" />
                  )}
                </Card>
              </TabsContent>

              <TabsContent value="about" className="grid gap-6 xl:grid-cols-2">
                <Card>
                  <CardHeader title="Интеграция" />
                  <CardBody>
                    <KV
                      items={[
                        ["Метод", s.integration_method],
                        ["Валюта", s.currency],
                        ["Категории", s.categories.join(", ") || "—"],
                        ["Возвраты", s.refund_policy],
                        ["Правила", s.policy_note],
                        ["Сайт", s.website ? <a key="w" href={s.website} target="_blank" rel="noreferrer noopener" className="text-highlight hover:underline">{s.website}</a> : "—"],
                      ]}
                    />
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="Проверка допустимости" description={s.verification?.checked_at ? `Проверено ${s.verification.checked_at}` : undefined} />
                  <CardBody className="flex flex-col gap-4 text-[13px]">
                    {s.verification?.facts?.length ? (
                      <div>
                        <p className="mb-1 font-medium">Подтверждённые факты</p>
                        <ul className="list-disc pl-5 text-muted-foreground">
                          {s.verification.facts.map((f) => (
                            <li key={f}>{f}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {s.verification?.unverified?.length ? (
                      <div>
                        <p className="mb-1 font-medium">Не подтверждено</p>
                        <ul className="list-disc pl-5 text-yellow-200/80">
                          {s.verification.unverified.map((f) => (
                            <li key={f}>{f}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {s.verification?.sources?.length ? (
                      <div>
                        <p className="mb-1 font-medium">Источники</p>
                        <ul className="flex flex-col gap-0.5">
                          {s.verification.sources.map((u) => (
                            <li key={u}>
                              <a href={u} target="_blank" rel="noreferrer noopener" className="break-all text-highlight hover:underline">
                                {u}
                              </a>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </CardBody>
                </Card>
              </TabsContent>
            </Tabs>
          </>
        );
      }}
    </Async>
  );
}
