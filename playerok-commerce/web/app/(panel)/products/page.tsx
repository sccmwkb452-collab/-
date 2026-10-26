"use client";

import { Download, Package, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Async, Empty, PageHeader, Pager } from "@/components/app/blocks";
import { EMPTY_PRODUCT, ProductForm, toPayload, type ProductFormValue } from "@/components/app/product-form";
import { StatusBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Input, NativeSelect } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useAction } from "@/lib/actions";
import { api, download, useApi } from "@/lib/api";
import { useDebounced, usePage } from "@/lib/hooks";
import { money, pct } from "@/lib/format";
import { useSession } from "@/lib/session";
import { COMPLIANCE, PRICING_STATUS, PRODUCT_STATUS } from "@/lib/status";
import type { Category, Paged, Product } from "@/lib/types";

function NewProduct({ categories }: { categories: Category[] }) {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [value, setValue] = React.useState<ProductFormValue>(EMPTY_PRODUCT);
  const { busy, run } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="primary">
          <Plus /> Новый товар
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Новый товар"
        description="Товар создаётся черновиком. Активировать можно только товар из разрешённой категории."
        className="max-w-2xl"
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              loading={busy === "create"}
              disabled={value.name.trim().length < 3 || !value.category_id}
              onClick={async () => {
                const p = await run("create", () => api.post<Product>("/products", toPayload(value, true)), "Товар создан");
                if (p) router.push(`/products/${p.id}`);
              }}
            >
              Создать
            </Button>
          </>
        }
      >
        <ProductForm value={value} onChange={setValue} categories={categories} creating />
      </DialogContent>
    </Dialog>
  );
}

export default function ProductsPage() {
  const { can } = useSession();
  const categories = useApi<{ items: Category[] }>("/categories");
  const [q, setQ] = React.useState("");
  const query = useDebounced(q);
  const [category, setCategory] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [page, setPage] = usePage(JSON.stringify([query, category, status]));
  const { run } = useAction();

  const qs = new URLSearchParams({ page: String(page), per_page: "25" });
  if (query) qs.set("q", query);
  if (category) qs.set("category_id", category);
  if (status) qs.set("status", status);
  const state = useApi<Paged<Product>>(`/products?${qs}`);

  return (
    <>
      <PageHeader
        title="Товары"
        description="Каталог: себестоимость, минимальная и рекомендуемая цена, остатки кодов и допустимость продажи."
        actions={
          <>
            {can("analytics.export") && (
              <Button onClick={() => run("export", () => download("/products-export?format=xlsx", "products.xlsx"))}>
                <Download /> Excel
              </Button>
            )}
            {can("products.manage") && categories.data && <NewProduct categories={categories.data.items} />}
          </>
        }
      />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Название или артикул" className="pl-9" />
          </div>
          <NativeSelect value={category} onChange={(e) => setCategory(e.target.value)} className="w-56" aria-label="Категория">
            <option value="">Все категории</option>
            {categories.data?.items.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} className="w-44" aria-label="Статус">
            <option value="">Любой статус</option>
            {Object.entries(PRODUCT_STATUS).map(([k, s]) => (
              <option key={k} value={k}>
                {s.label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <Async state={state} rows={8}>
          {(d) =>
            d.items.length ? (
              <>
                <Table>
                  <THead>
                    <TR className="hover:bg-transparent">
                      <TH>Товар</TH>
                      <TH>Статус</TH>
                      <TH className="text-right">Себестоимость</TH>
                      <TH className="text-right">Мин. цена</TH>
                      <TH className="text-right">Цена</TH>
                      <TH className="text-right">Прибыль</TH>
                      <TH>Расчёт</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {d.items.map((p) => (
                      <TR key={p.id}>
                        <TD className="max-w-80">
                          <Link href={`/products/${p.id}`} className="font-medium hover:text-highlight">
                            {p.name}
                          </Link>
                          <p className="truncate text-xs text-muted-foreground">
                            {p.sku} · {p.category.name}
                          </p>
                        </TD>
                        <TD>
                          <div className="flex flex-col items-start gap-1">
                            <StatusBadge map={PRODUCT_STATUS} value={p.status} />
                            {p.compliance_status !== "approved" && <StatusBadge map={COMPLIANCE} value={p.compliance_status} />}
                          </div>
                        </TD>
                        <TD className="text-right tabular-nums">{money(p.pricing.full_cost)}</TD>
                        <TD className="text-right tabular-nums">{money(p.pricing.min_price)}</TD>
                        <TD className="text-right font-medium tabular-nums">{money(p.pricing.current_price ?? p.pricing.recommended_price)}</TD>
                        <TD className="text-right tabular-nums">
                          {p.pricing.expected_profit ? (
                            <>
                              <span className={Number(p.pricing.expected_profit) < 0 ? "text-red-300" : "text-green-300"}>{money(p.pricing.expected_profit)}</span>
                              <span className="block text-xs text-muted-foreground">{pct(p.pricing.expected_margin_pct)}</span>
                            </>
                          ) : (
                            "—"
                          )}
                        </TD>
                        <TD>
                          <StatusBadge map={PRICING_STATUS} value={p.pricing.status} />
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
                <Pager page={d.page} total={d.total} perPage={d.per_page} onPage={setPage} />
              </>
            ) : (
              <Empty title={query || category || status ? "Ничего не найдено" : "Товаров пока нет"} icon={Package}>
                {query || category || status
                  ? "Измените фильтры."
                  : "Создайте товар вручную или из позиции поставщика в разделе «Поиск товаров» — система сразу рассчитает минимальную цену."}
              </Empty>
            )
          }
        </Async>
      </Card>
    </>
  );
}
