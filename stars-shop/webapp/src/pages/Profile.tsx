import { formatDate, formatMoney, formatStars, TelegramStar } from "@starshop/shared";
import { Copy, Gift, LifeBuoy, Moon, ReceiptText, Share2, Smartphone, Sun } from "lucide-react";
import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router";
import { useBoot } from "../components/BootContext";
import { Avatar, Page, PageHeader } from "../components/Layout";
import { OrderRow } from "../components/home/Sections";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Segmented } from "../components/ui/Segmented";
import { Skeleton } from "../components/ui/Skeleton";
import { EmptyState, ErrorState } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { canAuthenticate, errorMessage } from "../lib/api";
import { useMe } from "../lib/queries";
import { openExternal } from "../lib/telegram";
import { useTheme, type ThemePref } from "../lib/theme";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[20px] bg-surface-2/70 p-4 ring-1 ring-inset ring-line">
      <div className="text-[12px] font-semibold text-text-3">{label}</div>
      <div className="mt-1 font-display text-[19px] font-bold tracking-[-0.03em] tabular">{value}</div>
    </div>
  );
}

export function Profile() {
  const boot = useBoot();
  const me = useMe();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const { pref, setPref } = useTheme();
  const loaded = Boolean(me.data);

  // Promo banners link to /profile#bonuses.
  useEffect(() => {
    if (!loaded || location.hash !== "#bonuses") return;
    const t = setTimeout(() => document.getElementById("bonuses")?.scrollIntoView({ behavior: "smooth", block: "start" }), 250);
    return () => clearTimeout(t);
  }, [loaded, location.hash, location.key]);

  const themePicker = (
    <Card className="p-4">
      <div className="mb-3 px-1 text-[13px] font-semibold text-text-2">Оформление</div>
      <Segmented<ThemePref>
        label="Тема"
        value={pref}
        onChange={setPref}
        options={[
          { id: "dark", label: "Тёмная" },
          { id: "light", label: "Светлая" },
          { id: "telegram", label: "Как в Telegram" },
        ]}
      />
      <div className="mt-2 flex justify-center gap-6 text-text-3" aria-hidden>
        <Moon className="size-4" />
        <Sun className="size-4" />
        <Smartphone className="size-4" />
      </div>
    </Card>
  );

  if (!canAuthenticate)
    return (
      <>
        <PageHeader title="Профиль" />
        <Page className="space-y-4">
          <EmptyState icon={<TelegramStar size={30} />} title="Откройте магазин в Telegram" text="Профиль и история заказов доступны в мини-приложении." />
          {themePicker}
        </Page>
      </>
    );

  if (me.isPending)
    return (
      <>
        <PageHeader title="Профиль" />
        <Page className="space-y-3">
          <Skeleton className="h-[150px] rounded-[28px]" />
          <Skeleton className="h-[160px] rounded-[28px]" />
        </Page>
      </>
    );
  if (me.isError || !me.data)
    return (
      <>
        <PageHeader title="Профиль" />
        <Page>
          <ErrorState text={errorMessage(me.error)} onRetry={() => me.refetch()} />
        </Page>
      </>
    );

  const { user, stats, bonus } = me.data;
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast("Скопировано", "success");
    } catch {
      toast("Не удалось скопировать", "error");
    }
  };

  return (
    <>
      <PageHeader title="Профиль" />
      <Page className="space-y-4">
        <Card className="relative overflow-hidden p-5">
          <div className="pointer-events-none absolute -right-16 -top-16 size-48 rounded-full bg-accent/25 blur-3xl" aria-hidden />
          <div className="relative flex items-center gap-4">
            <Avatar name={user.first_name} photo={user.photo_url} size={60} />
            <div className="min-w-0">
              <h2 className="truncate font-display text-[19px] font-semibold tracking-[-0.025em]">
                {user.first_name} {user.last_name ?? ""}
              </h2>
              <div className="truncate text-[13.5px] text-text-3">{user.username ? `@${user.username}` : "username не задан"}</div>
            </div>
          </div>
          <dl className="relative mt-5 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
            <dt className="text-text-3">Telegram ID</dt>
            <dd className="flex items-center justify-end gap-1.5 font-semibold tabular">
              {user.telegram_id}
              <button onClick={() => copy(String(user.telegram_id))} aria-label="Скопировать Telegram ID" className="text-text-3 hover:text-text">
                <Copy className="size-3.5" />
              </button>
            </dd>
            <dt className="text-text-3">С нами с</dt>
            <dd className="text-right font-semibold">{formatDate(user.first_seen_at, boot.timezone, false)}</dd>
          </dl>
          {user.is_blocked && <p className="relative mt-4 rounded-2xl bg-danger/10 p-3 text-[13px] text-danger">Покупки для аккаунта ограничены. Напишите в поддержку.</p>}
        </Card>

        <div className="grid grid-cols-2 gap-3">
          <Stat label="Заказов" value={formatStars(stats.orders_count)} />
          <Stat label="Сумма покупок" value={formatMoney(stats.total_spent, boot.currency)} />
        </div>

        {stats.last_order && (
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between px-4 pt-4 text-[13px] font-semibold text-text-2">
              Последний заказ
              <button className="text-accent" onClick={() => navigate("/orders")}>
                Все заказы
              </button>
            </div>
            <OrderRow order={stats.last_order} />
          </Card>
        )}

        {bonus.referral_enabled ? (
          <Card id="bonuses" className="relative scroll-mt-20 overflow-hidden p-5">
            <div className="pointer-events-none absolute -bottom-16 -left-10 size-48 rounded-full bg-gold/20 blur-3xl" aria-hidden />
            <div className="relative flex items-center gap-2">
              <Gift className="size-5 text-gold" />
              <h3 className="text-[15px] font-semibold">Бонусы и приглашения</h3>
            </div>
            <div className="relative mt-3 flex items-baseline gap-2">
              <span className="font-display text-[28px] font-bold tracking-[-0.04em] tabular">{formatMoney(bonus.balance, boot.currency)}</span>
              <span className="text-[13px] text-text-3">на балансе</span>
            </div>
            <p className="relative mt-2 text-[13px] leading-relaxed text-text-2">
              Пригласите друга — когда его первый заказ будет оплачен и выполнен, вы получите{" "}
              {bonus.reward_kind === "percent" ? `${bonus.reward_value}% от суммы заказа` : formatMoney(bonus.reward_value, boot.currency)}. Приглашено: {bonus.invited}, начислено: {bonus.rewarded}.
            </p>
            {bonus.referral_link && (
              <div className="relative mt-4 flex gap-2">
                <Button size="sm" variant="secondary" icon={<Copy className="size-4" />} onClick={() => copy(bonus.referral_link!)}>
                  Скопировать ссылку
                </Button>
                <Button
                  size="sm"
                  icon={<Share2 className="size-4" />}
                  onClick={() => openExternal(`https://t.me/share/url?url=${encodeURIComponent(bonus.referral_link!)}&text=${encodeURIComponent(`Telegram Stars в ${boot.brand.name}`)}`)}
                >
                  Поделиться
                </Button>
              </div>
            )}
            {bonus.referral_code && <p className="relative mt-3 text-[12px] text-text-3">Ваш код: <b className="tabular text-text-2">{bonus.referral_code}</b></p>}
          </Card>
        ) : (
          location.hash === "#bonuses" && (
            <Card id="bonuses" className="scroll-mt-20 p-5">
              <div className="flex items-center gap-2">
                <Gift className="size-5 text-gold" />
                <h3 className="text-[15px] font-semibold">Бонусы</h3>
              </div>
              <p className="mt-2 text-[13px] leading-relaxed text-text-2">Бонусная программа сейчас не активна. Мы сообщим, когда она запустится.</p>
            </Card>
          )
        )}

        {themePicker}

        <div className="grid grid-cols-2 gap-3">
          <Button variant="secondary" icon={<ReceiptText className="size-4" />} onClick={() => navigate("/orders")}>
            Заказы
          </Button>
          <Button variant="secondary" icon={<LifeBuoy className="size-4" />} onClick={() => navigate("/support")}>
            Поддержка
          </Button>
        </div>
      </Page>
    </>
  );
}
