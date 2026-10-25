import type { OrderSummary, PaymentInfo } from "@starshop/shared";
import { formatMoney, formatStars, TelegramStar } from "@starshop/shared";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FlaskConical, ShieldAlert } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { Page, PageHeader } from "../components/Layout";
import { DemoBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Skeleton } from "../components/ui/Skeleton";
import { ErrorState } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { api, errorMessage } from "../lib/api";
import { useInvalidateOrders } from "../lib/queries";

/** DEMO checkout: no money moves. The backend turns the button press into
 * an HMAC-signed provider event processed by the regular webhook pipeline. */
export function DemoPay() {
  const { paymentId = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrders();
  const info = useQuery({
    queryKey: ["demo-payment", paymentId],
    queryFn: () => api<{ payment: PaymentInfo; order: OrderSummary }>(`/demo/payments/${paymentId}`),
  });
  const complete = useMutation({
    mutationFn: (outcome: "success" | "fail") => api<{ result: string; order_id: string }>(`/demo/payments/${paymentId}/complete`, { method: "POST", body: { outcome } }),
    onSuccess: (r, outcome) => {
      invalidate();
      toast(outcome === "success" ? "DEMO-оплата подтверждена" : "DEMO: оплата отклонена", outcome === "success" ? "success" : "error");
      navigate(`/orders/${r.order_id}`, { replace: true });
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <>
      <PageHeader title="Оплата" right={<DemoBadge />} />
      <Page className="space-y-4">
        {info.isPending ? (
          <Skeleton className="h-[320px] rounded-[28px]" />
        ) : info.isError || !info.data ? (
          <ErrorState text={errorMessage(info.error)} onRetry={() => info.refetch()} />
        ) : (
          <>
            <Card className="relative overflow-hidden p-6 text-center">
              <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-[repeating-linear-gradient(135deg,color-mix(in_oklab,var(--c-warning)_14%,transparent)_0_12px,transparent_12px_24px)]" aria-hidden />
              <div className="relative mx-auto flex size-16 items-center justify-center rounded-[22px] bg-warning/15 ring-1 ring-warning/30">
                <FlaskConical className="size-8 text-warning" />
              </div>
              <h2 className="relative mt-4 font-display text-[20px] font-bold tracking-[-0.03em]">Тестовая оплата</h2>
              <p className="relative mx-auto mt-2 max-w-[320px] text-[13.5px] leading-relaxed text-text-2">
                Это DEMO-режим: деньги не списываются, реальные Stars и Premium не отправляются. Нажмите кнопку, чтобы сымитировать ответ платёжного провайдера.
              </p>
              <div className="relative mt-5 flex items-center justify-center gap-2">
                {info.data.order.premium_months ? (
                  <span className="font-display text-[18px] font-bold">{info.data.order.item}</span>
                ) : (
                  <>
                    <TelegramStar size={26} />
                    <span className="font-display text-[24px] font-bold tabular">{formatStars(info.data.order.stars_amount)}</span>
                  </>
                )}
                <span className="text-text-3">·</span>
                <span className="text-[20px] font-bold tabular">{formatMoney(info.data.payment.amount, info.data.payment.currency)}</span>
              </div>
              <p className="relative mt-1 text-[12.5px] text-text-3">Заказ #{info.data.order.number}</p>
            </Card>
            <Button size="lg" block variant="gold" loading={complete.isPending && complete.variables === "success"} disabled={complete.isPending || info.data.payment.status !== "pending"} onClick={() => complete.mutate("success")}>
              Оплатить (DEMO)
            </Button>
            <Button size="md" block variant="danger" loading={complete.isPending && complete.variables === "fail"} disabled={complete.isPending || info.data.payment.status !== "pending"} onClick={() => complete.mutate("fail")}>
              Сымитировать отказ банка
            </Button>
            <p className="flex items-start justify-center gap-1.5 px-4 text-center text-[12px] leading-relaxed text-text-3">
              <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
              В режиме PRODUCTION эта страница недоступна: заказ оплачивается только через подключённого провайдера.
            </p>
          </>
        )}
      </Page>
    </>
  );
}
