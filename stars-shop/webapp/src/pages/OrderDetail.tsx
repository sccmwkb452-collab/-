import type { LuckyDraw, OrderDetail, OrderStatus } from "@starshop/shared";
import { formatDate, formatMoney, formatRate, formatStars, newClientSeed, STATUS_META, TelegramStar } from "@starshop/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
import { Check, Clock3, Clover, CreditCard, Dices, LifeBuoy, RefreshCw, RotateCcw, Sparkles, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { useBoot } from "../components/BootContext";
import { Page, PageHeader } from "../components/Layout";
import { SummaryRow } from "../components/checkout/parts";
import { DrawResult, FairnessCard, LUCKY_FRAME } from "../components/lucky/LuckyParts";
import { DemoBadge, LuckyBadge, StatusBadge } from "../components/ui/Badge";
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
    case "lost":
      return <Dices className={cls} />;
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

function Tracker({ status, lucky }: { status: OrderStatus; lucky?: boolean }) {
  if (status === "cancelled" || status === "refunded" || status === "refund_pending" || status === "lost") return null;
  const index = TRACK.findIndex((t) => t.statuses.includes(status));
  // Lucky Buy is drawn the moment the payment is confirmed.
  const track = lucky ? TRACK.map((t) => (t.id === "paid" ? { ...t, label: "Розыгрыш" } : t)) : TRACK;
  return (
    <div className="mt-6 grid grid-cols-4 gap-1.5" aria-label="Прогресс заказа">
      {track.map((t, i) => {
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

/** True while the draw is being revealed: once, right after it happened. */
function useReveal(orderId: string, lucky: LuckyDraw | null | undefined): [boolean, () => void] {
  const key = `lucky-revealed:${orderId}`;
  const reduced = useReducedMotion();
  const [, rerender] = useState(0);
  let seen = false;
  try {
    seen = sessionStorage.getItem(key) === "1";
  } catch {
    /* storage unavailable: just animate */
  }
  const fresh = Boolean(lucky?.drawn_at) && Date.now() - new Date(lucky!.drawn_at!).getTime() < 3 * 60_000;
  const markSeen = () => {
    try {
      sessionStorage.setItem(key, "1");
    } catch {
      /* ignore */
    }
    rerender((n) => n + 1);
  };
  return [fresh && !seen && !reduced, markSeen];
}

function LuckyPanel({ order, lucky, revealing, onRevealed }: { order: OrderDetail; lucky: LuckyDraw; revealing: boolean; onRevealed: () => void }) {
  return (
    <div className="relative mt-5 overflow-hidden rounded-[22px] p-4 text-left text-white" style={LUCKY_FRAME}>
      {lucky.roll_bp !== null ? (
        <DrawResult lucky={lucky} animated={revealing} onDone={onRevealed} />
      ) : (
        <div className="flex items-center gap-3">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-white/10 ring-1 ring-inset ring-white/15">
            <Clover className="size-6 text-[#7FE0FF]" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="font-display text-[20px] font-extrabold leading-tight tabular">Шанс {lucky.chance}%</div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[13px] text-[#CFE2FF]">
              на <TelegramStar size={14} /> {formatStars(order.stars_amount)} Stars · розыгрыш сразу после оплаты
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const REVEALING = { label: "Розыгрыш", tone: "info", hint: "Определяем результат…" } as const;

function StatusCard({ order, revealing, onRevealed }: { order: OrderDetail; revealing: boolean; onRevealed: () => void }) {
  // While the draw is being revealed the outcome is not spoiled by the heading.
  const meta = revealing ? REVEALING : STATUS_META[order.status];
  const active = revealing || ["pending_payment", "paid", "processing"].includes(order.status);
  return (
    <Card className="relative overflow-hidden p-6 text-center">
      <div className={cn("pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b opacity-60", TONE_GLOW[meta.tone])} aria-hidden />
      <div className={cn("relative mx-auto flex size-20 items-center justify-center", TONE_TEXT[meta.tone])}>
        {active && <span className="absolute inset-0 rounded-full bg-current opacity-25 animate-[pulse-ring_2s_ease-out_infinite]" />}
        <span className="relative flex size-20 items-center justify-center rounded-full bg-surface ring-1 ring-line shadow-card">
          {revealing ? <Clover className="size-8" /> : <StatusIcon status={order.status} />}
        </span>
      </div>
      <div className="relative mt-4 flex items-center justify-center gap-2">
        <h2 className="font-display text-[22px] font-bold tracking-[-0.03em]">{meta.label}</h2>
        {order.kind === "lucky" && <LuckyBadge />}
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
      {order.lucky ? (
        <LuckyPanel order={order} lucky={order.lucky} revealing={revealing} onRevealed={onRevealed} />
      ) : (
        <>
          <div className="relative mt-5 flex items-center justify-center gap-2.5">
            <TelegramStar size={30} />
            <span className="font-display text-[30px] font-bold tracking-[-0.04em] tabular">{formatStars(order.stars_amount)}</span>
            <span className="text-[14px] font-semibold text-text-3">Stars</span>
          </div>
          <div className="relative mt-1 text-[13.5px] text-text-2">{order.recipient.type === "self" ? "Себе" : `для @${order.recipient.username}`}</div>
        </>
      )}
      {!revealing && <Tracker status={order.status} lucky={order.kind === "lucky"} />}
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
  const [revealing, markRevealed] = useReveal(id, order.data?.lucky);
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
      // A Lucky Buy order gets the device's seed with its first payment.
      const clientSeed = o.lucky && !o.lucky.client_seed ? newClientSeed() : undefined;
      const payment = o.payment?.pay_url ? o.payment : await createPayment.mutateAsync({ orderId: o.id, provider: o.payment_provider, clientSeed });
      if (payment.pay_url_kind === "internal") navigate(`/pay/demo/${payment.id}`);
      else if (payment.pay_url) openPayment(payment.pay_url, payment.pay_url_kind, () => order.refetch());
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
      <PageHeader title={`Заказ #${o.number}`} subtitle={formatDate(o.created_at, boot.timezone)} right={revealing ? undefined : <StatusBadge status={o.status} />} />
      <Page className="space-y-4">
        {params.get("paying") && o.status === "pending_payment" && (
          <div className="rounded-[20px] bg-accent/10 p-4 text-[13.5px] leading-relaxed text-text-2 ring-1 ring-inset ring-accent/25">
            Завершите оплату на странице провайдера и вернитесь сюда — статус обновится автоматически.
          </div>
        )}
        <StatusCard order={o} revealing={revealing} onRevealed={markRevealed} />

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
        {revealing ? null : o.kind === "lucky" && (o.status === "completed" || o.status === "lost") && boot.lucky.available ? (
          <Button size="lg" variant="lucky" block onClick={() => navigate("/lucky")} icon={<Clover className="size-5" />}>
            Испытать удачу ещё раз
          </Button>
        ) : (
          (o.status === "completed" || o.status === "lost") && (
            <Button size="lg" variant="secondary" block onClick={() => navigate("/catalog")} icon={<Sparkles className="size-5" />}>
              Купить ещё
            </Button>
          )
        )}
        {(o.status === "failed" || o.status === "refund_pending") && (
          <Button size="lg" variant="secondary" block onClick={() => navigate(`/support?order=${o.id}`)} icon={<LifeBuoy className="size-5" />}>
            Написать в поддержку
          </Button>
        )}

        <Card className="px-5 py-2">
          <div className="divide-y divide-line">
            {o.lucky ? (
              <>
                <SummaryRow
                  label="Приз"
                  value={
                    <span className="inline-flex items-center gap-1.5">
                      <TelegramStar size={16} /> {formatStars(o.stars_amount)} Stars{c === "XTR" ? "" : ` · ${formatMoney(o.lucky.prize_value, c)}`}
                    </span>
                  }
                />
                <SummaryRow label="Шанс выигрыша" value={`${o.lucky.chance}%`} />
                <SummaryRow label="Цена попытки" value={formatMoney(o.amounts.subtotal, c)} />
              </>
            ) : (
              <>
                <SummaryRow label="Цена за звезду" value={formatRate(o.amounts.unit_price, c)} />
                <SummaryRow label="Стоимость" value={formatMoney(o.amounts.subtotal, c)} />
              </>
            )}
            {Number(o.amounts.discount) > 0 && <SummaryRow label="Скидка" value={`−${formatMoney(o.amounts.discount, c)}`} tone="success" />}
            {Number(o.amounts.bonus_spent) > 0 && <SummaryRow label="Бонусы" value={`−${formatMoney(o.amounts.bonus_spent, c)}`} tone="success" />}
            <SummaryRow label="Комиссия" value={Number(o.amounts.fee) > 0 ? formatMoney(o.amounts.fee, c) : "Без комиссии"} />
            <SummaryRow label="Способ оплаты" value={<span className="text-[13.5px]">{o.payment_method}</span>} />
            <SummaryRow label="Итого" value={formatMoney(o.amounts.total, c)} strong />
          </div>
        </Card>

        {o.lucky && <FairnessCard lucky={o.lucky} />}

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
