"use client";

import { Archive, ArrowLeft, Ban, Eye, EyeOff, FileText, KeyRound, Link2, Pause, Play, Plus, RefreshCw, Save, Search } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";

import { Async, CopyButton, Empty, KV, Notice, PageHeader } from "@/components/app/blocks";
import { ConfirmAction } from "@/components/app/confirm";
import { CalculationView, FactorList } from "@/components/app/pricing-view";
import { ProductForm, toPayload, type ProductFormValue } from "@/components/app/product-form";
import { StatusBadge } from "@/components/app/status";
import { PriceChart } from "@/components/charts/charts";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { useDraft } from "@/lib/hooks";
import { dt, money, num } from "@/lib/format";
import { POLICY_FIELDS } from "@/lib/pricing";
import { useSession } from "@/lib/session";
import { CODE_STATUS, COMPLIANCE, CONFIDENCE, DELIVERY_TYPE, PRODUCT_STATUS } from "@/lib/status";
import type { Code, Listing, Paged, ProductDetail, Supplier, SupplierProduct } from "@/lib/types";

function toForm(p: ProductDetail): ProductFormValue {
  return {
    name: p.name,
    category_id: String(p.category.id),
    sku: p.sku,
    description: p.description ?? "",
    region: p.region ?? "",
    face_value: p.face_value ?? "",
    face_currency: p.face_currency ?? "",
    delivery_type: p.delivery_type,
    delivery_time: p.delivery_time ?? "",
    activation_notes: p.activation_notes ?? "",
    buyer_instructions: p.buyer_instructions ?? "",
    required_buyer_data: p.required_buyer_data ?? "",
    supplier_quantity: String(p.supplier_quantity),
    manual_unit_cost: p.manual_unit_cost ?? "",
  };
}

function LinkSupplier({ productId, onDone }: { productId: number; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const suppliers = useApi<{ items: Supplier[] }>(open ? "/suppliers" : null);
  const [sid, setSid] = React.useState("");
  const [q, setQ] = React.useState("");
  const items = useApi<Paged<SupplierProduct>>(open && sid ? `/suppliers/${sid}/products?per_page=50&q=${encodeURIComponent(q)}` : null);
  const { busy, run } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Link2 /> Привязать позицию поставщика
        </Button>
      </DialogTrigger>
      <DialogContent title="Позиция поставщика" description="Цена позиции станет закупочной ценой товара." className="max-w-2xl">
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <NativeSelect value={sid} onChange={(e) => setSid(e.target.value)} aria-label="Поставщик">
              <option value="">Выберите поставщика…</option>
              {suppliers.data?.items.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.products_count ?? 0} позиций)
                </option>
              ))}
            </NativeSelect>
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по названию" className="pl-9" disabled={!sid} />
            </div>
          </div>
          {sid && items.data && !items.data.items.length && (
            <Notice>У поставщика нет позиций в каталоге. Запустите синхронизацию на странице поставщика.</Notice>
          )}
          <div className="flex max-h-80 flex-col divide-y divide-border overflow-y-auto rounded-md border border-border">
            {items.data?.items.map((sp) => (
              <button
                key={sp.id}
                disabled={busy !== null}
                onClick={async () => {
                  const r = await run("link", () => api.post(`/products/${productId}/link-supplier`, { supplier_product_id: sp.id }), "Позиция привязана");
                  if (r) {
                    setOpen(false);
                    onDone();
                  }
                }}
                className="flex items-center justify-between gap-3 px-3 py-2.5 text-left hover:bg-surface-2"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm">{sp.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {sp.external_id} · {sp.compliance_label}
                  </span>
                </span>
                <span className="shrink-0 text-sm tabular-nums">
                  {sp.price} {sp.currency}
                  {sp.price_unit > 1 ? ` / ${num(sp.price_unit)}` : ""}
                </span>
              </button>
            ))}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Observation({ productId, onDone }: { productId: number; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [v, setV] = React.useState({ competitor_min: "", competitor_median: "", competitor_max: "", offers_count: "", note: "" });
  const { busy, run } = useAction();
  const dec = (s: string) => (s.trim() ? s.replace(",", ".") : null);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus /> Цены конкурентов
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Наблюдение за рынком PlayerOK"
        description="Цены конкурентов система не собирает сама (у PlayerOK нет API). Внесите то, что видите на площадке, — запись сохранится с датой и вашим именем."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              disabled={!Number(dec(v.competitor_min))}
              loading={busy === "obs"}
              onClick={async () => {
                const r = await run(
                  "obs",
                  () =>
                    api.post(`/products/${productId}/observations`, {
                      competitor_min: dec(v.competitor_min),
                      competitor_median: dec(v.competitor_median),
                      competitor_max: dec(v.competitor_max),
                      offers_count: v.offers_count ? Number(v.offers_count) : null,
                      note: v.note,
                    }),
                  "Наблюдение сохранено, цена пересчитана",
                );
                if (r) {
                  setOpen(false);
                  onDone();
                }
              }}
            >
              Сохранить
            </Button>
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Минимальная цена, ₽">
            <Input inputMode="decimal" value={v.competitor_min} onChange={(e) => setV({ ...v, competitor_min: e.target.value })} autoFocus />
          </Field>
          <Field label="Медианная цена, ₽">
            <Input inputMode="decimal" value={v.competitor_median} onChange={(e) => setV({ ...v, competitor_median: e.target.value })} />
          </Field>
          <Field label="Максимальная цена, ₽">
            <Input inputMode="decimal" value={v.competitor_max} onChange={(e) => setV({ ...v, competitor_max: e.target.value })} />
          </Field>
          <Field label="Число предложений">
            <Input inputMode="numeric" value={v.offers_count} onChange={(e) => setV({ ...v, offers_count: e.target.value.replace(/\D/g, "") })} />
          </Field>
          <Field label="Комментарий" className="sm:col-span-2">
            <Textarea value={v.note} onChange={(e) => setV({ ...v, note: e.target.value })} className="min-h-16" />
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function CodeRow({ code, onChange }: { code: Code; onChange: () => void }) {
  const { can } = useSession();
  const [plain, setPlain] = React.useState<string>();
  const { busy, run } = useAction();
  React.useEffect(() => {
    if (!plain) return;
    const t = setTimeout(() => setPlain(undefined), 60_000);
    return () => clearTimeout(t);
  }, [plain]);
  return (
    <TR>
      <TD>
        <code className="font-mono text-[13px]">{plain ?? code.mask}</code>
        {code.is_test && <span className="ml-2 text-xs text-yellow-300">тест</span>}
      </TD>
      <TD>
        <StatusBadge map={CODE_STATUS} value={code.status} />
      </TD>
      <TD className="text-muted-foreground">{code.revealed_count}</TD>
      <TD className="text-right">
        <div className="flex justify-end gap-1">
          {plain && <CopyButton value={plain} />}
          {can("orders.reveal_codes") && (
            <Button
              size="sm"
              variant="ghost"
              loading={busy === "r"}
              onClick={async () => {
                if (plain) return setPlain(undefined);
                const r = await run("r", () => api.post<{ code: string }>(`/codes/${code.id}/reveal`));
                if (r) setPlain(r.code);
              }}
            >
              {plain ? <EyeOff /> : <Eye />}
            </Button>
          )}
          {code.status === "available" && (
            <ConfirmAction
              label=""
              icon={<Ban />}
              variant="ghost"
              title="Аннулировать код"
              input={{ label: "Причина", required: true }}
              confirmVariant="danger"
              onConfirm={async (reason) => {
                const r = await run("v", () => api.post(`/codes/${code.id}/void`, { reason }), "Код аннулирован");
                if (r) onChange();
                return r;
              }}
            />
          )}
        </div>
      </TD>
    </TR>
  );
}

function Inventory({ productId }: { productId: number }) {
  const state = useApi<{ items: Code[]; stock: Record<string, number> }>(`/products/${productId}/codes`);
  const [codes, setCodes] = React.useState("");
  const [cost, setCost] = React.useState("");
  const { busy, run } = useAction();
  const list = codes.split("\n").map((c) => c.trim()).filter(Boolean);
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
      <Card>
        <CardHeader
          title="Коды на складе"
          description="Коды хранятся зашифрованными. Просмотр полного кода записывается в журнал."
          actions={
            state.data && (
              <div className="flex gap-3 text-[13px] text-muted-foreground">
                <span>доступно {state.data.stock.available ?? 0}</span>
                <span>резерв {state.data.stock.reserved ?? 0}</span>
                <span>выдано {state.data.stock.issued ?? 0}</span>
              </div>
            )
          }
        />
        <Async state={state}>
          {(d) =>
            d.items.length ? (
              <Table>
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH>Код</TH>
                    <TH>Статус</TH>
                    <TH>Просмотров</TH>
                    <TH />
                  </TR>
                </THead>
                <TBody>
                  {d.items.map((c) => (
                    <CodeRow key={c.id} code={c} onChange={state.reload} />
                  ))}
                </TBody>
              </Table>
            ) : (
              <Empty title="Кодов нет" icon={KeyRound}>
                Загрузите коды справа — они будут выдаваться покупателям по очереди, без повторов.
              </Empty>
            )
          }
        </Async>
      </Card>
      <Card>
        <CardHeader title="Загрузить коды" />
        <CardBody className="flex flex-col gap-4">
          <Field label="По одному в строке" hint={list.length ? `${list.length} кодов` : "Дубли и уже загруженные коды будут отклонены"}>
            <Textarea value={codes} onChange={(e) => setCodes(e.target.value)} className="min-h-40 font-mono" spellCheck={false} autoComplete="off" />
          </Field>
          <Field label="Себестоимость за код, ₽">
            <Input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
          </Field>
          <Button
            variant="primary"
            disabled={!list.length}
            loading={busy === "add"}
            onClick={async () => {
              const r = await run(
                "add",
                () =>
                  api.post<{ added: number; duplicates: number; rejected: number }>(`/products/${productId}/codes`, {
                    codes: list,
                    unit_cost: cost ? cost.replace(",", ".") : null,
                  }),
                (x) => `Добавлено ${x.added}, дублей ${x.duplicates}, отклонено ${x.rejected}`,
              );
              if (r) {
                setCodes("");
                state.reload();
              }
            }}
          >
            Сохранить коды
          </Button>
        </CardBody>
      </Card>
    </div>
  );
}

function ProductSettings({ p, onSaved }: { p: ProductDetail; onSaved: () => void }) {
  const templates = useApi<{ items: { code: string; name: string; active: boolean }[] }>("/images/templates");
  const { busy, run } = useAction();
  return (
    <div className="flex flex-col gap-5">
      <label className="flex items-start justify-between gap-4">
        <span>
          <span className="block text-sm font-medium">Разрешить автоматическую закупку</span>
          <span className="text-[13px] text-muted-foreground">
            Работает только у поставщика в режиме «Автоматически в лимитах» и только в боевом режиме.
          </span>
        </span>
        <Switch
          checked={p.auto_purchase_allowed}
          disabled={busy !== null}
          onCheckedChange={async (v) => {
            const r = await run("auto", () => api.patch(`/products/${p.id}`, { auto_purchase_allowed: v }), "Сохранено");
            if (r) onSaved();
          }}
        />
      </label>
      <Field label="Шаблон изображения" hint="По умолчанию выбирается шаблон категории">
        <NativeSelect
          value={p.image_template ?? ""}
          disabled={busy !== null}
          onChange={async (e) => {
            const r = await run("tpl", () => api.patch(`/products/${p.id}`, { image_template: e.target.value }), "Шаблон сохранён");
            if (r) onSaved();
          }}
        >
          <option value="">Автоматически</option>
          {templates.data?.items.map((t) => (
            <option key={t.code} value={t.code} disabled={!t.active}>
              {t.name}
              {!t.active ? " (нет файла)" : ""}
            </option>
          ))}
        </NativeSelect>
      </Field>
    </div>
  );
}

export default function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const state = useApi<ProductDetail>(`/products/${id}`);
  const { can } = useSession();
  const { busy, run } = useAction();
  const [form, setForm] = useDraft(state.data, toForm);
  const [price, setPrice] = React.useState("");

  async function setStatus(status: string, reason = "") {
    const r = await run(status, () => api.post(`/products/${id}/status`, { status, reason }), "Статус изменён");
    if (r) state.reload();
    return r;
  }

  return (
    <Async state={state} rows={10}>
      {(p) => {
        const dyn = p.price_dynamics;
        const points = [
          ...dyn.purchase.map((x) => ({ at: x.at, purchase: x.price_rub ? Number(x.price_rub) : null, sale: null })),
          ...dyn.sale.map((x) => ({ at: x.at, purchase: null, sale: x.price ? Number(x.price) : null })),
        ].sort((a, b) => a.at.localeCompare(b.at));
        return (
          <>
            <Link href="/products" className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground">
              <ArrowLeft className="size-4" /> Все товары
            </Link>
            <PageHeader
              title={p.name}
              description={`${p.sku} · ${p.category.name} · ${DELIVERY_TYPE[p.delivery_type]}`}
              actions={
                <>
                  <Button size="sm" loading={busy === "reprice"} onClick={async () => { if (await run("reprice", () => api.post(`/products/${id}/reprice`), "Цена пересчитана")) state.reload(); }}>
                    <RefreshCw /> Пересчитать
                  </Button>
                  {can("listings.manage") && (
                    <Button
                      size="sm"
                      loading={busy === "listing"}
                      onClick={async () => {
                        const l = await run("listing", () => api.post<Listing>("/listings", { product_id: p.id }), "Черновик объявления создан");
                        if (l) router.push(`/listings/${l.id}`);
                      }}
                    >
                      <FileText /> Создать объявление
                    </Button>
                  )}
                  {can("products.manage") && p.status !== "active" && (
                    <Button variant="success" size="sm" loading={busy === "active"} onClick={() => setStatus("active")}>
                      <Play /> Активировать
                    </Button>
                  )}
                  {can("products.manage") && p.status === "active" && (
                    <Button size="sm" loading={busy === "paused"} onClick={() => setStatus("paused")}>
                      <Pause /> Пауза
                    </Button>
                  )}
                  {can("products.manage") && p.status !== "archived" && (
                    <ConfirmAction label="В архив" icon={<Archive />} title="Убрать товар в архив?" onConfirm={() => setStatus("archived")} />
                  )}
                </>
              }
            >
              <div className="flex flex-wrap gap-2">
                <StatusBadge map={PRODUCT_STATUS} value={p.status} />
                <StatusBadge map={COMPLIANCE} value={p.compliance_status} />
              </div>
            </PageHeader>

            {p.compliance_status !== "approved" && (
              <Notice tone="warning" title="Продажа этой категории не подтверждена" className="mb-5">
                {p.category_full.compliance_note || "Проверьте правила площадки и поставщика."} Активация, автоматизация и публикация
                заблокированы до одобрения категории.
              </Notice>
            )}

            <Tabs defaultValue="price">
              <TabsList>
                <TabsTrigger value="price">Цена и прибыль</TabsTrigger>
                <TabsTrigger value="edit">Карточка</TabsTrigger>
                {p.delivery_type === "code" && can("inventory.manage") && <TabsTrigger value="codes">Коды</TabsTrigger>}
                <TabsTrigger value="market">Рынок и исследование</TabsTrigger>
              </TabsList>

              <TabsContent value="price" className="grid gap-6 xl:grid-cols-[1fr_360px]">
                <Card>
                  <CardHeader title="Расчёт цены" description={p.pricing.priced_at ? `Рассчитано ${dt(p.pricing.priced_at)}` : undefined} />
                  <CardBody>
                    <CalculationView calc={p.calculation} currency={p.cost_currency} fxRate={p.fx_rate} costSource={p.cost_source} />
                  </CardBody>
                </Card>
                <div className="flex flex-col gap-6">
                  {can("pricing.manage") && (
                    <Card>
                      <CardHeader title="Цена продажи" description={`Сейчас: ${money(p.pricing.current_price)}`} />
                      <CardBody className="flex flex-col gap-3">
                        <Field label="Новая цена, ₽" hint={p.pricing.min_price ? `Не ниже ${money(p.pricing.min_price)} — иначе система откажет` : undefined}>
                          <Input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} placeholder={p.pricing.recommended_price ?? ""} />
                        </Field>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            variant="primary"
                            size="sm"
                            disabled={!Number(price.replace(",", "."))}
                            loading={busy === "price"}
                            onClick={async () => {
                              const r = await run("price", () => api.post(`/products/${id}/price`, { price: price.replace(",", ".") }), "Цена сохранена");
                              if (r) {
                                setPrice("");
                                state.reload();
                              }
                            }}
                          >
                            <Save /> Сохранить цену
                          </Button>
                          {p.pricing.recommended_price && (
                            <Button size="sm" onClick={() => setPrice(p.pricing.recommended_price ?? "")}>
                              Рекомендуемая
                            </Button>
                          )}
                        </div>
                      </CardBody>
                    </Card>
                  )}
                  <Card>
                    <CardHeader title="Поставщик" />
                    <CardBody className="flex flex-col gap-3">
                      {p.supplier_product ? (
                        <KV
                          items={[
                            ["Поставщик", <Link key="s" href={`/suppliers/${p.supplier_product.supplier_id}`} className="hover:text-highlight">{p.supplier_product.supplier}</Link>],
                            ["Позиция", p.supplier_product.name],
                            ["Цена", `${p.supplier_product.price} ${p.supplier_product.currency}${p.supplier_product.price_unit > 1 ? ` за ${num(p.supplier_product.price_unit)}` : ""}`],
                            ["Обновлена", dt(p.supplier_product.last_seen_at)],
                          ]}
                        />
                      ) : (
                        <p className="text-[13px] text-muted-foreground">
                          Не привязан. {p.manual_unit_cost ? `Используется себестоимость ${money(p.manual_unit_cost)}.` : "Укажите себестоимость в карточке или привяжите позицию."}
                        </p>
                      )}
                      {can("products.manage") && (
                        <div className="flex flex-wrap gap-2">
                          <LinkSupplier productId={p.id} onDone={state.reload} />
                          {p.supplier_product && (
                            <Button size="sm" variant="ghost" onClick={async () => { if (await run("unlink", () => api.post(`/products/${id}/link-supplier`, { supplier_product_id: null }), "Отвязано")) state.reload(); }}>
                              Отвязать
                            </Button>
                          )}
                        </div>
                      )}
                    </CardBody>
                  </Card>
                  {can("products.manage") && (
                    <Card>
                      <CardHeader title="Автоматизация и изображение" />
                      <CardBody>
                        <ProductSettings p={p} onSaved={state.reload} />
                      </CardBody>
                    </Card>
                  )}
                  <Card>
                    <CardHeader title="Правила цены" description="Действующие значения: глобальные → категория → товар" />
                    <CardBody>
                      <KV
                        className="text-[13px]"
                        items={Object.entries(p.policy)
                          .filter(([k]) => POLICY_FIELDS[k])
                          .slice(0, 8)
                          .map(([k, v]) => [POLICY_FIELDS[k].label, v === null || v === "" ? "не задано" : `${v} ${POLICY_FIELDS[k].unit}`])}
                      />
                      <Button size="sm" variant="link" asChild className="mt-3">
                        <Link href={`/pricing?product=${p.id}`}>Изменить правила для товара</Link>
                      </Button>
                    </CardBody>
                  </Card>
                </div>
              </TabsContent>

              <TabsContent value="edit">
                <Card>
                  <CardHeader title="Карточка товара" description="После сохранения цена пересчитывается автоматически" />
                  <CardBody>
                    {form && <ProductForm value={form} onChange={setForm} />}
                    {can("products.manage") && form && (
                      <div className="mt-5 flex gap-2">
                        <Button
                          variant="primary"
                          loading={busy === "save"}
                          onClick={async () => {
                            const r = await run("save", () => api.patch(`/products/${id}`, toPayload(form, false)), "Товар сохранён");
                            if (r) state.reload();
                          }}
                        >
                          <Save /> Сохранить
                        </Button>
                        <Button onClick={() => setForm(toForm(p))}>Сбросить изменения</Button>
                      </div>
                    )}
                  </CardBody>
                </Card>
              </TabsContent>

              {p.delivery_type === "code" && can("inventory.manage") && (
                <TabsContent value="codes">
                  <Inventory productId={p.id} />
                </TabsContent>
              )}

              <TabsContent value="market" className="grid gap-6 xl:grid-cols-2">
                <Card>
                  <CardHeader
                    title="Цены конкурентов"
                    description="Вносятся вручную с указанием даты — источник всегда виден"
                    actions={can("pricing.manage") && <Observation productId={p.id} onDone={state.reload} />}
                  />
                  {p.observations.length ? (
                    <Table>
                      <THead>
                        <TR className="hover:bg-transparent">
                          <TH>Дата</TH>
                          <TH className="text-right">Мин.</TH>
                          <TH className="text-right">Медиана</TH>
                          <TH className="text-right">Предложений</TH>
                          <TH>Кто внёс</TH>
                        </TR>
                      </THead>
                      <TBody>
                        {p.observations.map((o) => (
                          <TR key={o.id}>
                            <TD className="whitespace-nowrap">{dt(o.observed_at)}</TD>
                            <TD className="text-right tabular-nums">{money(o.competitor_min)}</TD>
                            <TD className="text-right tabular-nums">{money(o.competitor_median)}</TD>
                            <TD className="text-right">{o.offers_count ?? "—"}</TD>
                            <TD className="text-muted-foreground">{o.recorded_by ?? o.source}</TD>
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                  ) : (
                    <Empty title="Наблюдений нет">Без цен конкурентов рекомендуемая цена равна целевой.</Empty>
                  )}
                </Card>
                <Card>
                  <CardHeader title="Оценка исследования" />
                  <CardBody>
                    {p.research ? (
                      <div className="flex flex-col gap-4">
                        <div className="flex items-center gap-3">
                          <span className="text-3xl font-semibold tabular-nums">{Number(p.research.total_score).toFixed(0)}</span>
                          <span className="text-sm text-muted-foreground">из 100</span>
                          <StatusBadge map={CONFIDENCE} value={p.research.confidence} />
                        </div>
                        <FactorList factors={p.research.factors} />
                        <p className="text-xs text-muted-foreground">Рассчитано {dt(p.research.computed_at)}</p>
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">Ещё не рассчитано. Нажмите «Пересчитать».</p>
                    )}
                  </CardBody>
                </Card>
                <Card className="xl:col-span-2">
                  <CardHeader title="Динамика цен за 30 дней" description="Закупка — по истории цен поставщика; продажа — по изменениям объявлений" />
                  <CardBody>
                    {points.length >= 2 ? (
                      <PriceChart points={points} />
                    ) : (
                      <Empty title="Недостаточно истории">График появится, когда накопится хотя бы два изменения цены.</Empty>
                    )}
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
