import { formatDate, formatMoney } from "@starshop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorBox, Input, Label, Modal, PageTitle, Select, Skeleton, Toggle, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { can, useAdmin } from "../lib/auth";
import { useShop } from "../lib/shop";
import type { Promo } from "../lib/types";

type Form = {
  code: string;
  description: string;
  kind: "percent" | "fixed";
  value: string;
  max_discount: string;
  min_order_amount: string;
  starts_at: string;
  expires_at: string;
  max_uses: string;
  per_user_limit: string;
  first_order_only: boolean;
  is_active: boolean;
};

const EMPTY: Form = { code: "", description: "", kind: "percent", value: "10", max_discount: "", min_order_amount: "", starts_at: "", expires_at: "", max_uses: "", per_user_limit: "1", first_order_only: false, is_active: true };

const toLocalInput = (iso: string | null) => (iso ? new Date(iso).toISOString().slice(0, 16) : "");
const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : null);
const dec = (v: string) => (v.trim() ? v.trim().replace(",", ".") : null);

function promoStatus(p: Promo): { label: string; tone: "success" | "neutral" | "warning" | "danger" } {
  const now = Date.now();
  if (!p.is_active) return { label: "Выключен", tone: "neutral" };
  if (p.expires_at && new Date(p.expires_at).getTime() <= now) return { label: "Истёк", tone: "danger" };
  if (p.starts_at && new Date(p.starts_at).getTime() > now) return { label: "Запланирован", tone: "warning" };
  if (p.max_uses !== null && p.used >= p.max_uses) return { label: "Исчерпан", tone: "warning" };
  return { label: "Активен", tone: "success" };
}

export default function PromoPage() {
  const admin = useAdmin();
  const editable = can(admin, "manager");
  const { currency } = useShop();
  const toast = useToast();
  const qc = useQueryClient();
  const promos = useQuery({ queryKey: ["promos"], queryFn: () => api<{ items: Promo[] }>("/promo-codes") });
  const [editing, setEditing] = useState<Promo | "new" | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [usagesOf, setUsagesOf] = useState<Promo | null>(null);
  const usages = useQuery({
    queryKey: ["promo-usages", usagesOf?.id],
    queryFn: () => api<{ items: { id: number; status: string; discount: string; order_id: string; user: { telegram_id: number; username: string | null }; at: string }[]; applied_discount_total: string }>(`/promo-codes/${usagesOf!.id}/usages`),
    enabled: usagesOf !== null,
  });

  const save = useMutation({
    mutationFn: () => {
      const common = {
        description: form.description.trim() || null,
        max_discount: dec(form.max_discount),
        min_order_amount: dec(form.min_order_amount),
        starts_at: fromLocalInput(form.starts_at),
        expires_at: fromLocalInput(form.expires_at),
        max_uses: form.max_uses ? Number(form.max_uses) : null,
        per_user_limit: Number(form.per_user_limit || 1),
        first_order_only: form.first_order_only,
        is_active: form.is_active,
      };
      return editing === "new"
        ? api("/promo-codes", { method: "POST", body: { ...common, code: form.code.trim(), kind: form.kind, value: dec(form.value) } })
        : api(`/promo-codes/${(editing as Promo).id}`, { method: "PATCH", body: common });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["promos"] });
      setEditing(null);
      toast("Промокод сохранён");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));
  const items = promos.data?.items ?? [];

  return (
    <>
      <PageTitle
        title="Промокоды"
        subtitle="Скидка резервируется при создании заказа и засчитывается только после подтверждённой оплаты."
        actions={
          editable && (
            <Button
              icon={<Plus className="size-4" />}
              onClick={() => {
                setForm(EMPTY);
                setEditing("new");
              }}
            >
              Новый промокод
            </Button>
          )
        }
      />
      {promos.isError && <ErrorBox text={errorMessage(promos.error)} onRetry={() => promos.refetch()} />}
      <Card className="overflow-hidden">
        {promos.isPending ? (
          <Skeleton className="m-4 h-32" />
        ) : items.length === 0 ? (
          <Empty title="Промокодов пока нет" />
        ) : (
          <div className="overflow-x-auto">
            <table className="data w-full min-w-[820px]">
              <thead>
                <tr>
                  <th>Код</th>
                  <th>Скидка</th>
                  <th>Условия</th>
                  <th>Период</th>
                  <th className="text-right">Использовано</th>
                  <th>Статус</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((p) => {
                  const st = promoStatus(p);
                  return (
                    <tr key={p.id}>
                      <td>
                        <div className="font-mono font-semibold">{p.code}</div>
                        {p.description && <div className="text-[12px] text-text-3">{p.description}</div>}
                      </td>
                      <td className="font-semibold">{p.kind === "percent" ? `${Number(p.value)}%` : formatMoney(p.value, currency)}</td>
                      <td className="text-[12.5px] text-text-2">
                        {p.min_order_amount && <div>от {formatMoney(p.min_order_amount, currency)}</div>}
                        {p.max_discount && <div>не более {formatMoney(p.max_discount, currency)}</div>}
                        <div>{p.per_user_limit} на пользователя</div>
                        {p.first_order_only && <div>только первый заказ</div>}
                      </td>
                      <td className="text-[12.5px] text-text-2">
                        {p.starts_at ? formatDate(p.starts_at) : "сразу"} — {p.expires_at ? formatDate(p.expires_at) : "бессрочно"}
                      </td>
                      <td className="text-right tabular">
                        {p.used}
                        {p.max_uses !== null && ` / ${p.max_uses}`}
                      </td>
                      <td>
                        <Badge tone={st.tone}>{st.label}</Badge>
                      </td>
                      <td>
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="ghost" icon={<BarChart3 className="size-3.5" />} onClick={() => setUsagesOf(p)}>
                            Статистика
                          </Button>
                          {editable && (
                            <Button
                              size="sm"
                              variant="ghost"
                              icon={<Pencil className="size-3.5" />}
                              onClick={() => {
                                setForm({
                                  ...EMPTY,
                                  code: p.code,
                                  description: p.description ?? "",
                                  kind: p.kind,
                                  value: p.value,
                                  max_discount: p.max_discount ?? "",
                                  min_order_amount: p.min_order_amount ?? "",
                                  starts_at: toLocalInput(p.starts_at),
                                  expires_at: toLocalInput(p.expires_at),
                                  max_uses: p.max_uses?.toString() ?? "",
                                  per_user_limit: String(p.per_user_limit),
                                  first_order_only: p.first_order_only,
                                  is_active: p.is_active,
                                });
                                setEditing(p);
                              }}
                            >
                              Изменить
                            </Button>
                          )}
                        </div>
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
        title={editing === "new" ? "Новый промокод" : `Промокод ${form.code}`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditing(null)}>
              Отмена
            </Button>
            <Button loading={save.isPending} onClick={() => save.mutate()} disabled={editing === "new" && (form.code.trim().length < 3 || !form.value)}>
              Сохранить
            </Button>
          </>
        }
      >
        {editing === "new" && (
          <div className="grid grid-cols-3 gap-3">
            <Label label="Код">
              <Input value={form.code} onChange={(e) => set("code", e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ""))} maxLength={32} placeholder="STARS10" />
            </Label>
            <Label label="Тип">
              <Select value={form.kind} onChange={(e) => set("kind", e.target.value as Form["kind"])}>
                <option value="percent">Процент</option>
                <option value="fixed">Фиксированная</option>
              </Select>
            </Label>
            <Label label={form.kind === "percent" ? "Скидка, %" : `Скидка, ${currency}`}>
              <Input inputMode="decimal" value={form.value} onChange={(e) => set("value", e.target.value)} />
            </Label>
          </div>
        )}
        <Label label="Описание (для сотрудников)">
          <Input value={form.description} onChange={(e) => set("description", e.target.value)} maxLength={255} />
        </Label>
        <div className="grid grid-cols-2 gap-3">
          <Label label="Минимальная сумма заказа">
            <Input inputMode="decimal" value={form.min_order_amount} onChange={(e) => set("min_order_amount", e.target.value)} />
          </Label>
          <Label label="Максимальная скидка">
            <Input inputMode="decimal" value={form.max_discount} onChange={(e) => set("max_discount", e.target.value)} />
          </Label>
          <Label label="Начало действия">
            <Input type="datetime-local" value={form.starts_at} onChange={(e) => set("starts_at", e.target.value)} />
          </Label>
          <Label label="Окончание">
            <Input type="datetime-local" value={form.expires_at} onChange={(e) => set("expires_at", e.target.value)} />
          </Label>
          <Label label="Лимит использований" hint="Пусто — без лимита">
            <Input inputMode="numeric" value={form.max_uses} onChange={(e) => set("max_uses", e.target.value.replace(/\D/g, ""))} />
          </Label>
          <Label label="На одного пользователя">
            <Input inputMode="numeric" value={form.per_user_limit} onChange={(e) => set("per_user_limit", e.target.value.replace(/\D/g, ""))} />
          </Label>
        </div>
        <Toggle checked={form.first_order_only} onChange={(v) => set("first_order_only", v)} label="Только для первого заказа" />
        <Toggle checked={form.is_active} onChange={(v) => set("is_active", v)} label="Активен" />
      </Modal>

      <Modal open={usagesOf !== null} onClose={() => setUsagesOf(null)} title={`Использования ${usagesOf?.code ?? ""}`} wide>
        {usages.isPending ? (
          <Skeleton className="h-24" />
        ) : usages.data && usages.data.items.length ? (
          <>
            <p className="text-[13.5px] text-text-2">Скидок по оплаченным заказам: {formatMoney(usages.data.applied_discount_total, currency)}</p>
            <table className="data w-full">
              <thead>
                <tr>
                  <th>Пользователь</th>
                  <th>Скидка</th>
                  <th>Статус</th>
                  <th>Дата</th>
                </tr>
              </thead>
              <tbody>
                {usages.data.items.map((u) => (
                  <tr key={u.id}>
                    <td>{u.user.username ? `@${u.user.username}` : u.user.telegram_id}</td>
                    <td className="tabular">{formatMoney(u.discount, currency)}</td>
                    <td>
                      <Badge tone={u.status === "applied" ? "success" : u.status === "reserved" ? "warning" : "neutral"}>{{ applied: "Засчитан", reserved: "Резерв", released: "Снят" }[u.status] ?? u.status}</Badge>
                    </td>
                    <td className="text-text-2">{formatDate(u.at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <Empty title="Промокод ещё не использовали" />
        )}
      </Modal>
    </>
  );
}
