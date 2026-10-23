import { formatDate, formatMoney, formatStars } from "@starshop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Ban, CircleCheck, StickyNote } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Badge, Button, Card, ErrorBox, KV, Label, Modal, Skeleton, StatusBadge, Textarea, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { can, useAdmin } from "../lib/auth";
import { useShop } from "../lib/shop";
import type { AdminOrder, AdminUserRow, AuditRow } from "../lib/types";

interface UserView {
  user: AdminUserRow;
  stats: { orders_count: number; completed_count: number; total_spent: string; invited: number; rewarded: number };
  orders: AdminOrder[];
  notes: { id: number; text: string; admin: string | null; at: string }[];
  audit: AuditRow[];
  bonus_transactions: { id: number; amount: string; kind: string; comment: string | null; at: string }[];
  referrals: { id: number; referred_id: number; status: string; reward_amount: string | null; reject_reason: string | null; at: string }[];
}

export default function UserPage() {
  const { id = "" } = useParams();
  const admin = useAdmin();
  const { currency } = useShop();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [blockOpen, setBlockOpen] = useState(false);
  const [reason, setReason] = useState("");
  const view = useQuery({ queryKey: ["user", id], queryFn: () => api<UserView>(`/users/${id}`) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["user", id] });

  const addNote = useMutation({
    mutationFn: () => api(`/users/${id}/notes`, { method: "POST", body: { text: note } }),
    onSuccess: () => {
      setNote("");
      refresh();
      toast("Заметка сохранена");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const block = useMutation({
    mutationFn: (blocked: boolean) => (blocked ? api(`/users/${id}/block`, { method: "POST", body: { reason } }) : api(`/users/${id}/unblock`, { method: "POST" })),
    onSuccess: () => {
      setBlockOpen(false);
      setReason("");
      refresh();
      toast("Готово");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (view.isPending) return <Skeleton className="h-96" />;
  if (view.isError || !view.data) return <ErrorBox text={errorMessage(view.error)} onRetry={() => view.refetch()} />;
  const { user: u, stats } = view.data;

  return (
    <>
      <Link to="/users" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-semibold text-text-3 hover:text-text">
        <ArrowLeft className="size-4" /> Пользователи
      </Link>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="font-display text-[24px] font-semibold tracking-[-0.03em]">{u.display_name}</h1>
        {u.is_blocked ? <Badge tone="danger">Заблокирован</Badge> : <Badge tone="success">Активен</Badge>}
        {can(admin, "manager") &&
          (u.is_blocked ? (
            <Button size="sm" variant="secondary" icon={<CircleCheck className="size-4" />} loading={block.isPending} onClick={() => block.mutate(false)}>
              Разблокировать
            </Button>
          ) : (
            <Button size="sm" variant="danger" icon={<Ban className="size-4" />} onClick={() => setBlockOpen(true)}>
              Заблокировать
            </Button>
          ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6">
          <Card title="Профиль">
            <KV
              items={[
                ["Telegram ID", u.telegram_id],
                ["Username", u.username ? `@${u.username}` : "—"],
                ["Первый запуск", formatDate(u.first_seen_at)],
                ["Последний визит", formatDate(u.last_seen_at)],
                ["Бот запущен", u.bot_started ? "да" : "нет"],
                ["Реферальный код", u.referral_code],
                ["Пригласил", u.referred_by_id ? <Link key="r" className="text-accent" to={`/users/${u.referred_by_id}`}>пользователь #{u.referred_by_id}</Link> : "—"],
                ["Бонусы", formatMoney(u.bonus_balance, currency)],
                ...(u.is_blocked ? ([["Причина блокировки", u.blocked_reason]] as [string, string | null][]) : []),
              ]}
            />
          </Card>
          <Card title="Статистика">
            <KV
              items={[
                ["Заказов", stats.orders_count],
                ["Выполнено", stats.completed_count],
                ["Сумма покупок", formatMoney(stats.total_spent, currency)],
                ["Приглашено", `${stats.invited} (с бонусом: ${stats.rewarded})`],
              ]}
            />
          </Card>
          <Card title="Заметки сотрудников">
            <div className="space-y-3 p-5">
              <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Видна только сотрудникам" rows={3} />
              <Button size="sm" icon={<StickyNote className="size-4" />} disabled={!note.trim()} loading={addNote.isPending} onClick={() => addNote.mutate()}>
                Добавить заметку
              </Button>
              <ul className="space-y-2">
                {view.data.notes.map((n) => (
                  <li key={n.id} className="rounded-xl bg-surface-2 p-3 text-[13px]">
                    <p className="whitespace-pre-wrap">{n.text}</p>
                    <div className="mt-1 text-[11.5px] text-text-3">
                      {n.admin ?? "—"} · {formatDate(n.at)}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </Card>
        </div>
        <div className="space-y-6 lg:col-span-2">
          <Card title="Заказы">
            {view.data.orders.length === 0 ? (
              <p className="p-5 text-[13.5px] text-text-3">Заказов нет.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="data w-full min-w-[560px]">
                  <thead>
                    <tr>
                      <th>Заказ</th>
                      <th>Дата</th>
                      <th className="text-right">Stars</th>
                      <th className="text-right">Сумма</th>
                      <th>Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.data.orders.map((o) => (
                      <tr key={o.id} className="clickable" onClick={() => navigate(`/orders/${o.id}`)}>
                        <td className="font-semibold">#{o.number}</td>
                        <td className="text-text-2">{formatDate(o.created_at)}</td>
                        <td className="text-right tabular">{formatStars(o.stars_amount)}</td>
                        <td className="text-right tabular">{formatMoney(o.total, o.currency)}</td>
                        <td>
                          <StatusBadge status={o.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Card title="Бонусный баланс">
            {view.data.bonus_transactions.length === 0 ? (
              <p className="p-5 text-[13.5px] text-text-3">Операций нет.</p>
            ) : (
              <ul className="divide-y divide-line">
                {view.data.bonus_transactions.map((b) => (
                  <li key={b.id} className="flex items-center justify-between gap-3 px-5 py-2.5 text-[13px]">
                    <span>
                      <span className="font-semibold">{b.kind}</span> <span className="text-text-3">{b.comment}</span>
                    </span>
                    <span className={Number(b.amount) > 0 ? "font-semibold text-success" : "font-semibold"}>{formatMoney(b.amount, currency)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Журнал действий по пользователю">
            {view.data.audit.length === 0 ? (
              <p className="p-5 text-[13.5px] text-text-3">Действий не было.</p>
            ) : (
              <ul className="divide-y divide-line">
                {view.data.audit.map((a) => (
                  <li key={a.id} className="px-5 py-2.5 text-[13px]">
                    <span className="font-semibold">{a.action}</span> <span className="text-text-2">{a.summary}</span>
                    <div className="text-[11.5px] text-text-3">
                      {formatDate(a.at)} · admin #{a.admin_id}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <Modal
        open={blockOpen}
        onClose={() => setBlockOpen(false)}
        title="Заблокировать пользователя"
        footer={
          <>
            <Button variant="ghost" onClick={() => setBlockOpen(false)}>
              Отмена
            </Button>
            <Button variant="danger" disabled={reason.trim().length < 3} loading={block.isPending} onClick={() => block.mutate(true)}>
              Заблокировать
            </Button>
          </>
        }
      >
        <p className="text-[13.5px] text-text-2">Пользователь не сможет оформлять заказы и писать в поддержку. Уже оплаченные заказы продолжат обрабатываться.</p>
        <Label label="Причина">
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
        </Label>
      </Modal>
    </>
  );
}
