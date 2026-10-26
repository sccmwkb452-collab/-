"use client";

import { ChevronDown, PackagePlus, RefreshCw, Search, Telescope } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Async, Empty, Notice, PageHeader, Pager } from "@/components/app/blocks";
import { FactorList } from "@/components/app/pricing-view";
import { StatusBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { ago, cn, dt, money, num } from "@/lib/format";
import { useDebounced, usePage } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { COMPLIANCE, CONFIDENCE, PRICING_STATUS } from "@/lib/status";
import type { Category, Product } from "@/lib/types";

type RankRow = { product: Product; score: string; confidence: string; factors: Record<string, unknown>; excluded_reason: string | null; computed_at: string };

type Opportunity = {
  id: number;
  supplier: string;
  supplier_code: string;
  name: string;
  category: string | null;
  price: string;
  currency: string;
  units_per_sale: number;
  cost_rub: string | null;
  min_price: string | null;
  target_price: string | null;
  status: string;
  compliance: string;
  checked_at: string | null;
  note: string;
};

function Ranking() {
  const [includeExcluded, setIncludeExcluded] = React.useState(false);
  const [page, setPage] = usePage(String(includeExcluded));
  const [open, setOpen] = React.useState<number | null>(null);
  const state = useApi<{ items: RankRow[]; total: number; page: number }>(`/research?page=${page}&include_excluded=${includeExcluded}`);
  const { busy, run } = useAction();
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
        <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
          <Switch checked={includeExcluded} onCheckedChange={setIncludeExcluded} /> Показать исключённые (запрещённые, без источника)
        </label>
        <Button
          size="sm"
          loading={busy === "re"}
          onClick={async () => {
            const r = await run("re", () => api.post<{ products: number }>("/research/recompute"), (x) => `Пересчитано товаров: ${x.products}`);
            if (r) state.reload();
          }}
        >
          <RefreshCw /> Пересчитать
        </Button>
      </div>
      <Async state={state} rows={8}>
        {(d) =>
          d.items.length ? (
            <>
              <ul className="divide-y divide-border">
                {d.items.map((r, i) => {
                  const score = Number(r.score);
                  const expanded = open === r.product.id;
                  return (
                    <li key={r.product.id}>
                      <button
                        className="flex w-full items-center gap-4 px-5 py-3.5 text-left hover:bg-white/[0.02]"
                        onClick={() => setOpen(expanded ? null : r.product.id)}
                        aria-expanded={expanded}
                      >
                        <span className="w-6 shrink-0 text-right text-sm text-subtle tabular-nums">{(d.page - 1) * 25 + i + 1}</span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">{r.product.name}</span>
                          <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            {r.product.category.name} · мин. цена {money(r.product.pricing.min_price)} · прибыль {money(r.product.pricing.expected_profit)}
                            {r.excluded_reason && <span className="text-red-300">· исключён: {r.excluded_reason}</span>}
                          </span>
                        </span>
                        <StatusBadge map={CONFIDENCE} value={r.confidence} className="hidden sm:inline-flex" />
                        <span className="w-24 shrink-0">
                          <span className="block text-right text-lg font-semibold tabular-nums">{score.toFixed(0)}</span>
                          <span className="mt-1 block h-1 overflow-hidden rounded-full bg-surface-3">
                            <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.min(100, Math.max(0, score))}%` }} />
                          </span>
                        </span>
                        <ChevronDown className={cn("size-4 shrink-0 text-subtle transition-transform", expanded && "rotate-180")} />
                      </button>
                      {expanded && (
                        <div className="grid gap-4 border-t border-border bg-surface-2/30 px-5 py-4 md:grid-cols-[1fr_240px]">
                          <FactorList factors={r.factors} />
                          <div className="flex flex-col gap-2 text-[13px] text-muted-foreground">
                            <p>Рассчитано {dt(r.computed_at)}</p>
                            <p>Факторы без данных не повышают оценку и снижают достоверность.</p>
                            <Button size="sm" asChild className="self-start">
                              <Link href={`/products/${r.product.id}`}>Открыть товар</Link>
                            </Button>
                          </div>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
              <Pager page={d.page} total={d.total} perPage={25} onPage={setPage} />
            </>
          ) : (
            <Empty title="Рейтинг пуст" icon={Telescope}>
              Рейтинг строится по товарам каталога. Создайте товары из позиций поставщиков на соседней вкладке и нажмите «Пересчитать».
            </Empty>
          )
        }
      </Async>
    </Card>
  );
}

function CreateFrom({ item }: { item: Opportunity }) {
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
        title="Создать товар"
        description={`${item.supplier}: ${item.name}`}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              disabled={!category}
              loading={busy === "c"}
              onClick={async () => {
                const p = await run("c", () => api.post<Product>("/products/from-supplier", { supplier_product_id: item.id, category_code: category }), "Товар создан");
                if (p) router.push(`/products/${p.id}`);
              }}
            >
              Создать черновик
            </Button>
          </>
        }
      >
        <Field label="Категория PlayerOK">
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

function Opportunities() {
  const { can } = useSession();
  const [q, setQ] = React.useState("");
  const query = useDebounced(q);
  const [page, setPage] = usePage(query);
  const state = useApi<{ items: Opportunity[]; total: number; page: number }>(`/research/opportunities?page=${page}&q=${encodeURIComponent(query)}`);
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по позициям поставщиков" className="pl-9" />
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
                    <TH className="text-right">Закупка</TH>
                    <TH className="text-right">Себестоимость</TH>
                    <TH className="text-right">Мин. цена</TH>
                    <TH className="text-right">Целевая</TH>
                    <TH>Оценка</TH>
                    <TH />
                  </TR>
                </THead>
                <TBody>
                  {d.items.map((o) => (
                    <TR key={o.id}>
                      <TD className="max-w-80">
                        <p className="truncate">{o.name}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {o.supplier} · цена от {ago(o.checked_at)}
                          {o.units_per_sale > 1 ? ` · за ${num(o.units_per_sale)} ед.` : ""}
                        </p>
                      </TD>
                      <TD className="text-right whitespace-nowrap tabular-nums">
                        {o.price} {o.currency}
                      </TD>
                      <TD className="text-right tabular-nums">{money(o.cost_rub)}</TD>
                      <TD className="text-right tabular-nums">{money(o.min_price)}</TD>
                      <TD className="text-right font-medium tabular-nums">{money(o.target_price)}</TD>
                      <TD>
                        <div className="flex flex-col items-start gap-1">
                          <StatusBadge map={PRICING_STATUS} value={o.status} />
                          {o.compliance !== "approved" && <StatusBadge map={COMPLIANCE} value={o.compliance} />}
                        </div>
                      </TD>
                      <TD className="text-right">{can("products.manage") && o.compliance === "approved" && <CreateFrom item={o} />}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <Pager page={d.page} total={d.total} perPage={30} onPage={setPage} />
            </>
          ) : (
            <Empty title={query ? "Ничего не найдено" : "Нет позиций без товара"} icon={Telescope}>
              {query ? "Измените запрос." : "Синхронизируйте каталоги поставщиков — здесь появятся позиции, для которых ещё нет товара."}
            </Empty>
          )
        }
      </Async>
    </Card>
  );
}

export default function ResearchPage() {
  return (
    <>
      <PageHeader
        title="Поиск товаров"
        description="Рейтинг товаров по реальным данным и позиции поставщиков, которые ещё не продаются, с расчётом минимальной и целевой цены."
      />
      <Notice className="mb-5" title="Как считается оценка">
        Спрос — по вашим завершённым продажам, а без них — только по числу предложений конкурентов, которое вы внесли вручную (это косвенный признак,
        достоверность «низкая»). Маржа — из Pricing Engine. Данных о продажах конкурентов у системы нет, и она их не выдумывает: фактор без данных
        показывается как «нет данных».
      </Notice>
      <Tabs defaultValue="ranking">
        <TabsList>
          <TabsTrigger value="ranking">Рейтинг товаров</TabsTrigger>
          <TabsTrigger value="opportunities">Позиции поставщиков</TabsTrigger>
        </TabsList>
        <TabsContent value="ranking">
          <Ranking />
        </TabsContent>
        <TabsContent value="opportunities">
          <Opportunities />
        </TabsContent>
      </Tabs>
    </>
  );
}
