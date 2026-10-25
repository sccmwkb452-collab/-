import type { Product } from "@starshop/shared";
import { formatMoney, monthsRu } from "@starshop/shared";
import { Check, Gem } from "lucide-react";
import { useNavigate } from "react-router";
import { haptic } from "../../lib/telegram";
import { useBoot } from "../BootContext";
import { cn } from "../ui/cn";

export const PREMIUM_PERKS = ["Без рекламы", "Удвоенные лимиты", "Премиум-эмодзи и стикеры", "Расшифровка голосовых"];

export function premiumPlans(catalog: Product[]): Product[] {
  return catalog.filter((p) => p.kind === "premium" && p.premium_months).sort((a, b) => (a.premium_months ?? 0) - (b.premium_months ?? 0));
}

function perMonth(p: Product): number {
  return Number(p.price ?? 0) / (p.premium_months || 1);
}

/** The plan with the lowest price per month, if it really is lower than the others. */
function bestValueId(plans: Product[]): number | null {
  if (plans.length < 2) return null;
  const sorted = [...plans].sort((a, b) => perMonth(a) - perMonth(b));
  return perMonth(sorted[0]) < perMonth(sorted[1]) ? sorted[0].id : null;
}

export function PremiumIcon({ size = 44 }: { size?: number }) {
  return (
    <span
      className="flex shrink-0 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,#2F6BFF_0%,#38BDF8_100%)] text-white shadow-[0_10px_26px_-10px_rgba(47,107,255,0.9)]"
      style={{ width: size, height: size }}
      aria-hidden
    >
      <Gem style={{ width: size * 0.5, height: size * 0.5 }} />
    </span>
  );
}

export function PlanPicker({ plans, currentId, onPick }: { plans: Product[]; currentId?: number; onPick: (p: Product) => void }) {
  const boot = useBoot();
  const best = bestValueId(plans);
  return (
    <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Срок подписки">
      {plans.map((p) => {
        const active = p.id === currentId;
        return (
          <button
            key={p.id}
            role="radio"
            aria-checked={active}
            onClick={() => {
              haptic.select();
              onPick(p);
            }}
            className={cn(
              "relative flex flex-col items-start rounded-2xl px-3 pb-3 pt-3.5 text-left ring-1 ring-inset transition",
              active ? "bg-accent/14 ring-accent" : "bg-surface/80 ring-line hover:ring-line-strong",
            )}
          >
            {best === p.id && (
              <span className="absolute -top-2 right-2 rounded-full bg-success px-2 py-0.5 text-[10px] font-bold text-white">Выгоднее</span>
            )}
            <span className="font-display text-[15px] font-bold tracking-[-0.02em]">{p.premium_months} мес.</span>
            <span className="mt-1 text-[14px] font-semibold tabular">{formatMoney(p.price, boot.currency)}</span>
            <span className="text-[11px] text-text-3 tabular">{formatMoney(perMonth(p).toFixed(2), boot.currency)}/мес</span>
          </button>
        );
      })}
    </div>
  );
}

/** Home: Telegram Premium for 3, 6 or 12 months, for yourself or as a gift. */
export function PremiumCard() {
  const boot = useBoot();
  const navigate = useNavigate();
  const plans = premiumPlans(boot.catalog);
  if (!plans.length) return null;
  return (
    <section aria-label="Telegram Premium" className="relative overflow-hidden rounded-[28px] bg-surface p-5 ring-1 ring-inset ring-line shadow-card">
      <div className="pointer-events-none absolute -left-10 -top-14 size-44 rounded-full bg-info/20 blur-3xl" aria-hidden />
      <div className="relative flex items-start gap-3">
        <PremiumIcon />
        <div className="min-w-0">
          <h2 className="font-display text-[19px] font-semibold leading-tight tracking-[-0.025em]">Telegram Premium</h2>
          <p className="mt-1 text-[13px] leading-relaxed text-text-2">Себе или в подарок по @username</p>
        </div>
      </div>
      <ul className="relative mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5">
        {PREMIUM_PERKS.map((perk) => (
          <li key={perk} className="flex items-center gap-1.5 text-[12.5px] text-text-2">
            <Check className="size-3.5 shrink-0 text-success" /> {perk}
          </li>
        ))}
      </ul>
      <div className="relative mt-4">
        <PlanPicker plans={plans} onPick={(p) => navigate(`/checkout/${p.id}`)} />
      </div>
    </section>
  );
}

export function PremiumHero({ product, plans, onPick }: { product: Product; plans: Product[]; onPick: (p: Product) => void }) {
  const boot = useBoot();
  return (
    <div className="rounded-[28px] bg-surface p-5 ring-1 ring-inset ring-line shadow-card">
      <div className="flex items-center gap-3">
        <PremiumIcon size={52} />
        <div className="min-w-0">
          <div className="font-display text-[20px] font-bold tracking-[-0.03em]">Telegram Premium</div>
          <div className="text-[13px] text-text-3">на {monthsRu(product.premium_months ?? 0)}</div>
        </div>
        <div className="ml-auto text-right">
          <div className="text-[12px] text-text-3">Стоимость</div>
          <div className="text-[22px] font-bold tracking-[-0.02em] tabular">{formatMoney(product.price, boot.currency)}</div>
        </div>
      </div>
      <ul className="mt-4 grid grid-cols-2 gap-x-3 gap-y-1.5">
        {PREMIUM_PERKS.map((perk) => (
          <li key={perk} className="flex items-center gap-1.5 text-[12.5px] text-text-2">
            <Check className="size-3.5 shrink-0 text-success" /> {perk}
          </li>
        ))}
      </ul>
      {plans.length > 1 && (
        <div className="mt-5">
          <div className="mb-2.5 px-1 text-[13px] font-semibold text-text-2">Срок подписки</div>
          <PlanPicker plans={plans} currentId={product.id} onPick={onPick} />
        </div>
      )}
    </div>
  );
}
