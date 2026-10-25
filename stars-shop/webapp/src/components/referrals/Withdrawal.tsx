import type { WithdrawalItem } from "@starshop/shared";
import { formatDate, formatMoney, formatStars, STATUS_META, TelegramStar } from "@starshop/shared";
import { ArrowDownToLine, CircleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { errorMessage } from "../../lib/api";
import { useRequestWithdrawal, useWithdrawals } from "../../lib/queries";
import { useBoot } from "../BootContext";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { Skeleton } from "../ui/Skeleton";
import { useToast } from "../ui/Toast";
import { cn } from "../ui/cn";

const STATUS: Record<WithdrawalItem["status"], { label: string; tone: "neutral" | "info" | "success" | "danger" }> = {
  pending: { label: "На проверке", tone: "neutral" },
  approved: { label: "Одобрен", tone: "info" },
  rejected: { label: "Отклонён", tone: "danger" },
  returned: { label: "Бонусы возвращены", tone: "danger" },
};

function itemStatus(w: WithdrawalItem) {
  if (w.status === "approved" && w.order) {
    const meta = STATUS_META[w.order.status];
    return { label: w.order.status === "completed" ? "Звёзды зачислены" : meta.label, tone: meta.tone };
  }
  return STATUS[w.status];
}

/** Referral bonuses paid out as Stars to the user's own account. */
export function WithdrawalCard() {
  const boot = useBoot();
  const toast = useToast();
  const data = useWithdrawals(boot.referral.enabled);
  const request = useRequestWithdrawal();
  const [raw, setRaw] = useState("");
  const [confirm, setConfirm] = useState(false);
  const available = data.data?.available_stars ?? 0;
  useEffect(() => {
    if (data.data) setRaw(String(data.data.available_stars));
  }, [data.data?.available_stars]); // eslint-disable-line react-hooks/exhaustive-deps

  if (data.isPending) return <Skeleton className="h-[180px] rounded-[24px]" />;
  if (data.isError || !data.data) return null;
  const w = data.data;
  if (!w.enabled) return null;
  const pending = w.items.find((i) => i.status === "pending");
  const stars = Number(raw);
  const valid = Number.isInteger(stars) && stars >= w.min_stars && stars <= available;
  const cost = w.rate ? (stars * Number(w.rate)).toFixed(2) : null;

  return (
    <section>
      <h3 className="mb-2.5 px-1 text-[13px] font-semibold text-text-2">Вывод звёздами</h3>
      <Card className="p-5">
        <div className="flex items-center gap-3">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-success/12 ring-1 ring-inset ring-success/30">
            <ArrowDownToLine className="size-5 text-success" />
          </span>
          <div className="min-w-0">
            <div className="flex items-baseline gap-1.5">
              <span className="font-display text-[22px] font-bold tracking-[-0.03em] tabular">{formatStars(available)}</span>
              <span className="text-[13px] font-semibold text-text-3">Stars доступно</span>
            </div>
            {w.rate && <div className="text-[12px] text-text-3">1 ⭐ = {formatMoney(w.rate, boot.currency)} бонусов</div>}
          </div>
        </div>

        {pending ? (
          <p className="mt-4 rounded-2xl bg-surface-2 p-3 text-[13px] text-text-2">
            Заявка #{pending.id} на {formatStars(pending.stars)} Stars ждёт проверки администратором.
          </p>
        ) : w.needs_username ? (
          <p className="mt-4 flex gap-2 rounded-2xl bg-warning/10 p-3 text-[13px] text-text-2 ring-1 ring-inset ring-warning/25">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-warning" />
            Для зачисления звёзд нужен публичный username в настройках Telegram.
          </p>
        ) : available < w.min_stars ? (
          <p className="mt-4 text-[13px] leading-relaxed text-text-2">Вывести можно от {formatStars(w.min_stars)} Stars. Приглашайте друзей — бонусы копятся.</p>
        ) : (
          <div className="mt-4">
            <div className={cn("flex items-center gap-2 rounded-2xl bg-surface-2 px-4 ring-1 ring-inset", valid ? "ring-line focus-within:ring-accent" : "ring-danger")}>
              <TelegramStar size={18} />
              <input
                aria-label="Сколько звёзд вывести"
                inputMode="numeric"
                value={raw}
                onChange={(e) => setRaw(e.target.value.replace(/\D/g, "").slice(0, 7))}
                className="h-12 min-w-0 flex-1 bg-transparent font-display text-[19px] font-bold outline-none tabular"
              />
              <button className="text-[12.5px] font-semibold text-accent" onClick={() => setRaw(String(available))}>
                Все
              </button>
            </div>
            <p className={cn("mt-1.5 px-1 text-[12px]", valid ? "text-text-3" : "text-danger")}>
              {valid && cost ? `Спишется ${formatMoney(cost, boot.currency)} бонусов` : `От ${formatStars(w.min_stars)} до ${formatStars(available)} Stars`}
            </p>
            <Button variant="primary" block className="mt-3" disabled={!valid} loading={request.isPending} onClick={() => setConfirm(true)}>
              Вывести {valid ? `${formatStars(stars)} ⭐` : ""}
            </Button>
            <p className="mt-2 text-[11.5px] leading-relaxed text-text-3">
              Звёзды придут на ваш аккаунт после проверки заявки. Если отправить не получится, бонусы вернутся. <Link to="/info/terms" className="text-accent">Условия</Link>
            </p>
          </div>
        )}

        {w.items.length > 0 && (
          <ul className="mt-4 divide-y divide-line border-t border-line">
            {w.items.map((i) => {
              const st = itemStatus(i);
              return (
                <li key={i.id} className="flex items-center gap-3 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13.5px] font-semibold tabular">
                      {formatStars(i.stars)} Stars · #{i.id}
                    </span>
                    <span className="block truncate text-[11.5px] text-text-3">
                      {formatDate(i.created_at, boot.timezone)}
                      {i.comment ? ` · ${i.comment}` : ""}
                    </span>
                  </span>
                  <Badge tone={st.tone}>{st.label}</Badge>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
      <ConfirmDialog
        open={confirm}
        title={`Вывести ${formatStars(stars)} Stars?`}
        text={`С бонусного баланса спишется ${cost ? formatMoney(cost, boot.currency) : ""}. Звёзды придут на ваш аккаунт Telegram.`}
        confirmLabel="Вывести"
        onClose={() => setConfirm(false)}
        onConfirm={() => {
          setConfirm(false);
          request.mutate(stars, {
            onSuccess: () => toast("Заявка на вывод создана", "success"),
            onError: (e) => toast(errorMessage(e), "error"),
          });
        }}
      />
    </section>
  );
}
