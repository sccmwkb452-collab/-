import { formatDate, formatMoney, formatStars } from "@starshop/shared";
import { Copy, Gift, Lock, Share2, UsersRound } from "lucide-react";
import { useBoot } from "../components/BootContext";
import { Page, PageHeader } from "../components/Layout";
import { WithdrawalCard } from "../components/referrals/Withdrawal";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Skeleton } from "../components/ui/Skeleton";
import { EmptyState, ErrorState } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { canAuthenticate, errorMessage } from "../lib/api";
import { useReferrals } from "../lib/queries";
import { copyText, openExternal, shareLink } from "../lib/telegram";

const STATUS = {
  pending: { label: "Ждём заказ", tone: "neutral" },
  rewarded: { label: "Бонус начислен", tone: "success" },
  rejected: { label: "Без бонуса", tone: "danger" },
  reversed: { label: "Отменён", tone: "danger" },
} as const;

const KIND: Record<string, string> = {
  referral_reward: "Бонус за друга",
  referral_reversal: "Отмена бонуса (возврат заказа)",
  order_spend: "Оплата заказа бонусами",
  order_return: "Возврат бонусов за заказ",
  withdrawal: "Вывод звёздами",
  withdrawal_return: "Возврат бонусов за вывод",
  admin_adjust: "Корректировка администрацией",
};

export function Referrals() {
  const boot = useBoot();
  const toast = useToast();
  const data = useReferrals(boot.referral.enabled);
  const header = <PageHeader title="Рефералы" subtitle="Приглашайте друзей и получайте бонусы" />;

  if (!boot.referral.enabled)
    return (
      <>
        {header}
        <Page>
          <EmptyState icon={<UsersRound className="size-7 text-accent" />} title="Программа приглашений выключена" text="Загляните позже — мы сообщим, когда она снова заработает." />
        </Page>
      </>
    );
  if (!canAuthenticate)
    return (
      <>
        {header}
        <Page>
          <EmptyState
            icon={<Lock className="size-7 text-accent" />}
            title="Откройте магазин в Telegram"
            text="Ваша ссылка для приглашений доступна в мини-приложении."
            action={boot.bot_username && <Button onClick={() => openExternal(`https://t.me/${boot.bot_username}`)}>Открыть бота</Button>}
          />
        </Page>
      </>
    );
  if (data.isPending)
    return (
      <>
        {header}
        <Page className="space-y-3" aria-busy="true">
          <Skeleton className="h-[190px] rounded-[28px]" />
          <Skeleton className="h-[86px] rounded-[24px]" />
          <Skeleton className="h-[160px] rounded-[24px]" />
        </Page>
      </>
    );
  if (data.isError || !data.data)
    return (
      <>
        {header}
        <Page>
          <ErrorState text={errorMessage(data.error)} onRetry={() => data.refetch()} />
        </Page>
      </>
    );

  const r = data.data;
  const reward = r.rules.reward_kind === "percent" ? `${r.rules.reward_value}% от суммы его первого оплаченного заказа` : formatMoney(r.rules.reward_value, boot.currency);
  const copy = async () => {
    const ok = r.link ? await copyText(r.link) : false;
    toast(ok ? "Ссылка скопирована" : "Не удалось скопировать", ok ? "success" : "error");
  };

  return (
    <>
      {header}
      <Page className="space-y-4">
        <Card className="relative overflow-hidden p-5">
          <div className="pointer-events-none absolute -right-16 -top-16 size-48 rounded-full bg-info/20 blur-3xl" aria-hidden />
          <div className="relative flex items-center gap-2">
            <Gift className="size-5 text-info" />
            <h2 className="text-[15px] font-semibold">Ваша ссылка</h2>
          </div>
          {r.link ? (
            <>
              <button onClick={copy} className="relative mt-3 block w-full truncate rounded-2xl bg-surface-2 px-4 py-3 text-left font-mono text-[13px] text-text-2 ring-1 ring-inset ring-line">
                {r.link}
              </button>
              <div className="relative mt-3 grid grid-cols-2 gap-2">
                <Button icon={<Share2 className="size-4" />} onClick={() => shareLink(r.link!, `Telegram Stars в ${boot.brand.name}`)}>
                  Поделиться
                </Button>
                <Button variant="secondary" icon={<Copy className="size-4" />} onClick={copy}>
                  Копировать
                </Button>
              </div>
            </>
          ) : (
            <p className="relative mt-2 text-[13.5px] text-text-2">Ссылка появится, когда бот будет настроен.</p>
          )}
          <p className="relative mt-4 text-[13px] leading-relaxed text-text-2">
            Вы получите {reward}
            {Number(r.rules.min_order_amount) > 0 && ` (заказ от ${formatMoney(r.rules.min_order_amount, boot.currency)})`}. Бонус начисляется один раз за друга, после реальной оплаты
            и выполнения его заказа. Пригласить самого себя нельзя. Бонусами можно оплатить до {r.rules.max_bonus_spend_percent}% заказа.
          </p>
        </Card>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ["Приглашено", formatStars(r.invited)],
            ["Активных", formatStars(r.activated)],
            ["Заработано", formatMoney(r.earned, boot.currency)],
            ["Баланс", formatMoney(r.balance, boot.currency)],
          ].map(([label, value]) => (
            <Card key={label} className="p-4">
              <div className="text-[12px] font-semibold text-text-3">{label}</div>
              <div className="mt-1 font-display text-[19px] font-bold tracking-[-0.03em] tabular">{value}</div>
            </Card>
          ))}
        </div>

        <WithdrawalCard />

        <section>
          <h3 className="mb-2.5 px-1 text-[13px] font-semibold text-text-2">Приглашённые</h3>
          {r.referrals.length === 0 ? (
            <Card className="p-5 text-[13.5px] text-text-2">Пока никого. Отправьте ссылку другу — он появится здесь после запуска бота.</Card>
          ) : (
            <Card className="divide-y divide-line overflow-hidden">
              {r.referrals.map((f, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] font-semibold">{f.name}</span>
                    <span className="block text-[12px] text-text-3">{formatDate(f.created_at, boot.timezone, false)}</span>
                  </span>
                  {f.reward && <span className="text-[13px] font-semibold text-success tabular">+{formatMoney(f.reward, boot.currency)}</span>}
                  <Badge tone={STATUS[f.status]?.tone ?? "neutral"}>{STATUS[f.status]?.label ?? f.status}</Badge>
                </div>
              ))}
            </Card>
          )}
        </section>

        <section>
          <h3 className="mb-2.5 px-1 text-[13px] font-semibold text-text-2">История бонусов</h3>
          {r.history.length === 0 ? (
            <Card className="p-5 text-[13.5px] text-text-2">Начислений и списаний пока не было.</Card>
          ) : (
            <Card className="divide-y divide-line overflow-hidden">
              {r.history.map((t) => {
                const positive = Number(t.amount) > 0;
                return (
                  <div key={t.id} className="flex items-center gap-3 px-4 py-3">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-semibold">{KIND[t.kind] ?? t.comment ?? t.kind}</span>
                      <span className="block text-[12px] text-text-3">{formatDate(t.created_at, boot.timezone)}</span>
                    </span>
                    <span className={`text-[14px] font-semibold tabular ${positive ? "text-success" : "text-danger"}`}>
                      {positive ? "+" : ""}
                      {formatMoney(t.amount, boot.currency)}
                    </span>
                  </div>
                );
              })}
            </Card>
          )}
        </section>
      </Page>
    </>
  );
}
