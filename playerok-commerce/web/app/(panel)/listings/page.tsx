"use client";

import { Archive, Download, FileText, Pause, Play, Plus, Search, Send, Wand2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Async, Empty, Notice, PageHeader, Pager } from "@/components/app/blocks";
import { StatusBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useAction } from "@/lib/actions";
import { api, download, useApi } from "@/lib/api";
import { dt, money } from "@/lib/format";
import { useDebounced, usePage } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { LISTING_STATUS } from "@/lib/status";
import type { ExportPayload, Listing, Paged, Product } from "@/lib/types";

type BulkResult = { ok: number[]; errors: Record<string, string> } | { needs_confirmation: true; first_time: boolean; previews: (ExportPayload & { id: number; status: string })[] };

function NewListing() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const products = useApi<Paged<Product>>(open ? "/products?status=active&per_page=100" : null);
  const [productId, setProductId] = React.useState("");
  const [strategy, setStrategy] = React.useState("recommended");
  const { busy, run } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="primary">
          <Plus /> Новое объявление
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Новое объявление"
        description="Текст и цена заполнятся из товара; перед публикацией вы проверите предпросмотр."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              disabled={!productId}
              loading={busy === "c"}
              onClick={async () => {
                const l = await run("c", () => api.post<Listing>("/listings", { product_id: Number(productId), price_strategy: strategy }), "Черновик создан");
                if (l) router.push(`/listings/${l.id}`);
              }}
            >
              Создать черновик
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="Товар" hint="Только активные товары из разрешённых категорий">
            <NativeSelect value={productId} onChange={(e) => setProductId(e.target.value)}>
              <option value="">Выберите…</option>
              {products.data?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — {money(p.pricing.recommended_price)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Цена">
            <NativeSelect value={strategy} onChange={(e) => setStrategy(e.target.value)}>
              <option value="recommended">Рекомендуемая</option>
              <option value="target">Целевая</option>
              <option value="min">Минимальная</option>
            </NativeSelect>
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function ListingsPage() {
  const { can } = useSession();
  const [status, setStatus] = React.useState("");
  const [q, setQ] = React.useState("");
  const query = useDebounced(q);
  const [page, setPage] = usePage(JSON.stringify([status, query]));
  const [selected, setSelected] = React.useState<number[]>([]);
  const [confirm, setConfirm] = React.useState<Extract<BulkResult, { needs_confirmation: true }>>();
  const [pctValue, setPctValue] = React.useState("");
  const { busy, run } = useAction();

  const qs = new URLSearchParams({ page: String(page), per_page: "25" });
  if (status) qs.set("status", status);
  if (query) qs.set("q", query);
  const state = useApi<Paged<Listing>>(`/listings?${qs}`);

  async function bulk(action: string, extra: Record<string, unknown> = {}) {
    const r = await run(action, () => api.post<BulkResult>("/listings/bulk", { ids: selected, action, ...extra }));
    if (!r) return;
    if ("needs_confirmation" in r) {
      setConfirm(r);
      return;
    }
    const errors = Object.entries(r.errors);
    if (errors.length) {
      const { toast } = await import("sonner");
      toast.warning(`Выполнено: ${r.ok.length}, с ошибкой: ${errors.length}`, { description: errors.slice(0, 3).map(([id, e]) => `#${id}: ${e}`).join("\n") });
    } else {
      const { toast } = await import("sonner");
      toast.success(`Выполнено для ${r.ok.length} объявлений`);
    }
    setSelected([]);
    setConfirm(undefined);
    state.reload();
  }

  const items = state.data?.items ?? [];
  const allSelected = items.length > 0 && items.every((l) => selected.includes(l.id));

  return (
    <>
      <PageHeader
        title="Объявления"
        description="Черновики, проверка, публикация и история изменений. Первая массовая публикация требует отдельного подтверждения."
        actions={
          <>
            <Button onClick={() => run("csv", () => download("/listings/export.csv", "listings.csv"))}>
              <Download /> CSV
            </Button>
            {can("listings.manage") && <NewListing />}
          </>
        }
      />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Название или номер лота" className="pl-9" />
          </div>
          <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} className="w-56" aria-label="Статус">
            <option value="">Все статусы</option>
            {Object.entries(LISTING_STATUS).map(([k, s]) => (
              <option key={k} value={k}>
                {s.label}
              </option>
            ))}
          </NativeSelect>
        </div>
        {selected.length > 0 && can("listings.manage") && (
          <div className="flex flex-wrap items-center gap-2 border-b border-border bg-primary/[0.06] px-5 py-2.5 text-[13px]">
            <span className="mr-2">Выбрано: {selected.length}</span>
            <Button size="sm" loading={busy === "prepare"} onClick={() => bulk("prepare")}>
              <Wand2 /> Подготовить
            </Button>
            {can("listings.publish") && (
              <Button size="sm" variant="primary" loading={busy === "publish"} onClick={() => bulk("publish")}>
                <Send /> Опубликовать
              </Button>
            )}
            <Button size="sm" loading={busy === "pause"} onClick={() => bulk("pause")}>
              <Pause /> Пауза
            </Button>
            <Button size="sm" loading={busy === "resume"} onClick={() => bulk("resume")}>
              <Play /> Возобновить
            </Button>
            <Button size="sm" loading={busy === "archive"} onClick={() => bulk("archive")}>
              <Archive /> В архив
            </Button>
            {can("pricing.manage") && (
              <span className="flex items-center gap-1.5">
                <Input value={pctValue} onChange={(e) => setPctValue(e.target.value)} placeholder="±%" className="h-8 w-20" aria-label="Изменение цены в процентах" />
                <Button size="sm" disabled={!Number(pctValue.replace(",", "."))} loading={busy === "price_change_pct"} onClick={() => bulk("price_change_pct", { data: { pct: pctValue.replace(",", ".") } })}>
                  Изменить цену
                </Button>
              </span>
            )}
            <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
              Снять выбор
            </Button>
          </div>
        )}
        <Async state={state} rows={8}>
          {(d) =>
            d.items.length ? (
              <>
                <Table>
                  <THead>
                    <TR className="hover:bg-transparent">
                      <TH className="w-10">
                        <input
                          type="checkbox"
                          aria-label="Выбрать все"
                          checked={allSelected}
                          onChange={() => setSelected(allSelected ? [] : d.items.map((l) => l.id))}
                          className="size-4 accent-[var(--primary)]"
                        />
                      </TH>
                      <TH>Объявление</TH>
                      <TH>Статус</TH>
                      <TH className="text-right">Цена</TH>
                      <TH className="text-right">Мин. цена</TH>
                      <TH>Лот PlayerOK</TH>
                      <TH>Изменено</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {d.items.map((l) => (
                      <TR key={l.id}>
                        <TD>
                          <input
                            type="checkbox"
                            aria-label={`Выбрать ${l.title}`}
                            checked={selected.includes(l.id)}
                            onChange={() => setSelected((s) => (s.includes(l.id) ? s.filter((x) => x !== l.id) : [...s, l.id]))}
                            className="size-4 accent-[var(--primary)]"
                          />
                        </TD>
                        <TD className="max-w-96">
                          <Link href={`/listings/${l.id}`} className="font-medium hover:text-highlight">
                            {l.title}
                          </Link>
                          <p className="truncate text-xs text-muted-foreground">
                            {l.product} · версия {l.version}
                            {l.auto_created ? " · создано автоматически" : ""}
                          </p>
                        </TD>
                        <TD>
                          <StatusBadge map={LISTING_STATUS} value={l.status} />
                          {l.status_reason && <p className="mt-1 max-w-64 truncate text-xs text-muted-foreground">{l.status_reason}</p>}
                        </TD>
                        <TD className="text-right font-medium tabular-nums">{money(l.price)}</TD>
                        <TD className="text-right tabular-nums text-muted-foreground">{money(l.min_price)}</TD>
                        <TD>
                          {l.external_url ? (
                            <a href={l.external_url} target="_blank" rel="noreferrer noopener" className="text-highlight hover:underline">
                              {l.external_id}
                            </a>
                          ) : (
                            l.external_id ?? <span className="text-muted-foreground">—</span>
                          )}
                        </TD>
                        <TD className="whitespace-nowrap text-muted-foreground">{dt(l.updated_at)}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
                <Pager page={d.page} total={d.total} perPage={d.per_page} onPage={setPage} />
              </>
            ) : (
              <Empty title={status || query ? "Ничего не найдено" : "Объявлений пока нет"} icon={FileText}>
                {status || query ? "Измените фильтр." : "Создайте объявление из карточки товара или кнопкой «Новое объявление»."}
              </Empty>
            )
          }
        </Async>
      </Card>

      <Dialog open={Boolean(confirm)} onOpenChange={(v) => !v && setConfirm(undefined)}>
        {confirm && (
          <DialogContent
            title={confirm.first_time ? "Первая массовая публикация" : "Подтвердите публикацию"}
            description="Проверьте каждое объявление. После подтверждения система опубликует их через API площадки или подготовит данные для ручной публикации."
            className="max-w-3xl"
            footer={
              <>
                <Button onClick={() => setConfirm(undefined)}>Отмена</Button>
                <Button variant="primary" loading={busy === "publish"} onClick={() => bulk("publish", { confirm: true })}>
                  <Send /> Подтверждаю — опубликовать {confirm.previews.length}
                </Button>
              </>
            }
          >
            {confirm.first_time && (
              <Notice tone="warning" className="mb-4">
                Это первая массовая публикация. Дальше подтверждение всё равно будет запрашиваться, но без этого предупреждения.
              </Notice>
            )}
            <div className="flex flex-col gap-3">
              {confirm.previews.map((p) => (
                <div key={p.id} className="rounded-md border border-border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium">{p.title}</p>
                    <span className="text-sm font-semibold tabular-nums">{money(p.price)}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {p.category} · {p.quantity} шт. · {LISTING_STATUS[p.status]?.label ?? p.status}
                  </p>
                  <p className="mt-2 line-clamp-3 text-[13px] whitespace-pre-wrap text-muted-foreground">{p.description}</p>
                </div>
              ))}
            </div>
          </DialogContent>
        )}
      </Dialog>
    </>
  );
}
