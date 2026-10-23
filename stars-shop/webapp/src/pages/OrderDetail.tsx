import type { OrderDetail, OrderStatus } from "@starshop/shared";
import { formatDate, formatMoney, formatRate, formatStars, STATUS_META, TelegramStar } from "@starshop/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Check, Clock3, CreditCard, LifeBuoy, RefreshCw, RotateCcw, Sparkles, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { useBoot } from "../components/BootContext";
import { Page, PageHeader } from "../components/Layout";
import { SummaryRow } from "../components/checkout/parts";
import { DemoBadge, StatusBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { Skeleton } from "../components/ui/Skeleton";
import { ErrorState } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { cn } from "../components/ui/cn";
import { api, errorMessage } from "../lib/api";
import { keys, useCreatePayment, useInvalidateOrders, useOrder } from "../lib/queries";
import { haptic, openPayment } from "../lib/telegram";

const TONE_GLOW: Record<string, string> = {
  neutral: "from-text-3/30 to-text-3/5",
  warning: "from-warning/35 to-warning/5",
  info: "from-accent/40 to-accent/5",
  success: "from-success/40 to-success/5",
  danger: "from-danger/40 to-danger/5",
  violet: "from-accent-2/40 to-accent-2/5",
};

const TONE_TEXT: Record<string, string> = {
  neutral: "text-text-2",
  warning: "text-warning",
  info: "text-accent",
  success: "text-success",
  danger: "text-danger",
  violet: "text-accent-2",
};

function StatusIcon({ status }: { status: OrderStatus }) {
  const cls = "size-8";
  switch (status) {
    case "completed":
      return <Check className={cls} strokeWidth={2.6} />;
    case "failed":
      return <TriangleAlert className={cls} />;
    case "cancelled":
      return <X className={cls} />;
    case "refund_pending":
    case "refunded":
      return <RotateCcw className={cls} />;
    case "pending_payment":
    case "created":
      return <CreditCard className={cls} />;
    default:
      return <Sparkles className={cls} />;
  }
}

const TRACK: { id: string; label: string; statuses: OrderStatus[] }[] = [
  { id: "created", label: "Создан", statuses: ["created", "pending_payment"] },
  { id: "paid", label: "Оплачен", statuses: ["paid"] },
  { id: "processing", label: "Доставка", statuses: ["processing", "failed"] },
  { id: "completed", label: "Готово", statuses: ["completed"] },
];

function Tracker({ status }: { status: OrderStatus }) {
  if (status === "cancelled" || status === "refunded" || status === "refund_pending") return null;
  const index = TRACK.findIndex((t) => t.statuses.includes(status));
  return (
    <div className="mt-6 grid grid-cols-4 gap-1.5" aria-label="Прогресс заказа">
      {TRACK.map((t, i) => {
        const done = i < index || status === "completed";
        const active = i === index && status !== "completed";
        const failed = active && status === "failed";
        return (
          <div key={t.id} className="flex flex-col gap-2">
            <div className="h-1.5 overflow-hidden rounded-full bg-surface-3">
              <motion.div
                className={cn("h-full rounded-full", failed ? "bg-danger" : "bg-accent-gradient")}
                initial={{ width: 0 }}
                animate={{ width: done ? "100%" : active ? "55%" : "0%" }}
                transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
            <span className={cn("text-[11.5px] font-semibold", done || active ? "text-text" : "text-text-3")}>{t.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function Countdown({ until }: { until: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const left = Math.max(0, Math.floor((new Date(until).getTime() - now) / 1000));
  if (left <= 0) return <span>время на оплату истекло</span>;
  const m = Math.floor(left / 60);
  const s = String(left % 60).padStart(2, "0");
  return (
    <span>
      оплатите в течение <b className="tabular text-text">{m}:{s}</b>
    </span>
  );
}

function StatusCard({ order }: { order: OrderDetail }) {
  const meta = STATUS_META[order.status];
  const active = ["pending_payment", "paid", "processing"].includes(order.status);
  return (
    <Card className="relative overflow-hidden p-6 text-center">
      <div className={cn("pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b opacity-60", TONE_GLOW[meta.tone])} aria-hidden />
      <div className={cn("relative mx-auto flex size-20 items-center justify-center", TONE_TEXT[meta.tone])}>
        {active && <span className="absolute inset-0 rounded-full bg-current opacity-25 animate-[pulse-ring_2s_ease-out_infinite]" />}
        <span className="relative flex size-20 items-center justify-center rounded-full bg-surface ring-1 ring-line shadow-card">
          <StatusIcon status={order.status} />
        </span>
      </div>
      <div className="relative mt-4 flex items-center justify-center gap-2">
        <h2 className="font-display text-[22px] font-bold tracking-[-0.03em]">{meta.label}</h2>
        {order.mode === "demo" && <DemoBadge />}
      </div>
      <p className="relative mx-auto mt-1.5 max-w-[320px] text-[13.5px] leading-relaxed text-text-2">
        {order.mode === "demo" && order.status === "completed" ? "DEMO-заказ выполнен: реальные Stars не отправлялись." : meta.hint}
      </p>
      {order.status === "pending_payment" && order.expires_at && (
        <p className="relative mt-2 inline-flex items-center gap-1.5 text-[12.5px] text-text-3">
          <Clock3 className="size-3.5" />
          <Countdown until={order.expires_at} />
        </p>
      )}
      <div className="relative mt-5 flex items-center justify-center gap-2.5">
        <TelegramStar size={30} />
        <span className="font-display text-[30px] font-bold tracking-[-0.04em] tabular">{formatStars(order.stars_amount)}</span>
        <span className="text-[14px] font-semibold text-text-3">Stars</span>
      </div>
      <div className="relative mt-1 text-[13.5px] text-text-2">{order.recipient.type === "self" ? "Себе" : `для @${order.recipient.username}`}</div>
      <Tracker status={order.status} />
    </Card>
  );
}

export function OrderDetailPage() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const boot = useBoot();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const invalidate = useInvalidateOrders();
  const order = useOrder(id);
  const createPayment = useCreatePayment();
  const [confirmCancel, setConfirmCancel] = useState(false);

  const prevStatus = useRef<OrderStatus | undefined>(undefined);
  useEffect(() => {
    const s = order.data?.status;
    if (!s) return;
    if (prevStatus.current && prevStatus.current !== s) {
      if (s === "completed") haptic.success();
      if (s === "failed") haptic.error();
      invalidate();
    }
    prevStatus.current = s;
  }, [order.data?.status, invalidate]);

  const check = useMutation({
    mutationFn: () => api<{ result: string; order: OrderDetail }>(`/orders/${id}/check-payment`, { method: "POST" }),
    onSuccess: (r) => {
      qc.setQueryData(keys.order(id), r.order);
      if (r.result === "confirmed") toast("Оплата подтверждена!", "success");
      else if (r.order.status === "pending_payment") toast("Провайдер пока не подтвердил оплату. Мы проверим ещё раз автоматически", "info");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const cancel = useMutation({
    mutationFn: () => api<OrderDetail>(`/orders/${id}/cancel`, { method: "POST" }),
    onSuccess: (o) => {
      qc.setQueryData(keys.order(id), o);
      invalidate();
      setConfirmCancel(false);
      toast("Заказ отменён", "info");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const payNow = async () => {
    const o = order.data;
    if (!o) return;
    try {
      const payment = o.payment?.pay_url ? o.payment : await createPayment.mutateAsync({ orderId: o.id, provider: o.payment_provider });
      if (payment.pay_url_kind === "internal") navigate(`/pay/demo/${payment.id}`);
      else if (payment.pay_url) openPayment(payment.pay_url, payment.pay_url_kind);
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  if (order.isPending)
    return (
      <>
        <PageHeader title="Заказ" />
        <Page className="space-y-3">
          <Skeleton className="h-[340px] rounded-[28px]" />
          <Skeleton className="h-[220px] rounded-[28px]" />
        </Page>
      </>
    );
  if (order.isError || !order.data)
    return (
      <>
        <PageHeader title="Заказ" />
        <Page>
          <ErrorState text={errorMessage(order.error)} onRetry={() => order.refetch()} />
        </Page>
      </>
    );

  const o = order.data;
  const c = o.amounts.currency;
  return (
    <>
      <PageHeader title={`Заказ #${o.number}`} subtitle={formatDate(o.created_at, boot.timezone)} right={<StatusBadge status={o.status} />} />
      <Page className="space-y-4">
        {params.get("paying") && o.status === "pending_payment" && (
          <div className="rounded-[20px] bg-accent/10 p-4 text-[13.5px] leading-relaxed text-text-2 ring-1 ring-inset ring-accent/25">
            Завершите оплату на странице провайдера и вернитесь сюда — статус обновится автоматически.
          </div>
        )}
        <StatusCard order={o} />

        {o.can_pay && (
          <div className="space-y-2.5">
            <Button size="lg" block onClick={payNow} loading={createPayment.isPending} icon={<CreditCard className="size-5" />}>
              Оплатить {formatMoney(o.total, c)}
            </Button>
            {o.payment && !o.payment.is_demo && (
              <Button variant="secondary" size="md" block onClick={() => check.mutate()} loading={check.isPending} icon={<RefreshCw className="size-4" />}>
                Я оплатил — проверить
              </Button>
            )}
            {o.can_cancel && (
              <Button variant="ghost" size="md" block onClick={() => setConfirmCancel(true)}>
                Отменить заказ
              </Button>
            )}
          </div>
        )}
        {o.status === "completed" && (
          <Button size="lg" variant="secondary" block onClick={() => navigate("/catalog")} icon={<Sparkles className="size-5" />}>
            Купить ещё
          </Button>
        )}
        {(o.status === "failed" || o.status === "refund_pending") && (
          <Button size="lg" variant="secondary" block onClick={() => navigate(`/support?order=${o.id}`)} icon={<LifeBuoy className="size-5" />}>
            Написать в поддержку
          </Button>
        )}

        <Card className="px-5 py-2">
          <div className="divide-y divide-line">
            <SummaryRow label="Цена за звезду" value={formatRate(o.amounts.unit_price, c)} />
            <SummaryRow label="Стоимость" value={formatMoney(o.amounts.subtotal, c)} />
            {Number(o.amounts.discount) > 0 && <SummaryRow label="Скидка" value={`−${formatMoney(o.amounts.discount, c)}`} tone="success" />}
            {Number(o.amounts.bonus_spent) > 0 && <SummaryRow label="Бонусы" value={`−${formatMoney(o.amounts.bonus_spent, c)}`} tone="success" />}
            <SummaryRow label="Комиссия" value={Number(o.amounts.fee) > 0 ? formatMoney(o.amounts.fee, c) : "Без комиссии"} />
            <SummaryRow label="Способ оплаты" value={<span className="text-[13.5px]">{o.payment_method}</span>} />
            <SummaryRow label="Итого" value={formatMoney(o.amounts.total, c)} strong />
          </div>
        </Card>

        {o.timeline.length > 0 && (
          <Card className="p-5">
            <h3 className="mb-4 text-[15px] font-semibold">История заказа</h3>
            <ol className="relative space-y-4 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-line-strong">
              {[...o.timeline].reverse().map((e, i) => (
                <li key={`${e.at}-${i}`} className="relative flex gap-3.5 pl-0.5">
                  <span className={cn("relative z-10 mt-1 size-3.5 shrink-0 rounded-full ring-4 ring-surface", i === 0 ? "bg-accent" : "bg-surface-3")} />
                  <div>
                    <div className="text-[14px] font-semibold">{e.message ?? (e.status ? STATUS_META[e.status]?.label : e.type)}</div>
                    <div className="text-[12px] text-text-3">{formatDate(e.at, boot.timezone)}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        )}

        <button onClick={() => navigate(`/support?order=${o.id}`)} className="mx-auto flex items-center gap-1.5 py-2 text-[13.5px] font-semibold text-text-3 hover:text-text">
          <LifeBuoy className="size-4" /> Вопрос по заказу
        </button>
      </Page>
      <ConfirmDialog
        open={confirmCancel}
        title="Отменить заказ?"
        text="Заказ будет закрыт. Если вы уже оплатили — не отменяйте, а нажмите «Я оплатил — проверить»."
        confirmLabel="Отменить заказ"
        tone="danger"
        loading={cancel.isPending}
        onConfirm={() => cancel.mutate()}
        onClose={() => setConfirmCancel(false)}
      />
    </>
  );
}
