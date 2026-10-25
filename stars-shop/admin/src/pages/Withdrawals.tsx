import { formatDate, formatMoney, formatStars, STATUS_META } from "@starshop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, Check, RotateCcw, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Badge, Button, Card, Empty, ErrorBox, Label, Modal, PageTitle, Pagination, Skeleton, Tabs, Textarea, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { can, useAdmin } from "../lib/auth";
import { useShop } from "../lib/shop";

interface Row {
  id: number;
  stars: number;
  amount: string;
  rate: string;
  status: "pending" | "approved" | "rejected" | "returned";
  comment: string | null;
  created_at: string;
  decided_at: string | null;
  order: { id: string; number: string; status: keyof typeof STATUS_META } | null;
  user: { id: number; telegram_id: number; username: string | null; display_name: string; bonus_balance: string };
}

const FILTERS = [
  { id: "pending", label: "На проверке" },
  { id: "approved", label: "Одобренные" },
  { id: "rejected", label: "Отклонённые" },
  { id: "returned", label: "Возвращённые" },
  { id: "", label: "Все" },
];
const STATUS = {
  pending: { label: "На проверке", tone: "warning" },
  approved: { label: "Одобрен", tone: "info" },
  rejected: { label: "Отклонён", tone: "neutral" },
  returned: { label: "Бонусы возвращены", tone: "neutral" },
} as const;
const LIMIT = 50;

export default function Withdrawals() {
  const admin = useAdmin();
  const { currency } = useShop();
  const editable = can(admin, "manager");
  const qc = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState("pending");
  const [offset, setOffset] = useState(0);
  const [rejecting, setRejecting] = useState<Row | null>(null);
  const [comment, setComment] = useState("");
  const data = useQuery({
    queryKey: ["withdrawals", status, offset],
    queryFn: () => api<{ items: Row[]; total: number; pending: number }>(`/withdrawals?limit=${LIMIT}&offset=${offset}${status ? `&status=${status}` : ""}`),
    refetchInterval: 30_000,
  });
  const act = useMutation({
    mutationFn: ({ id, action, body }: { id: number; action: "approve" | "reject" | "return"; body?: unknown }) =>
      api<Row>(`/withdrawals/${id}/${action}`, { method: "POST", body }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ["withdrawals"] });
      setRejecting(null);
      setComment("");
      toast(v.action === "approve" ? "Одобрено: звёзды уходят на доставку" : v.action === "reject" ? "Отклонено, бонусы возвращены" : "Бонусы возвращены", "success");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <>
      <PageTitle
        title="Выводы"
        subtitle="Заявки на вывод реферальных бонусов звёздами. При заявке бонусы замораживаются; одобренная заявка становится заказом Stars на аккаунт пользователя."
      />
      <div className="mb-4">
        <Tabs
          value={status}
          onChange={(v) => {
            setStatus(v);
            setOffset(0);
          }}
          items={FILTERS.map((f) => (f.id === "pending" && data.data?.pending ? { ...f, label: `${f.label} · ${data.data.pending}` } : f))}
        />
      </div>
      {data.isError && <ErrorBox text={errorMessage(data.error)} onRetry={() => data.refetch()} />}
      <Card className="overflow-hidden">
        {data.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : !data.data?.items.length ? (
          <Empty title="Заявок нет" text="Здесь появятся заявки на вывод бонусов." icon={<ArrowDownToLine className="size-6" />} />
        ) : (
          <div className="overflow-x-auto">
            <table className="data w-full min-w-[820px]">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Пользователь</th>
                  <th className="text-right">Stars</th>
                  <th className="text-right">Бонусы</th>
                  <th>Создана</th>
                  <th>Статус</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.data.items.map((w) => {
                  const orderFailed = w.order?.status === "failed";
                  return (
                    <tr key={w.id}>
                      <td className="tabular text-text-3">{w.id}</td>
                      <td>
                        <Link to={`/users/${w.user.id}`} className="font-semibold hover:text-accent">
                          {w.user.username ? `@${w.user.username}` : w.user.display_name}
                        </Link>
                        <div className="text-[12px] text-text-3">
                          ID {w.user.telegram_id} · баланс {formatMoney(w.user.bonus_balance, currency)}
                        </div>
                      </td>
                      <td className="text-right font-semibold tabular">{formatStars(w.stars)}</td>
                      <td className="text-right tabular">
                        {formatMoney(w.amount, currency)}
                        <div className="text-[11.5px] text-text-3">по {formatMoney(w.rate, currency)}</div>
                      </td>
                      <td className="text-[13px] text-text-2">{formatDate(w.created_at)}</td>
                      <td>
                        <Badge tone={STATUS[w.status].tone}>{STATUS[w.status].label}</Badge>
                        {w.order && (
                          <div className="mt-1 text-[12px]">
                            <Link to={`/orders/${w.order.id}`} className="text-accent">
                              #{w.order.number}
                            </Link>{" "}
                            · {STATUS_META[w.order.status].label}
                          </div>
                        )}
                        {w.comment && <div className="mt-1 max-w-[220px] text-[12px] text-text-3">{w.comment}</div>}
                      </td>
                      <td>
                        {editable && w.status === "pending" && (
                          <div className="flex justify-end gap-1.5">
                            <Button
                              size="sm"
                              icon={<Check className="size-3.5" />}
                              loading={act.isPending && act.variables?.id === w.id && act.variables.action === "approve"}
                              onClick={() => window.confirm(`Отправить ${w.stars} Stars пользователю?`) && act.mutate({ id: w.id, action: "approve" })}
                            >
                              Одобрить
                            </Button>
                            <Button size="sm" variant="danger" icon={<X className="size-3.5" />} onClick={() => setRejecting(w)}>
                              Отклонить
                            </Button>
                          </div>
                        )}
                        {editable && w.status === "approved" && orderFailed && (
                          <div className="flex justify-end">
                            <Button
                              size="sm"
                              variant="secondary"
                              icon={<RotateCcw className="size-3.5" />}
                              onClick={() => window.confirm("Звёзды не доставлены. Закрыть заказ и вернуть бонусы?") && act.mutate({ id: w.id, action: "return" })}
                            >
                              Вернуть бонусы
                            </Button>
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
      {data.data && data.data.total > LIMIT && <Pagination total={data.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}

      <Modal
        open={rejecting !== null}
        onClose={() => setRejecting(null)}
        title={`Отклонить заявку #${rejecting?.id ?? ""}`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRejecting(null)}>
              Отмена
            </Button>
            <Button
              variant="danger"
              disabled={comment.trim().length < 3}
              loading={act.isPending}
              onClick={() => rejecting && act.mutate({ id: rejecting.id, action: "reject", body: { comment: comment.trim() } })}
            >
              Отклонить и вернуть бонусы
            </Button>
          </>
        }
      >
        <Label label="Причина" hint="Пользователь увидит её в уведомлении">
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={255} />
        </Label>
      </Modal>
    </>
  );
}
