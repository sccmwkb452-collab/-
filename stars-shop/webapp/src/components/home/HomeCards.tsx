import { formatMoney, formatStars, TelegramStar } from "@starshop/shared";
import { ChevronRight, Copy, RefreshCw, Share2, Sparkles, UsersRound } from "lucide-react";
import { useNavigate } from "react-router";
import luckyArt from "../../assets/lucky/art.webp?no-inline";
import { canAuthenticate, errorMessage } from "../../lib/api";
import { useMe, useReferrals } from "../../lib/queries";
import { copyText, shareLink, tg } from "../../lib/telegram";
import { useBoot } from "../BootContext";
import { LUCKY_FRAME } from "../lucky/LuckyParts";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Skeleton } from "../ui/Skeleton";
import { useToast } from "../ui/Toast";

export function Greeting() {
  const boot = useBoot();
  const me = useMe();
  const name = me.data?.user.first_name || tg?.initDataUnsafe.user?.first_name;
  return (
    <section className="px-1">
      <h1 className="font-display text-[24px] font-semibold leading-tight tracking-[-0.03em]">{name ? `Привет, ${name}!` : "Привет!"}</h1>
      <p className="mt-1.5 text-[14px] leading-relaxed text-text-2">{boot.content.hero.subtitle || "Telegram Stars — себе или в подарок другу."}</p>
    </section>
  );
}

/** The big Lucky Buy card: the cheapest attempt comes from the server settings. */
export function LuckyCard() {
  const boot = useBoot();
  const navigate = useNavigate();
  if (!boot.lucky.available) return null;
  return (
    <section aria-label="Lucky Buy" className="relative overflow-hidden rounded-[28px] text-white" style={LUCKY_FRAME}>
      <img
        src={luckyArt}
        alt=""
        aria-hidden
        className="pointer-events-none absolute right-0 top-0 h-full w-[62%] object-cover object-left opacity-90 [mask-image:linear-gradient(90deg,transparent_0%,#000_45%)]"
      />
      <div className="relative p-5">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white/12 px-2.5 py-1 font-display text-[11.5px] font-bold uppercase tracking-[0.08em] ring-1 ring-inset ring-white/20">
          🍀 Lucky Buy
        </span>
        <h2 className="mt-3 max-w-[64%] font-display text-[21px] font-bold leading-[1.15] tracking-[-0.02em]">Испытай удачу за Stars</h2>
        <p className="mt-1.5 max-w-[58%] text-[13.5px] leading-snug text-[#CFE2FF]">Попробуй получить приз</p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button variant="lucky" icon={<Sparkles className="size-[18px]" />} onClick={() => navigate("/lucky")}>
            Испытать удачу
          </Button>
          <span className="inline-flex items-center gap-1 rounded-full bg-[#00CFFF]/16 px-3 py-1.5 text-[13.5px] font-bold tabular ring-1 ring-inset ring-[#7FD3FF]/40">
            От {formatStars(boot.lucky.min_stake)} <TelegramStar size={15} />
          </span>
        </div>
      </div>
    </section>
  );
}

function rewardText(kind: "percent" | "fixed", value: string, currency: string): string {
  return kind === "percent" ? `${value}% от суммы его первого заказа` : formatMoney(value, currency);
}

/** Compact referral card: real numbers from the server, never placeholders. */
export function ReferralCard() {
  const boot = useBoot();
  const navigate = useNavigate();
  const toast = useToast();
  const data = useReferrals(boot.referral.enabled);
  if (!boot.referral.enabled) return null;

  const body = !canAuthenticate ? (
    <p className="mt-2 text-[13.5px] leading-relaxed text-text-2">Ссылка для приглашений доступна в мини-приложении Telegram.</p>
  ) : data.isPending ? (
    <div className="mt-4 grid grid-cols-3 gap-2" aria-busy="true">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-[58px] rounded-2xl" />
      ))}
    </div>
  ) : data.isError ? (
    <div className="mt-3 flex items-center gap-3">
      <span className="flex-1 text-[13px] text-danger">{errorMessage(data.error)}</span>
      <Button size="sm" variant="secondary" icon={<RefreshCw className="size-4" />} onClick={() => data.refetch()}>
        Повторить
      </Button>
    </div>
  ) : (
    <>
      <p className="mt-1.5 text-[13px] leading-relaxed text-text-2">
        Друг получает звёзды, вы — {rewardText(data.data.rules.reward_kind, data.data.rules.reward_value, boot.currency)} бонусами после оплаты его заказа.
      </p>
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        {[
          ["Приглашено", formatStars(data.data.invited)],
          ["Активных", formatStars(data.data.activated)],
          ["Заработано", formatMoney(data.data.earned, boot.currency)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl bg-surface-2/70 px-2 py-2.5 ring-1 ring-inset ring-line">
            <div className="truncate font-display text-[16px] font-bold tracking-[-0.03em] tabular">{value}</div>
            <div className="mt-0.5 text-[11.5px] font-semibold text-text-3">{label}</div>
          </div>
        ))}
      </div>
      {data.data.link && (
        <div className="mt-4 flex gap-2">
          <Button size="sm" icon={<Share2 className="size-4" />} onClick={() => shareLink(data.data.link!, `Telegram Stars в ${boot.brand.name}`)}>
            Пригласить
          </Button>
          <Button
            size="sm"
            variant="secondary"
            icon={<Copy className="size-4" />}
            onClick={async () => {
              const ok = await copyText(data.data.link!);
              toast(ok ? "Ссылка скопирована" : "Не удалось скопировать", ok ? "success" : "error");
            }}
          >
            Копировать
          </Button>
        </div>
      )}
    </>
  );

  return (
    <Card className="relative overflow-hidden p-5">
      <div className="pointer-events-none absolute -right-14 -top-14 size-44 rounded-full bg-info/20 blur-3xl" aria-hidden />
      <button className="relative flex w-full items-center gap-3 text-left" onClick={() => navigate("/referrals")}>
        <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-info/15 ring-1 ring-inset ring-info/30">
          <UsersRound className="size-5 text-info" />
        </span>
        <span className="flex-1 font-display text-[16px] font-semibold tracking-[-0.02em]">Приглашайте друзей</span>
        <ChevronRight className="size-5 text-text-3" />
      </button>
      <div className="relative">{body}</div>
    </Card>
  );
}
