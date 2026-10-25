import { formatDate, formatMoney, formatRate, formatStars, formatRoll } from "@starshop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Ban, CheckCheck, RefreshCw, RotateCcw, SearchCheck, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Badge, Button, Card, ErrorBox, Input, KV, Label, ModeBadge, Modal, Skeleton, StatusBadge, Textarea, Toggle, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { can, useAdmin } from "../lib/auth";
import type { OrderView } from "../lib/types";

type Action = "cancel" | "retry" | "confirm" | "fail" | "refund" | "manual_refund" | null;

const PAYMENT_STATUS: Record<string, string> = {
  created: "Создан",
  pending: "Ожидает",
  succeeded: "Подтверждён",
  failed: "Ошибка",
  expired: "Истёк",
  cancelled: "Отменён",
  refund_pending: "Возврат",
  refunded: "Возвращён",
};

const TASK_STATUS: Record<string, string> = {
  queued: "В очереди",
  in_progress: "Выполняется",
  waiting_provider: "Ждём поставщика",
  needs_attention: "Нужен оператор",
  succeeded: "Доставлено",
  failed: "Ошибка",
  cancelled: "Отменена",
};

export default function OrderPage() {
  const { id = "" } = useParams();
  const admin = useAdmin();
  const toast = useToast();
  const qc = useQueryClient();
  const [action, setAction] = useState<Action>(null);
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const [confirmNotDelivered, setConfirmNotDelivered] = useState(false);
  const [allowCompleted, setAllowCompleted] = useState(false);

  const view = useQuery({ queryKey: ["order", id], queryFn: () => api<OrderView>(`/orders/${id}`), refetchInterval: 10_000 });

  const run = useMutation({
    mutationFn: async (a: NonNullable<Action> | "check") => {
      const base = `/orders/${id}`;
      switch (a) {
        case "check":
          return api<OrderView & { result: string }>(`${base}/check-payment`, { method: "POST" });
        case "cancel":
          return api<OrderView>(`${base}/cancel`, { method: "POST", body: { reason } });
        case "retry":
          return api<OrderView>(`${base}/retry-delivery`, { method: "POST", body: { confirm_not_delivered: confirmNotDelivered } });
        case "confirm":
          return api<OrderView>(`${base}/confirm-delivery`, { method: "POST", body: { reference, note: reason || null } });
        case "fail":
          return api<OrderView>(`${base}/mark-failed`, { method: "POST", body: { reason } });
        case "refund":
          return api<OrderView>(`${base}/refund`, { method: "POST", body: { reason, allow_completed: allowCompleted } });
        case "manual_refund": {
          const p = view.data?.payments.find((x) => x.status === "refund_pending");
          return api<OrderView>(`${base}/payments/${p?.id}/confirm-refund`, { method: "POST", body: { reference, note: reason || null } });
        }
      }
    },
    onSuccess: (data, a) => {
      if (data) qc.setQueryData(["order", id], data);
      qc.invalidateQueries({ queryKey: ["orders"] });
      setAction(null);
      setReason("");
      setReference("");
      if (a === "check") toast(`Провайдер: ${(data as { result?: string }).result ?? "проверено"}`);
      else toast("Готово");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (view.isPending) return <Skeleton className="h-96" />;
  if (view.isError || !view.data) return <ErrorBox text={errorMessage(view.error)} onRetry={() => view.refetch()} />;

  const { order: o, payments, delivery, lucky, events, webhooks, actions } = view.data;
  const c = o.currency;
  const isManager = can(admin, "manager");
  const margin = o.cost !== null ? Number(o.total) - Number(o.cost) : null;
  const open = (a: Action) => {
    setReason("");
    setReference("");
    setConfirmNotDelivered(false);
    setAllowCompleted(false);
    setAction(a);
  };

  return (
    <>
      <Link to="/orders" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-semibold text-text-3 hover:text-text">
        <ArrowLeft className="size-4" /> Все заказы
      </Link>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="font-display text-[24px] font-semibold tracking-[-0.03em]">Заказ #{o.number}</h1>
        <StatusBadge status={o.status} />
        <ModeBadge mode={o.mode} />
        {o.kind === "lucky" && <Badge tone="info">Lucky Buy</Badge>}
      </div>

      {(actions.length > 0 || o.failure_reason) && (
        <Card className="mb-6 p-4">
          {o.failure_reason && (
            <p className="mb-3 flex items-start gap-2 text-[13.5px] text-danger">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" /> {o.failure_reason}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {actions.includes("check_payment") && (
              <Button variant="secondary" icon={<SearchCheck className="size-4" />} loading={run.isPending && run.variables === "check"} onClick={() => run.mutate("check")}>
                Проверить оплату у провайдера
              </Button>
            )}
            {isManager && actions.includes("confirm_delivery") && (
              <Button icon={<CheckCheck className="size-4" />} onClick={() => open("confirm")}>
                Подтвердить доставку
              </Button>
            )}
            {isManager && actions.includes("retry_delivery") && (
              <Button variant="secondary" icon={<RefreshCw className="size-4" />} onClick={() => open("retry")}>
                Повторить доставку
              </Button>
            )}
            {isManager && actions.includes("mark_failed") && (
              <Button variant="secondary" icon={<TriangleAlert className="size-4" />} onClick={() => open("fail")}>
                Доставка не удалась
              </Button>
            )}
            {isManager && (actions.includes("refund") || (actions.includes("refund_completed") && can(admin, "owner"))) && (
              <Button variant="danger" icon={<RotateCcw className="size-4" />} onClick={() => open("refund")}>
                Оформить возврат
              </Button>
            )}
            {can(admin, "owner") && actions.includes("confirm_manual_refund") && (
              <Button variant="secondary" icon={<CheckCheck className="size-4" />} onClick={() => open("manual_refund")}>
                Подтвердить ручной возврат
              </Button>
            )}
            {isManager && actions.includes("cancel") && (
              <Button variant="ghost" icon={<Ban className="size-4" />} onClick={() => open("cancel")}>
                Отменить заказ
              </Button>
            )}
          </div>
          <p className="mt-3 text-[12px] text-text-3">Отметить заказ оплаченным вручную нельзя: оплату подтверждает только провайдер. Все действия записываются в журнал.</p>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Состав и сумма">
            <KV
              items={
                lucky
                  ? [
                      ["Приз", `${formatStars(o.stars_amount)} Stars · ${formatMoney(lucky.prize_value, c)}`],
                      ["Шанс", `${lucky.chance}%`],
                      ["Цена попытки", formatMoney(o.subtotal, c)],
                      ["Комиссия", formatMoney(o.fee, c)],
                      ["Итого", <b key="t">{formatMoney(o.total, c)}</b>],
                      ["Себестоимость", o.cost ? formatMoney(o.cost, c) : lucky.won === null ? "после розыгрыша" : "не указана"],
                      ["Маржа", margin !== null ? formatMoney(margin, c) : "—"],
                    ]
                  : [
                      o.premium_months ? ["Товар", o.item] : ["Stars", formatStars(o.stars_amount)],
                      ["Цена за звезду", formatRate(o.unit_price, c)],
                      ["Стоимость", formatMoney(o.subtotal, c)],
                      ["Скидка", Number(o.discount) ? `−${formatMoney(o.discount, c)}` : "—"],
                      ["Бонусы", Number(o.bonus_spent) ? `−${formatMoney(o.bonus_spent, c)}` : "—"],
                      ["Комиссия", formatMoney(o.fee, c)],
                      ["Итого", <b key="t">{formatMoney(o.total, c)}</b>],
                      ["Себестоимость", o.cost ? formatMoney(o.cost, c) : "не указана"],
                      ["Маржа", margin !== null ? formatMoney(margin, c) : "—"],
                    ]
              }
            />
          </Card>

          <Card title="Платежи">
            {payments.length === 0 ? (
              <p className="p-5 text-[13.5px] text-text-3">Платёж ещё не создавался.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="data w-full min-w-[640px]">
                  <thead>
                    <tr>
                      <th>Провайдер</th>
                      <th>ID у провайдера</th>
                      <th>Сумма</th>
                      <th>Оплачено</th>
                      <th>Статус</th>
                      <th>Создан</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payments.map((p) => (
                      <tr key={p.id}>
                        <td>{p.provider}</td>
                        <td className="font-mono text-[12px] text-text-2">{p.provider_payment_id ?? "—"}</td>
                        <td className="tabular">{formatMoney(p.amount, p.currency)}</td>
                        <td className="tabular text-text-2">{p.paid_amount ? `${p.paid_amount} ${p.paid_asset ?? ""}` : "—"}</td>
                        <td>
                          <Badge tone={p.status === "succeeded" ? "success" : p.status === "failed" ? "danger" : p.status.startsWith("refund") ? "violet" : "neutral"}>{PAYMENT_STATUS[p.status] ?? p.status}</Badge>
                          {p.is_duplicate && <Badge tone="warning" className="ml-1">дубль</Badge>}
                          {p.last_error && <div className="mt-1 max-w-[260px] text-[11.5px] text-danger">{p.last_error}</div>}
                          {p.refund_reference && <div className="mt-1 text-[11.5px] text-text-3">ref: {p.refund_reference}</div>}
                        </td>
                        <td className="whitespace-nowrap text-text-2">{formatDate(p.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Журнал событий">
            <ol className="divide-y divide-line">
              {[...events].reverse().map((e) => (
                <li key={e.id} className="flex gap-4 px-5 py-3 text-[13px]">
                  <span className="w-[136px] shrink-0 whitespace-nowrap text-text-3">{formatDate(e.at)}</span>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold">
                      {e.message ?? e.type}
                      {e.from_status && e.to_status && (
                        <span className="ml-2 font-normal text-text-3">
                          {e.from_status} → {e.to_status}
                        </span>
                      )}
                    </div>
                    <div className="text-[12px] text-text-3">
                      {e.type} · {e.actor_type}
                      {e.actor_id ? ` (${e.actor_id})` : ""}
                      {!e.is_public && " · внутреннее"}
                    </div>
                    {e.data && <pre className="mt-1 max-w-full overflow-x-auto rounded-lg bg-surface-2 p-2 text-[11px] text-text-2">{JSON.stringify(e.data, null, 1)}</pre>}
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </div>

        <div className="space-y-6">
          {lucky && (
            <Card title="Lucky Buy">
              <KV
                items={[
                  ["Шанс", `${lucky.chance}%`],
                  [
                    "Результат",
                    lucky.won === null ? (
                      "розыгрыш после оплаты"
                    ) : (
                      <Badge key="r" tone={lucky.won ? "success" : "neutral"}>
                        {lucky.won ? "выигрыш" : "без выигрыша"}
                      </Badge>
                    ),
                  ],
                  ["Выпало", lucky.roll_bp !== null ? `${formatRoll(lucky.roll_bp).replace(".", ",")} (нужно меньше ${lucky.chance})` : "—"],
                  ["Розыгрыш", lucky.drawn_at ? formatDate(lucky.drawn_at) : "—"],
                ]}
              />
              <div className="space-y-2 border-t border-line px-5 py-4 text-[12px]">
                <div>
                  <div className="text-text-3">Хэш сида сервера</div>
                  <div className="break-all font-mono text-text-2">{lucky.server_seed_hash}</div>
                </div>
                <div>
                  <div className="text-text-3">Сид сервера</div>
                  <div className="break-all font-mono text-text-2">{lucky.server_seed ?? "раскрывается после розыгрыша"}</div>
                </div>
                <div>
                  <div className="text-text-3">Сид клиента · nonce</div>
                  <div className="break-all font-mono text-text-2">
                    {lucky.client_seed ?? "—"} · {lucky.nonce}
                  </div>
                </div>
              </div>
            </Card>
          )}
          <Card title="Покупатель">
            <KV
              items={[
                ["Пользователь", o.user ? <Link key="u" className="text-accent" to={`/users/${o.user_id}`}>{o.user.username ? `@${o.user.username}` : o.user.display_name}</Link> : "—"],
                ["Telegram ID", o.user?.telegram_id],
                ["Получатель", o.recipient.type === "self" ? `себе${o.recipient.username ? ` (@${o.recipient.username})` : ""}` : `@${o.recipient.username}`],
              ]}
            />
          </Card>
          <Card title="Доставка">
            {delivery ? (
              <>
                <KV
                  items={[
                    ["Способ", delivery.provider],
                    ["Статус", TASK_STATUS[delivery.status] ?? delivery.status],
                    ["Попытки", `${delivery.attempts} / ${delivery.max_attempts}`],
                    ["ID у поставщика", delivery.external_id ?? "—"],
                    ["Ошибка", delivery.last_error ?? "—"],
                    ["Завершена", delivery.completed_at ? formatDate(delivery.completed_at) : "—"],
                  ]}
                />
                {delivery.result && <pre className="m-4 mt-0 overflow-x-auto rounded-lg bg-surface-2 p-3 text-[11px] text-text-2">{JSON.stringify(delivery.result, null, 1)}</pre>}
              </>
            ) : (
              <p className="p-5 text-[13.5px] text-text-3">Задача доставки создаётся после подтверждения оплаты.</p>
            )}
          </Card>
          <Card title="Даты">
            <KV
              items={[
                ["Создан", formatDate(o.created_at)],
                ["Оплачен", o.paid_at ? formatDate(o.paid_at) : "—"],
                ["Выполнен", o.completed_at ? formatDate(o.completed_at) : "—"],
                ["Отменён", o.cancelled_at ? formatDate(o.cancelled_at) : "—"],
                ["Возврат", o.refunded_at ? formatDate(o.refunded_at) : "—"],
              ]}
            />
          </Card>
          {webhooks.length > 0 && (
            <Card title="Webhook-события">
              <ul className="divide-y divide-line text-[12.5px]">
                {webhooks.map((w) => (
                  <li key={w.id} className="px-5 py-2.5">
                    <div className="font-semibold">
                      {w.provider} · {w.type ?? "—"} <span className="text-text-3">{w.status}</span>
                    </div>
                    <div className="text-text-3">{formatDate(w.received_at)} · {w.event_id ?? "без id"}</div>
                    {w.error && <div className="text-danger">{w.error}</div>}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>

      <Modal
        open={action !== null}
        onClose={() => setAction(null)}
        title={
          { cancel: "Отменить заказ", retry: "Повторить доставку", confirm: "Подтвердить доставку", fail: "Отметить доставку неуспешной", refund: "Оформить возврат", manual_refund: "Подтвердить ручной возврат" }[action ?? "cancel"]
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setAction(null)}>
              Отмена
            </Button>
            <Button
              variant={action === "refund" || action === "cancel" ? "danger" : "primary"}
              loading={run.isPending}
              disabled={
                ((action === "cancel" || action === "fail" || action === "refund") && reason.trim().length < 3) ||
                ((action === "confirm" || action === "manual_refund") && reference.trim().length < 4) ||
                (action === "refund" && (o.status === "completed" || o.status === "lost") && !allowCompleted)
              }
              onClick={() => action && run.mutate(action)}
            >
              Подтвердить
            </Button>
          </>
        }
      >
        {action === "confirm" && (
          <p className="text-[13.5px] leading-relaxed text-text-2">
            Подтверждайте, только если {o.premium_months ? "Premium действительно подключён" : "Stars действительно зачислены"} получателю <b className="text-text">@{o.recipient.username}</b> ({o.item}). Покупатель получит уведомление о доставке.
          </p>
        )}
        {action === "retry" && (
          <>
            <p className="text-[13.5px] leading-relaxed text-text-2">Задача вернётся в очередь доставки. Если способ доставки не защищён от повторов, сначала убедитесь, что Stars не были зачислены.</p>
            <Toggle checked={confirmNotDelivered} onChange={setConfirmNotDelivered} label="Я проверил: Stars не были доставлены" />
          </>
        )}
        {action === "refund" && (
          <>
            <p className="text-[13.5px] leading-relaxed text-text-2">
              Возврат {formatMoney(o.total, c)} пройдёт через платёжного провайдера. Доставка, если она ещё не началась, будет отменена.
            </p>
            {o.status === "completed" && <Toggle checked={allowCompleted} onChange={setAllowCompleted} label="Заказ выполнен — Stars уже у получателя. Всё равно вернуть деньги" hint="Доступно только владельцу" />}
            {o.status === "lost" && (
              <Toggle checked={allowCompleted} onChange={setAllowCompleted} label="Попытка Lucky Buy не выиграла: по правилам оплата не возвращается. Всё равно вернуть деньги" hint="Исключение, доступно только владельцу" />
            )}
          </>
        )}
        {(action === "confirm" || action === "manual_refund") && (
          <Label label={action === "confirm" ? "ID транзакции / ссылка на подтверждение" : "Номер операции возврата"} hint="Сохраняется в журнале действий">
            <Input value={reference} onChange={(e) => setReference(e.target.value)} placeholder={action === "confirm" ? "Например, хэш транзакции Fragment" : "Например, номер перевода"} />
          </Label>
        )}
        <Label label={action === "confirm" || action === "manual_refund" ? "Комментарий (необязательно)" : action === "retry" ? "Комментарий (необязательно)" : "Причина"}>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
        </Label>
      </Modal>
    </>
  );
}
