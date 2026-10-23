import type { Product, Quote } from "@starshop/shared";
import { formatMoney, formatRate, formatStars, TelegramStar } from "@starshop/shared";
import { Check, Minus, Plus } from "lucide-react";
import type { ReactNode } from "react";
import { haptic } from "../../lib/telegram";
import { StarArt } from "../art/StarArt";
import { Skeleton } from "../ui/Skeleton";
import { cn } from "../ui/cn";

export const STEPS = ["Пакет", "Получатель", "Подтверждение"] as const;

export function StepIndicator({ step }: { step: number }) {
  return (
    <ol className="mb-5 flex items-center gap-2 px-1" aria-label="Шаги оформления">
      {STEPS.map((label, i) => {
        const done = i < step;
        const active = i === step;
        return (
          <li key={label} className="flex flex-1 items-center gap-2" aria-current={active ? "step" : undefined}>
            <span
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-full text-[12px] font-bold transition-colors duration-300",
                done && "bg-success text-white",
                active && "bg-accent-gradient text-white shadow-glow",
                !done && !active && "bg-surface-2 text-text-3 ring-1 ring-inset ring-line",
              )}
            >
              {done ? <Check className="size-3.5" /> : i + 1}
            </span>
            <span className={cn("truncate text-[12.5px] font-semibold", active ? "text-text" : "text-text-3")}>{label}</span>
            {i < STEPS.length - 1 && <span className={cn("h-px flex-1 rounded-full", done ? "bg-success/60" : "bg-line-strong")} />}
          </li>
        );
      })}
    </ol>
  );
}

export function PackageHero({ stars, price, perStar, currency, estimate }: { stars: number; price: string | null; perStar: string | null; currency: string; estimate?: boolean }) {
  return (
    <div className="rounded-[28px] bg-surface p-2 ring-1 ring-inset ring-line shadow-card">
      <StarArt stars={stars} className="h-[132px]" />
      <div className="flex items-end justify-between gap-3 px-3 pb-3 pt-4">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="font-display text-[34px] font-bold leading-none tracking-[-0.045em] tabular">{formatStars(stars)}</span>
            <span className="text-[14px] font-semibold text-text-3">Stars</span>
          </div>
          <div className="mt-1.5 text-[12.5px] text-text-3 tabular">{formatRate(perStar, currency)} за звезду</div>
        </div>
        <div className="text-right">
          <div className="text-[12px] text-text-3">{estimate ? "≈ стоимость" : "Стоимость"}</div>
          <div className="text-[22px] font-bold tracking-[-0.02em] tabular">{formatMoney(price, currency)}</div>
        </div>
      </div>
    </div>
  );
}

export function PackageSwitcher({ products, currentId, currency, onPick }: { products: Product[]; currentId: number; currency: string; onPick: (id: number) => void }) {
  const packages = products.filter((p) => p.kind === "package");
  if (packages.length < 2) return null;
  return (
    <div className="mt-5">
      <div className="mb-2.5 px-1 text-[13px] font-semibold text-text-2">Другие пакеты</div>
      <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
        {packages.map((p) => {
          const active = p.id === currentId;
          return (
            <button
              key={p.id}
              onClick={() => {
                haptic.select();
                onPick(p.id);
              }}
              aria-pressed={active}
              className={cn(
                "flex shrink-0 items-center gap-2 rounded-2xl px-3.5 py-2.5 text-left ring-1 ring-inset transition",
                active ? "bg-accent/15 ring-accent" : "bg-surface ring-line hover:ring-line-strong",
              )}
            >
              <TelegramStar size={18} />
              <span>
                <span className="block text-[14px] font-bold leading-tight tabular">{formatStars(p.stars_amount)}</span>
                <span className="block text-[11.5px] text-text-3 tabular">{formatMoney(p.price, currency)}</span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

const QUICK = [100, 250, 500, 1000, 2500, 5000, 10000];

export function AmountPicker({ value, min, max, onChange }: { value: number; min: number; max: number; onChange: (v: number) => void }) {
  const clamp = (v: number) => Math.min(max, Math.max(min, Math.round(v)));
  const step = value >= 1000 ? 100 : 50;
  const sliderMax = Math.min(max, 20000);
  return (
    <div className="mt-5 rounded-[24px] bg-surface p-4 ring-1 ring-inset ring-line">
      <div className="flex items-center gap-3">
        <button className="flex size-12 items-center justify-center rounded-2xl bg-surface-2 ring-1 ring-line active:scale-95 disabled:opacity-40" onClick={() => onChange(clamp(value - step))} disabled={value <= min} aria-label="Меньше">
          <Minus className="size-5" />
        </button>
        <label className="flex-1">
          <span className="sr-only">Количество звёзд</span>
          <input
            inputMode="numeric"
            value={Number.isFinite(value) ? String(value) : ""}
            onChange={(e) => {
              const digits = e.target.value.replace(/\D/g, "").slice(0, 7);
              onChange(digits ? Number(digits) : 0);
            }}
            onBlur={() => onChange(clamp(value || min))}
            className="h-12 w-full rounded-2xl bg-surface-2 text-center font-display text-[24px] font-bold tracking-[-0.03em] outline-none ring-1 ring-inset ring-line tabular focus:ring-2 focus:ring-accent"
          />
        </label>
        <button className="flex size-12 items-center justify-center rounded-2xl bg-surface-2 ring-1 ring-line active:scale-95 disabled:opacity-40" onClick={() => onChange(clamp(value + step))} disabled={value >= max} aria-label="Больше">
          <Plus className="size-5" />
        </button>
      </div>
      <input
        type="range"
        min={min}
        max={sliderMax}
        step={10}
        value={Math.min(value, sliderMax)}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-4 w-full accent-[var(--c-accent)]"
        aria-label="Количество звёзд"
      />
      <div className="mt-1 flex justify-between text-[11.5px] text-text-3 tabular">
        <span>от {formatStars(min)}</span>
        <span>до {formatStars(max)}</span>
      </div>
      <div className="no-scrollbar mt-3 flex gap-2 overflow-x-auto">
        {QUICK.filter((q) => q >= min && q <= max).map((q) => (
          <button
            key={q}
            onClick={() => {
              haptic.select();
              onChange(q);
            }}
            className={cn("shrink-0 rounded-xl px-3 py-1.5 text-[13px] font-semibold ring-1 ring-inset transition tabular", q === value ? "bg-accent text-white ring-accent" : "bg-surface-2 text-text-2 ring-line")}
          >
            {formatStars(q)}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SummaryRow({ label, value, strong, tone }: { label: ReactNode; value: ReactNode; strong?: boolean; tone?: "success" }) {
  return (
    <div className={cn("flex items-center justify-between gap-4 py-2.5", strong && "pt-3.5")}>
      <span className={cn("text-[14px]", strong ? "font-semibold text-text" : "text-text-2")}>{label}</span>
      <span className={cn("text-right tabular", strong ? "font-display text-[22px] font-bold tracking-[-0.03em]" : "text-[14.5px] font-semibold", tone === "success" && "text-success")}>{value}</span>
    </div>
  );
}

export function QuoteSummary({ quote, loading, recipient, paymentTitle }: { quote?: Quote; loading: boolean; recipient: string; paymentTitle?: string }) {
  if (!quote) return <Skeleton className="h-[230px] rounded-[24px]" />;
  const c = quote.currency;
  return (
    <div className={cn("rounded-[24px] bg-surface px-5 py-2 ring-1 ring-inset ring-line transition-opacity", loading && "opacity-60")}>
      <div className="divide-y divide-line">
        <SummaryRow label="Количество" value={<span className="inline-flex items-center gap-1.5"><TelegramStar size={16} /> {formatStars(quote.stars_amount)} Stars</span>} />
        <SummaryRow label="Получатель" value={recipient} />
        {paymentTitle && <SummaryRow label="Способ оплаты" value={<span className="text-[13.5px]">{paymentTitle}</span>} />}
        <SummaryRow label="Стоимость" value={formatMoney(quote.subtotal, c)} />
        {Number(quote.discount) > 0 && <SummaryRow label="Скидка по промокоду" value={`−${formatMoney(quote.discount, c)}`} tone="success" />}
        {Number(quote.bonus_spent) > 0 && <SummaryRow label="Оплата бонусами" value={`−${formatMoney(quote.bonus_spent, c)}`} tone="success" />}
        <SummaryRow label="Комиссия" value={Number(quote.fee) > 0 ? formatMoney(quote.fee, c) : "Без комиссии"} />
        <SummaryRow label="Итого" value={formatMoney(quote.total, c)} strong />
      </div>
    </div>
  );
}

export function BottomBar({ children }: { children: ReactNode }) {
  return (
    <div className="sticky bottom-0 z-20 -mx-4 mt-6 bg-gradient-to-t from-bg via-bg/95 to-transparent px-4 pb-[calc(1rem+var(--safe-bottom))] pt-6">{children}</div>
  );
}
