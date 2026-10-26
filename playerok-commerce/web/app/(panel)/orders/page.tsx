"use client";

import { FileUp, Plus, Search, ShoppingCart, Trash2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Suspense } from "react";

import { Async, Empty, Notice, PageHeader, Pager } from "@/components/app/blocks";
import { OrderTable } from "@/components/app/order-table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { useDebounced, usePage } from "@/lib/hooks";
import { money } from "@/lib/format";
import { useSession } from "@/lib/session";
import { ORDER_STATUS } from "@/lib/status";
import type { Order, Paged, Product } from "@/lib/types";

type OrdersPage = Paged<Order> & { marketplace_note: string };

function NewOrderDialog({ onCreated }: { onCreated: (order: Order) => void }) {
  const [open, setOpen] = React.useState(false);
  const products = useApi<Paged<Product>>(open ? "/products?status=active&per_page=100" : null);
  const [externalId, setExternalId] = React.useState("");
  const [buyer, setBuyer] = React.useState("");
  const [link, setLink] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [items, setItems] = React.useState([{ product_id: "", quantity: "1", unit_price: "" }]);
  const { busy, run } = useAction();

  const list = products.data?.items ?? [];
  const total = items.reduce((s, i) => s + (Number(i.unit_price) || 0) * (Number(i.quantity) || 0), 0);

  function setItem(index: number, patch: Partial<(typeof items)[number]>) {
    setItems((prev) => prev.map((it, i) => (i === index ? { ...it, ...patch } : it)));
  }

  async function submit() {
    const result = await run(
      "create",
      () =>
        api.post<{ order: Order; created: boolean }>("/orders", {
          external_id: externalId.trim(),
          buyer_name: buyer.trim() || null,
          buyer_link: link.trim() || null,
          notes,
          items: items.map((i) => ({ product_id: Number(i.product_id), quantity: Number(i.quantity), unit_price: i.unit_price.replace(",", ".") })),
        }),
      (r) => (r.created ? `Заказ ${r.order.number} создан` : `Такой заказ уже есть: ${r.order.number}`),
    );
    if (result) {
      setOpen(false);
      onCreated(result.order);
    }
  }

  const valid = externalId.trim() && items.every((i) => i.product_id && Number(i.quantity) > 0 && Number(i.unit_price.replace(",", ".")) > 0);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="primary">
          <Plus /> Внести заказ
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Новый заказ PlayerOK"
        description="Перенесите данные сделки с PlayerOK. Повторный ввод того же номера сделки не создаст дубль."
        className="max-w-2xl"
        footer={
          <>
            <span className="mr-auto self-center text-sm text-muted-foreground">Итого: {money(total)}</span>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button variant="primary" onClick={submit} loading={busy === "create"} disabled={!valid}>
              Создать заказ
            </Button>
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Номер сделки на PlayerOK" hint="Из адреса или карточки сделки">
            <Input value={externalId} onChange={(e) => setExternalId(e.target.value)} placeholder="например, 1a2b3c" />
          </Field>
          <Field label="Покупатель (ник)">
            <Input value={buyer} onChange={(e) => setBuyer(e.target.value)} />
          </Field>
          <Field label="Ссылка или данные для выдачи" className="sm:col-span-2" hint="Например, @username для Stars/Premium или ссылка на канал для услуг">
            <Input value={link} onChange={(e) => setLink(e.target.value)} />
          </Field>
        </div>
        <div className="mt-5 flex flex-col gap-3">
          <p className="text-[13px] font-medium">Позиции</p>
          {products.data && !list.length && (
            <Notice tone="warning">Нет активных товаров. Создайте товар и переведите его в статус «Активен» в разделе «Товары».</Notice>
          )}
          {items.map((item, index) => (
            <div key={index} className="grid grid-cols-[1fr_80px_110px_auto] items-end gap-2">
              <Field label={index === 0 ? "Товар" : ""}>
                <NativeSelect value={item.product_id} onChange={(e) => {
                  const p = list.find((x) => String(x.id) === e.target.value);
                  setItem(index, { product_id: e.target.value, unit_price: item.unit_price || p?.pricing.current_price || p?.pricing.recommended_price || "" });
                }}>
                  <option value="">Выберите товар…</option>
                  {list.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.sku})
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field label={index === 0 ? "Кол-во" : ""}>
                <Input inputMode="numeric" value={item.quantity} onChange={(e) => setItem(index, { quantity: e.target.value.replace(/\D/g, "") })} />
              </Field>
              <Field label={index === 0 ? "Цена, ₽" : ""}>
                <Input inputMode="decimal" value={item.unit_price} onChange={(e) => setItem(index, { unit_price: e.target.value })} />
              </Field>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Убрать позицию"
                disabled={items.length === 1}
                onClick={() => setItems((prev) => prev.filter((_, i) => i !== index))}
              >
                <Trash2 />
              </Button>
            </div>
          ))}
          <Button size="sm" className="self-start" onClick={() => setItems((p) => [...p, { product_id: "", quantity: "1", unit_price: "" }])}>
            <Plus /> Ещё позиция
          </Button>
        </div>
        <Field label="Заметка" className="mt-5">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="min-h-16" />
        </Field>
      </DialogContent>
    </Dialog>
  );
}

function ImportDialog({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [file, setFile] = React.useState<File | null>(null);
  const [result, setResult] = React.useState<{ rows: number; created: number; duplicates: number; errors: number; messages: string[] }>();
  const { busy, run } = useAction();

  async function submit() {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    const r = await run("import", () => api.post<typeof result>("/orders/import", form), "Импорт выполнен");
    if (r) {
      setResult(r);
      onDone();
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setResult(undefined); setFile(null); } }}>
      <DialogTrigger asChild>
        <Button>
          <FileUp /> Импорт CSV
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Импорт заказов из CSV"
        description="Повторные строки (тот же номер сделки) пропускаются — импорт можно запускать сколько угодно раз."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Закрыть</Button>
            <Button variant="primary" onClick={submit} disabled={!file} loading={busy === "import"}>
              Импортировать
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Notice>
            Колонки: <b>external_id</b>, <b>sku</b>, <b>unit_price</b> (обязательные), quantity, placed_at, buyer, status
            (new|completed|cancelled|refund), unit_cost, link. Разделитель — «;» или «,», кодировка UTF-8 или Windows-1251. Новые заказы
            со статусом new сразу попадают в обработку.
          </Notice>
          <Input type="file" accept=".csv,text/csv" className="h-auto py-2" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          {result && (
            <div className="rounded-md border border-border bg-surface-2 p-3 text-sm">
              Строк: {result.rows} · создано: {result.created} · дублей: {result.duplicates} · ошибок: {result.errors}
              {result.messages.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-muted-foreground">
                  {result.messages.slice(0, 20).map((m, i) => (
                    <li key={i}>{m}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function OrdersView() {
  const router = useRouter();
  const params = useSearchParams();
  const { can } = useSession();
  const status = params.get("status") ?? "";
  const attention = params.get("attention") === "1";
  const [q, setQ] = React.useState(params.get("q") ?? "");
  const query = useDebounced(q);
  const [includeTest, setIncludeTest] = React.useState(true);
  const [page, setPage] = usePage(JSON.stringify([status, attention, query, includeTest]));

  const qs = new URLSearchParams({ page: String(page), per_page: "25", include_test: String(includeTest) });
  if (status) qs.set("status", status);
  if (attention) qs.set("attention", "true");
  if (query) qs.set("q", query);
  const state = useApi<OrdersPage>(`/orders?${qs}`);

  function setFilter(next: { status?: string; attention?: boolean }) {
    const sp = new URLSearchParams();
    const s = next.status ?? status;
    const a = next.attention ?? attention;
    if (s) sp.set("status", s);
    if (a) sp.set("attention", "1");
    router.replace(`/orders${sp.size ? `?${sp}` : ""}`);
  }

  return (
    <>
      <PageHeader
        title="Заказы"
        description="Все сделки с PlayerOK: проверка, закупка, выдача и завершение. Каждый переход статуса записывается в историю заказа."
        actions={
          can("orders.manage") && (
            <>
              <ImportDialog onDone={state.reload} />
              <NewOrderDialog onCreated={(o) => router.push(`/orders/${o.id}`)} />
            </>
          )
        }
      />
      {state.data?.marketplace_note && <Notice className="mb-4">{state.data.marketplace_note}</Notice>}
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Номер заказа, сделки или покупатель" className="pl-9" />
          </div>
          <NativeSelect value={status} onChange={(e) => setFilter({ status: e.target.value })} className="w-60" aria-label="Статус">
            <option value="">Все статусы</option>
            {Object.entries(ORDER_STATUS).map(([value, s]) => (
              <option key={value} value={value}>
                {s.label}
              </option>
            ))}
          </NativeSelect>
          <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <Switch checked={attention} onCheckedChange={(v) => setFilter({ attention: v })} /> Требуют внимания
          </label>
          <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <Switch checked={includeTest} onCheckedChange={setIncludeTest} /> Тестовые
          </label>
        </div>
        <Async state={state} rows={8}>
          {(d) =>
            d.items.length ? (
              <>
                <OrderTable orders={d.items} />
                <Pager page={d.page} total={d.total} perPage={d.per_page} onPage={setPage} />
              </>
            ) : (
              <Empty title={status || attention || query ? "Нет заказов по фильтру" : "Заказов пока нет"} icon={ShoppingCart}>
                {status || attention || query ? "Измените фильтр или строку поиска." : "Внесите первый заказ вручную или импортируйте выгрузку сделок."}
              </Empty>
            )
          }
        </Async>
      </Card>
    </>
  );
}

export default function OrdersPage() {
  return (
    <Suspense>
      <OrdersView />
    </Suspense>
  );
}
