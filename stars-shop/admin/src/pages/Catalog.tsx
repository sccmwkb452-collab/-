import { formatMoney, formatRate, formatStars, monthsRu, TelegramStar } from "@starshop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Archive, Flame, Gem, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorBox, Input, Label, Modal, PageTitle, Select, Skeleton, Toggle, cn, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { can, useAdmin } from "../lib/auth";
import { useShop } from "../lib/shop";
import type { AdminProduct } from "../lib/types";

type Form = {
  kind: "package" | "custom" | "premium";
  premium_months: string;
  cost_price: string;
  title: string;
  badge: string;
  stars_amount: string;
  price: string;
  price_per_star: string;
  min_stars: string;
  max_stars: string;
  cost_per_star: string;
  cost_source: string;
  is_active: boolean;
  is_popular: boolean;
};

const EMPTY: Form = { premium_months: "3", cost_price: "", kind: "package", title: "", badge: "", stars_amount: "", price: "", price_per_star: "", min_stars: "50", max_stars: "100000", cost_per_star: "", cost_source: "", is_active: true, is_popular: false };

function toForm(p: AdminProduct): Form {
  return {
    kind: p.kind,
    premium_months: p.premium_months?.toString() ?? "3",
    cost_price: p.cost_price ?? "",
    title: p.title ?? "",
    badge: p.badge ?? "",
    stars_amount: p.stars_amount?.toString() ?? "",
    price: p.price ?? "",
    price_per_star: p.kind === "custom" ? p.price_per_star ?? "" : "",
    min_stars: p.min_stars?.toString() ?? "",
    max_stars: p.max_stars?.toString() ?? "",
    cost_per_star: p.cost_per_star ?? "",
    cost_source: p.cost_source ?? "",
    is_active: p.is_active,
    is_popular: p.is_popular,
  };
}

function toBody(f: Form, creating: boolean) {
  const num = (v: string) => (v.trim() ? v.trim().replace(",", ".") : null);
  const int = (v: string) => (v.trim() ? Number(v) : null);
  const body: Record<string, unknown> = {
    title: f.title.trim() || null,
    badge: f.badge.trim() || null,
    cost_per_star: num(f.cost_per_star),
    cost_source: f.cost_source.trim() || null,
    is_active: f.is_active,
    is_popular: f.is_popular,
  };
  if (creating) body.kind = f.kind;
  if (f.kind === "package") Object.assign(body, { stars_amount: int(f.stars_amount), price: num(f.price) });
  else if (f.kind === "premium") {
    delete body.cost_per_star;
    delete body.is_popular;
    Object.assign(body, { premium_months: int(f.premium_months), price: num(f.price), cost_price: num(f.cost_price) });
  } else Object.assign(body, { price_per_star: num(f.price_per_star), min_stars: int(f.min_stars), max_stars: int(f.max_stars) });
  return body;
}

export default function Catalog() {
  const admin = useAdmin();
  const { currency } = useShop();
  const editable = can(admin, "manager");
  const toast = useToast();
  const qc = useQueryClient();
  const products = useQuery({ queryKey: ["products"], queryFn: () => api<{ items: AdminProduct[] }>("/products") });
  const [editing, setEditing] = useState<AdminProduct | "new" | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [archiveTarget, setArchiveTarget] = useState<AdminProduct | null>(null);

  const refresh = () => qc.invalidateQueries({ queryKey: ["products"] });
  const save = useMutation({
    mutationFn: () =>
      editing === "new"
        ? api<AdminProduct>("/products", { method: "POST", body: toBody(form, true) })
        : api<AdminProduct>(`/products/${(editing as AdminProduct).id}`, { method: "PATCH", body: toBody(form, false) }),
    onSuccess: () => {
      refresh();
      setEditing(null);
      toast("Каталог обновлён — изменения уже в приложении");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api(`/products/${id}`, { method: "PATCH", body }),
    onSuccess: refresh,
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const reorder = useMutation({
    mutationFn: (ids: number[]) => api("/products/reorder", { method: "POST", body: { ids } }),
    onSuccess: refresh,
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const archive = useMutation({
    mutationFn: (id: number) => api(`/products/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      refresh();
      setArchiveTarget(null);
      toast("Пакет удалён из каталога");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const items = products.data?.items ?? [];
  const move = (index: number, dir: -1 | 1) => {
    const ids = items.map((p) => p.id);
    const j = index + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[index], ids[j]] = [ids[j], ids[index]];
    reorder.mutate(ids);
  };
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <>
      <PageTitle
        title="Каталог"
        subtitle="Цены, порядок и доступность пакетов. Изменения сразу видны в мини-приложении."
        actions={
          editable && (
            <Button
              icon={<Plus className="size-4" />}
              onClick={() => {
                setForm(EMPTY);
                setEditing("new");
              }}
            >
              Добавить пакет
            </Button>
          )
        }
      />
      {products.isError && <ErrorBox text={errorMessage(products.error)} onRetry={() => products.refetch()} />}
      <Card className="overflow-hidden">
        {products.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <Empty title="Каталог пуст" text="Добавьте первый пакет Stars." />
        ) : (
          <div className="overflow-x-auto">
            <table className="data w-full min-w-[860px]">
              <thead>
                <tr>
                  <th>Порядок</th>
                  <th>Пакет</th>
                  <th className="text-right">Цена</th>
                  <th className="text-right">За звезду</th>
                  <th className="text-right">Себестоимость</th>
                  <th className="text-right">Маржа</th>
                  <th>Статус</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((p, i) => {
                  const premium = p.kind === "premium";
                  const perStar = Number(p.price_per_star ?? 0);
                  const cost = p.cost_per_star !== null ? Number(p.cost_per_star) : null;
                  const marginPct = premium
                    ? p.cost_price !== null && Number(p.price) > 0
                      ? ((Number(p.price) - Number(p.cost_price)) / Number(p.price)) * 100
                      : null
                    : cost !== null && perStar > 0
                      ? ((perStar - cost) / perStar) * 100
                      : null;
                  return (
                    <tr key={p.id} className={cn(!p.is_active && "opacity-60")}>
                      <td>
                        <div className="flex gap-1">
                          <button className="rounded-md p-1 text-text-3 hover:bg-surface-2 hover:text-text disabled:opacity-30" disabled={!editable || i === 0} onClick={() => move(i, -1)} aria-label="Выше">
                            <ArrowUp className="size-4" />
                          </button>
                          <button className="rounded-md p-1 text-text-3 hover:bg-surface-2 hover:text-text disabled:opacity-30" disabled={!editable || i === items.length - 1} onClick={() => move(i, 1)} aria-label="Ниже">
                            <ArrowDown className="size-4" />
                          </button>
                        </div>
                      </td>
                      <td>
                        <div className="flex items-center gap-2.5">
                          {premium ? <Gem className="size-[22px] text-accent" /> : <TelegramStar size={22} />}
                          <div>
                            <div className="font-semibold">
                              {premium ? `Telegram Premium · ${monthsRu(p.premium_months ?? 0)}` : p.kind === "package" ? `${formatStars(p.stars_amount)} Stars` : `${p.title || "Своё количество"}`}
                            </div>
                            <div className="text-[12px] text-text-3">
                              {premium ? "подписка" : p.kind === "custom" ? `от ${formatStars(p.min_stars)} до ${formatStars(p.max_stars)}` : p.title || "пакет"}
                            </div>
                          </div>
                          {p.is_popular && (
                            <Badge tone="info">
                              <Flame className="size-3" /> Популярное
                            </Badge>
                          )}
                        </div>
                      </td>
                      <td className="text-right font-semibold tabular">{p.kind !== "custom" ? formatMoney(p.price, currency) : "—"}</td>
                      <td className="text-right tabular">{premium ? "—" : formatRate(p.price_per_star, currency)}</td>
                      <td className="text-right tabular text-text-2" title={p.cost_source ?? undefined}>
                        {premium ? (p.cost_price ? formatMoney(p.cost_price, currency) : "—") : p.cost_per_star ? formatRate(p.cost_per_star, currency) : "—"}
                      </td>
                      <td className="text-right tabular">{marginPct !== null ? `${marginPct.toFixed(1)}%` : "—"}</td>
                      <td>
                        {editable ? (
                          <Toggle checked={p.is_active} onChange={(v) => patch.mutate({ id: p.id, body: { is_active: v } })} label={p.is_active ? "В продаже" : "Скрыт"} />
                        ) : (
                          <Badge tone={p.is_active ? "success" : "neutral"}>{p.is_active ? "В продаже" : "Скрыт"}</Badge>
                        )}
                      </td>
                      <td>
                        {editable && (
                          <div className="flex justify-end gap-1">
                            <Button
                              size="sm"
                              variant="ghost"
                              icon={<Pencil className="size-3.5" />}
                              onClick={() => {
                                setForm(toForm(p));
                                setEditing(p);
                              }}
                            >
                              Изменить
                            </Button>
                            <Button size="sm" variant="ghost" icon={<Archive className="size-3.5" />} onClick={() => setArchiveTarget(p)} aria-label="Удалить" />
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Новый пакет" : "Изменить пакет"}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditing(null)}>
              Отмена
            </Button>
            <Button loading={save.isPending} onClick={() => save.mutate()}>
              Сохранить
            </Button>
          </>
        }
      >
        {editing === "new" && (
          <Label label="Тип">
            <Select value={form.kind} onChange={(e) => set("kind", e.target.value as Form["kind"])}>
              <option value="package">Фиксированный пакет</option>
              <option value="custom">Произвольное количество</option>
              <option value="premium">Telegram Premium</option>
            </Select>
          </Label>
        )}
        {form.kind === "premium" ? (
          <div className="grid grid-cols-3 gap-3">
            <Label label="Срок">
              <Select value={form.premium_months} onChange={(e) => set("premium_months", e.target.value)}>
                <option value="3">3 месяца</option>
                <option value="6">6 месяцев</option>
                <option value="12">12 месяцев</option>
              </Select>
            </Label>
            <Label label={`Цена, ${currency}`}>
              <Input inputMode="decimal" value={form.price} onChange={(e) => set("price", e.target.value)} />
            </Label>
            <Label label="Себестоимость" hint="Не видна покупателям">
              <Input inputMode="decimal" value={form.cost_price} onChange={(e) => set("cost_price", e.target.value)} />
            </Label>
          </div>
        ) : form.kind === "package" ? (
          <div className="grid grid-cols-2 gap-3">
            <Label label="Количество Stars">
              <Input inputMode="numeric" value={form.stars_amount} onChange={(e) => set("stars_amount", e.target.value.replace(/\D/g, ""))} />
            </Label>
            <Label label={`Цена, ${currency}`}>
              <Input inputMode="decimal" value={form.price} onChange={(e) => set("price", e.target.value)} />
            </Label>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3">
            <Label label="Цена за звезду">
              <Input inputMode="decimal" value={form.price_per_star} onChange={(e) => set("price_per_star", e.target.value)} />
            </Label>
            <Label label="Минимум">
              <Input inputMode="numeric" value={form.min_stars} onChange={(e) => set("min_stars", e.target.value.replace(/\D/g, ""))} />
            </Label>
            <Label label="Максимум">
              <Input inputMode="numeric" value={form.max_stars} onChange={(e) => set("max_stars", e.target.value.replace(/\D/g, ""))} />
            </Label>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Label label="Название (необязательно)">
            <Input value={form.title} onChange={(e) => set("title", e.target.value)} maxLength={64} />
          </Label>
          <Label label="Бейдж (необязательно)" hint="Например, «Выгодно»">
            <Input value={form.badge} onChange={(e) => set("badge", e.target.value)} maxLength={32} />
          </Label>
        </div>
        {form.kind !== "premium" && <div className="grid grid-cols-2 gap-3">
          <Label label="Себестоимость за звезду" hint="Не показывается покупателям">
            <Input inputMode="decimal" value={form.cost_per_star} onChange={(e) => set("cost_per_star", e.target.value)} />
          </Label>
          <Label label="Источник себестоимости" hint="Например, «Fragment, курс TON на 20.10»">
            <Input value={form.cost_source} onChange={(e) => set("cost_source", e.target.value)} maxLength={255} />
          </Label>
        </div>}
        <Toggle checked={form.is_active} onChange={(v) => set("is_active", v)} label="В продаже" />
        {form.kind !== "premium" && (
          <Toggle checked={form.is_popular} onChange={(v) => set("is_popular", v)} label="Метка «Популярное»" hint="Только один пакет может быть популярным" />
        )}
      </Modal>

      <Modal
        open={archiveTarget !== null}
        onClose={() => setArchiveTarget(null)}
        title="Удалить пакет?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setArchiveTarget(null)}>
              Отмена
            </Button>
            <Button variant="danger" loading={archive.isPending} onClick={() => archiveTarget && archive.mutate(archiveTarget.id)}>
              Удалить
            </Button>
          </>
        }
      >
        <p className="text-[13.5px] text-text-2">Пакет исчезнет из каталога. История заказов с ним сохранится.</p>
      </Modal>
    </>
  );
}
