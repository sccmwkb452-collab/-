"use client";

import { Calculator, Plus, RefreshCw, RotateCcw, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { Suspense } from "react";

import { Async, Empty, Notice, PageHeader } from "@/components/app/blocks";
import { ConfirmAction } from "@/components/app/confirm";
import { CalculationView } from "@/components/app/pricing-view";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { dt } from "@/lib/format";
import { useDraft } from "@/lib/hooks";
import { POLICY_FIELDS } from "@/lib/pricing";
import { useSession } from "@/lib/session";
import type { Calculation, Category, Paged, Product } from "@/lib/types";

type Rules = {
  global: Record<string, string>;
  defaults: Record<string, string>;
  overrides: { id: number; scope: "category" | "product"; category_id: number | null; product_id: number | null; values: Record<string, string> }[];
  fields: string[];
};

const GROUPS: { title: string; fields: string[] }[] = [
  { title: "Пороги прибыли", fields: ["min_profit_rub", "min_margin_pct", "min_roi_pct", "target_profit_rub", "target_margin_pct"] },
  { title: "Расходы на продажу", fields: ["refund_reserve_pct", "payment_fee_pct", "withdrawal_fee_pct", "conversion_fee_pct", "other_costs_rub"] },
  { title: "Рынок и защита", fields: ["max_market_deviation_pct", "max_discount_pct", "undercut_rub", "price_step", "max_price_age_minutes", "max_market_age_hours", "max_purchase_budget_rub"] },
];

function PolicyForm({ values, onChange, placeholders, disabled }: { values: Record<string, string>; onChange: (v: Record<string, string>) => void; placeholders?: Record<string, string>; disabled?: boolean }) {
  return (
    <div className="flex flex-col gap-6">
      {GROUPS.map((g) => (
        <div key={g.title}>
          <p className="mb-3 text-[13px] font-medium text-muted-foreground">{g.title}</p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {g.fields.map((f) => (
              <Field key={f} label={`${POLICY_FIELDS[f].label}, ${POLICY_FIELDS[f].unit}`} hint={POLICY_FIELDS[f].hint}>
                <Input
                  inputMode="decimal"
                  value={values[f] ?? ""}
                  placeholder={placeholders?.[f]}
                  onChange={(e) => onChange({ ...values, [f]: e.target.value.replace(",", ".") })}
                  disabled={disabled}
                />
              </Field>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function OverrideDialog({
  rules,
  categories,
  initialProduct,
  onDone,
}: {
  rules: Rules;
  categories: Category[];
  initialProduct?: string | null;
  onDone: () => void;
}) {
  const [open, setOpen] = React.useState(Boolean(initialProduct));
  const [scope, setScope] = React.useState<"category" | "product">(initialProduct ? "product" : "category");
  const [ref, setRef] = React.useState(initialProduct ?? "");
  const products = useApi<Paged<Product>>(open && scope === "product" ? "/products?per_page=100" : null);
  const existing = rules.overrides.find((o) => o.scope === scope && String(scope === "category" ? o.category_id : o.product_id) === ref);
  const [values, setValues] = React.useState<Record<string, string>>({});
  const shown = Object.keys(values).length ? values : existing?.values ?? {};
  const { busy, run } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="primary">
          <Plus /> Правило для категории или товара
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Отдельные правила"
        description="Заполните только то, что отличается от глобальных правил. Пустое поле — берётся значение уровнем выше."
        className="max-w-3xl"
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              disabled={!ref}
              loading={busy === "s"}
              onClick={async () => {
                const clean = Object.fromEntries(Object.entries(shown).filter(([, v]) => String(v).trim() !== ""));
                const r = await run("s", () => api.put(`/pricing/rules/${scope}/${ref}`, { values: clean }), "Правило сохранено — цены будут пересчитаны");
                if (r) {
                  setOpen(false);
                  setValues({});
                  onDone();
                }
              }}
            >
              <Save /> Сохранить
            </Button>
          </>
        }
      >
        <div className="mb-5 grid gap-4 sm:grid-cols-2">
          <Field label="Для чего">
            <NativeSelect
              value={scope}
              onChange={(e) => {
                setScope(e.target.value as "category" | "product");
                setRef("");
                setValues({});
              }}
            >
              <option value="category">Категория</option>
              <option value="product">Товар</option>
            </NativeSelect>
          </Field>
          <Field label={scope === "category" ? "Категория" : "Товар"}>
            <NativeSelect
              value={ref}
              onChange={(e) => {
                setRef(e.target.value);
                setValues({});
              }}
            >
              <option value="">Выберите…</option>
              {scope === "category"
                ? categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))
                : products.data?.items.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
            </NativeSelect>
          </Field>
        </div>
        <PolicyForm values={shown} onChange={setValues} placeholders={rules.global} />
      </DialogContent>
    </Dialog>
  );
}

function RulesTab({ initialProduct }: { initialProduct: string | null }) {
  const { can } = useSession();
  const state = useApi<Rules>("/pricing/rules");
  const categories = useApi<{ items: Category[] }>("/categories");
  const [draft, setDraft] = useDraft(state.data, (r) => ({ ...r.global }));
  const { busy, run } = useAction();
  const manage = can("pricing.manage");
  const catName = (id: number | null) => categories.data?.items.find((c) => c.id === id)?.name ?? `#${id}`;

  return (
    <Async state={state} rows={8}>
      {(rules) => (
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader
              title="Глобальные правила"
              description="Действуют для всех товаров, если для категории или товара не задано своё. После сохранения все цены пересчитываются."
              actions={
                manage && (
                  <Button size="sm" variant="ghost" onClick={() => setDraft({ ...rules.defaults })}>
                    <RotateCcw /> Значения по умолчанию
                  </Button>
                )
              }
            />
            <CardBody>
              {draft && <PolicyForm values={draft} onChange={setDraft} disabled={!manage} />}
              {manage && draft && (
                <div className="mt-6 flex gap-2">
                  <Button
                    variant="primary"
                    loading={busy === "g"}
                    onClick={async () => {
                      const r = await run("g", () => api.put("/pricing/rules/global", { values: draft }), "Глобальные правила сохранены — цены пересчитываются");
                      if (r) state.reload();
                    }}
                  >
                    <Save /> Сохранить
                  </Button>
                  <Button onClick={() => setDraft({ ...rules.global })}>Отменить изменения</Button>
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Правила категорий и товаров"
              description="Приоритет: товар → категория → глобальные"
              actions={manage && categories.data && <OverrideDialog rules={rules} categories={categories.data.items} initialProduct={initialProduct} onDone={state.reload} />}
            />
            {rules.overrides.length ? (
              <Table>
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH>Для чего</TH>
                    <TH>Изменённые значения</TH>
                    <TH />
                  </TR>
                </THead>
                <TBody>
                  {rules.overrides.map((o) => (
                    <TR key={o.id}>
                      <TD className="whitespace-nowrap">
                        {o.scope === "category" ? (
                          <>Категория «{catName(o.category_id)}»</>
                        ) : (
                          <Link href={`/products/${o.product_id}`} className="hover:text-highlight">
                            Товар #{o.product_id}
                          </Link>
                        )}
                      </TD>
                      <TD className="text-[13px] text-muted-foreground">
                        {Object.entries(o.values)
                          .map(([k, v]) => `${POLICY_FIELDS[k]?.label ?? k}: ${v} ${POLICY_FIELDS[k]?.unit ?? ""}`)
                          .join(" · ") || "—"}
                      </TD>
                      <TD className="text-right">
                        {manage && (
                          <ConfirmAction
                            label=""
                            icon={<Trash2 />}
                            variant="ghost"
                            size="icon-sm"
                            title="Удалить правило?"
                            description="Начнут действовать правила уровнем выше."
                            confirmVariant="danger"
                            confirmLabel="Удалить"
                            onConfirm={async () => {
                              const r = await run("d", () => api.del(`/pricing/rules/${o.id}`), "Правило удалено");
                              if (r) state.reload();
                              return r;
                            }}
                          />
                        )}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            ) : (
              <Empty title="Отдельных правил нет">Все товары считаются по глобальным правилам.</Empty>
            )}
          </Card>
        </div>
      )}
    </Async>
  );
}

function CalculatorTab() {
  const [v, setV] = React.useState({ purchase_price: "", currency: "RUB", marketplace_commission_pct: "10", supplier_fee_pct: "0", sale_price: "", competitor_min: "" });
  const [result, setResult] = React.useState<{ result: Calculation; fx_rate: string | null; fx_date: string | null }>();
  const { busy, run } = useAction();
  const num = (s: string) => (s.trim() ? s.trim().replace(",", ".") : null);
  return (
    <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
      <Card>
        <CardHeader title="Калькулятор" description="По текущим глобальным правилам и курсу ЦБ" />
        <CardBody className="flex flex-col gap-4">
          <div className="grid grid-cols-[1fr_110px] gap-3">
            <Field label="Закупочная цена">
              <Input inputMode="decimal" value={v.purchase_price} onChange={(e) => setV({ ...v, purchase_price: e.target.value })} autoFocus />
            </Field>
            <Field label="Валюта">
              <NativeSelect value={v.currency} onChange={(e) => setV({ ...v, currency: e.target.value })}>
                {["RUB", "USD", "EUR", "CNY", "KZT", "TRY"].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </NativeSelect>
            </Field>
          </div>
          <Field label="Комиссия PlayerOK, %" hint="Своя для каждой категории — см. «Товары» → категория">
            <Input inputMode="decimal" value={v.marketplace_commission_pct} onChange={(e) => setV({ ...v, marketplace_commission_pct: e.target.value })} />
          </Field>
          <Field label="Комиссия поставщика, %">
            <Input inputMode="decimal" value={v.supplier_fee_pct} onChange={(e) => setV({ ...v, supplier_fee_pct: e.target.value })} />
          </Field>
          <Field label="Проверить цену продажи, ₽" hint="Необязательно">
            <Input inputMode="decimal" value={v.sale_price} onChange={(e) => setV({ ...v, sale_price: e.target.value })} />
          </Field>
          <Field label="Минимальная цена конкурента, ₽" hint="Необязательно">
            <Input inputMode="decimal" value={v.competitor_min} onChange={(e) => setV({ ...v, competitor_min: e.target.value })} />
          </Field>
          <Button
            variant="primary"
            disabled={!Number(num(v.purchase_price))}
            loading={busy === "calc"}
            onClick={async () => {
              const r = await run("calc", () =>
                api.post<NonNullable<typeof result>>("/pricing/calculate", {
                  purchase_price: num(v.purchase_price),
                  currency: v.currency,
                  marketplace_commission_pct: num(v.marketplace_commission_pct) ?? "0",
                  supplier_fee_pct: num(v.supplier_fee_pct) ?? "0",
                  sale_price: num(v.sale_price),
                  competitor_min: num(v.competitor_min),
                }),
              );
              if (r) setResult(r);
            }}
          >
            <Calculator /> Рассчитать
          </Button>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="Результат" />
        <CardBody>
          {result ? (
            <CalculationView calc={result.result} currency={v.currency} fxRate={result.fx_rate} costSource={undefined} />
          ) : (
            <Empty title="Введите закупочную цену" icon={Calculator}>
              Калькулятор покажет минимальную цену без убытка, целевую и рекомендуемую цену, а также прибыль, маржу и ROI.
            </Empty>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function RatesTab() {
  const { can } = useSession();
  const state = useApi<{ items: { currency: string; rate: string; date: string | null }[]; source: string }>("/fx");
  const { busy, run } = useAction();
  return (
    <Card className="max-w-2xl">
      <CardHeader
        title="Курсы валют"
        description={state.data?.source}
        actions={
          can("pricing.manage") && (
            <Button
              size="sm"
              loading={busy === "fx"}
              onClick={async () => {
                const r = await run("fx", () => api.post<{ run: { message: string } }>("/fx/sync"), (x) => x.run.message);
                if (r) state.reload();
              }}
            >
              <RefreshCw /> Обновить с ЦБ РФ
            </Button>
          )
        }
      />
      <Async state={state}>
        {(d) =>
          d.items.length ? (
            <Table>
              <THead>
                <TR className="hover:bg-transparent">
                  <TH>Валюта</TH>
                  <TH className="text-right">Курс, ₽</TH>
                  <TH>На дату</TH>
                </TR>
              </THead>
              <TBody>
                {d.items.map((r) => (
                  <TR key={r.currency}>
                    <TD>{r.currency}</TD>
                    <TD className="text-right tabular-nums">{Number(r.rate).toLocaleString("ru-RU", { maximumFractionDigits: 4 })}</TD>
                    <TD className="text-muted-foreground">{dt(r.date, false)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <Empty title="Курсов ещё нет">
              Воркер загружает курсы ЦБ РФ каждый день. Без курса цены в валюте не рассчитываются — система не подставляет курс «на глаз».
            </Empty>
          )
        }
      </Async>
    </Card>
  );
}

function PricingView() {
  const params = useSearchParams();
  const product = params.get("product");
  return (
    <>
      <PageHeader
        title="Прибыль и цены"
        description="Правила минимальной и рекомендуемой цены, калькулятор и курсы валют. Продажа ниже минимальной цены блокируется."
      />
      <Notice className="mb-5" title="Как считается минимальная цена">
        Полная себестоимость = закупка + комиссия поставщика + конвертация + прочие расходы. Минимальная цена — наибольшая из трёх: обеспечивающая
        минимальную прибыль, минимальную маржу и минимальный ROI после комиссии PlayerOK, платёжной комиссии, резерва на возвраты и комиссии вывода.
      </Notice>
      <Tabs defaultValue="rules">
        <TabsList>
          <TabsTrigger value="rules">Правила</TabsTrigger>
          <TabsTrigger value="calc">Калькулятор</TabsTrigger>
          <TabsTrigger value="fx">Курсы валют</TabsTrigger>
        </TabsList>
        <TabsContent value="rules">
          <RulesTab initialProduct={product} />
        </TabsContent>
        <TabsContent value="calc">
          <CalculatorTab />
        </TabsContent>
        <TabsContent value="fx">
          <RatesTab />
        </TabsContent>
      </Tabs>
    </>
  );
}

export default function PricingPage() {
  return (
    <Suspense>
      <PricingView />
    </Suspense>
  );
}
