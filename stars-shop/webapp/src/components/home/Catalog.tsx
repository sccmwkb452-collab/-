import type { Product } from "@starshop/shared";
import { formatMoney, formatRate, formatStars, TelegramStar } from "@starshop/shared";
import { motion } from "motion/react";
import { ArrowRight, Flame, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { errorMessage } from "../../lib/api";
import { useQuote } from "../../lib/queries";
import { haptic } from "../../lib/telegram";
import { useBoot } from "../BootContext";
import { StarArt } from "../art/StarArt";
import { Button } from "../ui/Button";
import { SectionHeader } from "../ui/Card";
import { cn } from "../ui/cn";

const item = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] as const } } };

function PackageCard({ product, currency }: { product: Product; currency: string }) {
  const navigate = useNavigate();
  const stars = product.stars_amount ?? 0;
  const popular = product.is_popular;
  return (
    <motion.button
      variants={item}
      whileTap={{ scale: 0.97 }}
      onClick={() => {
        haptic.tap();
        navigate(`/checkout/${product.id}`);
      }}
      aria-label={`${formatStars(stars)} Stars за ${formatMoney(product.price, currency)}`}
      className={cn(
        "group relative flex flex-col rounded-[26px] p-2 text-left transition-[box-shadow,transform] duration-300 ease-out-soft hover:-translate-y-0.5",
        popular
          ? "bg-[linear-gradient(var(--c-surface),var(--c-surface))_padding-box,linear-gradient(135deg,var(--c-accent),var(--c-accent-2),var(--c-accent-3))_border-box] border border-transparent shadow-glow"
          : "bg-surface ring-1 ring-inset ring-line shadow-card hover:shadow-[0_18px_40px_-20px_color-mix(in_oklab,var(--c-accent)_60%,transparent)] hover:ring-line-strong",
      )}
    >
      {popular && (
        <span className="absolute -top-2.5 left-1/2 z-10 inline-flex -translate-x-1/2 items-center gap-1 whitespace-nowrap rounded-full bg-accent-gradient px-2.5 py-1 text-[11px] font-bold text-white shadow-glow ring-2 ring-bg">
          <Flame className="size-3" aria-hidden />
          {product.badge || "Популярное"}
        </span>
      )}
      {!popular && product.badge && (
        <span className="absolute right-3 top-3 z-10 rounded-full bg-surface/80 px-2.5 py-1 text-[11px] font-bold text-text-2 ring-1 ring-line backdrop-blur">{product.badge}</span>
      )}
      <StarArt stars={stars} />
      <div className="px-2.5 pb-2 pt-3">
        {product.title && <div className="mb-0.5 text-[12px] font-semibold uppercase tracking-[0.06em] text-text-3">{product.title}</div>}
        <div className="flex items-baseline gap-1.5">
          <span className="font-display text-[25px] font-bold leading-none tracking-[-0.04em] tabular">{formatStars(stars)}</span>
          <span className="text-[12.5px] font-semibold text-text-3">Stars</span>
        </div>
        <div className="mt-3 flex items-end justify-between gap-2 max-[374px]:flex-wrap">
          <div>
            <div className="text-[17px] font-bold tracking-[-0.02em] tabular">{formatMoney(product.price, currency)}</div>
            <div className="flex items-center gap-1 whitespace-nowrap text-[11.5px] text-text-3 tabular">
              {formatRate(product.price_per_star, currency)} за <TelegramStar size={11} />
            </div>
          </div>
          <span
            className={cn(
              "inline-flex h-9 shrink-0 items-center rounded-xl px-3 text-[13px] font-bold transition",
              popular ? "bg-accent-gradient text-white" : "bg-surface-2 text-text ring-1 ring-inset ring-line group-hover:bg-accent group-hover:text-white group-hover:ring-transparent",
            )}
          >
            Купить
          </span>
        </div>
      </div>
    </motion.button>
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

const QUICK = [100, 250, 500, 1000];

/** «Купить Telegram Stars»: any amount within the limits set in the admin
 * panel. The price comes from the server (quote); the rate is only a hint
 * until it arrives. */
function BuyStarsCard({ product }: { product: Product | undefined }) {
  const boot = useBoot();
  const navigate = useNavigate();
  const min = product ? Math.max(product.min_stars ?? 1, boot.delivery.min_stars) : boot.delivery.min_stars;
  const max = product ? Math.min(product.max_stars ?? boot.delivery.max_stars, boot.delivery.max_stars) : boot.delivery.max_stars;
  const [raw, setRaw] = useState(() => String(Math.min(max, Math.max(min, 500))));
  const stars = Number(raw);
  const valid = Number.isInteger(stars) && stars >= min && stars <= max;
  const debounced = useDebounced(stars, 400);
  const provider = boot.payment_methods[0]?.id;
  const quote = useQuote(product && valid && debounced === stars ? { product_id: product.id, stars_amount: debounced, payment_provider: provider } : null);
  const price = quote.data && quote.data.stars_amount === stars ? quote.data.subtotal : null;
  const estimate = product?.price_per_star ? Number(product.price_per_star) * stars : null;
  const buy = () => {
    if (!product || !valid) return;
    haptic.tap("medium");
    navigate(`/checkout/${product.id}?stars=${stars}`);
  };

  return (
    <section
      aria-label="Купить Telegram Stars"
      className="relative overflow-hidden rounded-[28px] p-5 ring-1 ring-inset ring-line shadow-card"
      style={{ background: "linear-gradient(150deg, color-mix(in oklab, var(--c-accent) 22%, var(--c-surface)) 0%, var(--c-surface) 62%)" }}
    >
      <div className="pointer-events-none absolute -right-10 -top-12 size-44 rounded-full bg-accent/30 blur-3xl" aria-hidden />
      <div className="relative flex items-start gap-3">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-surface/80 ring-1 ring-inset ring-line">
          <TelegramStar size={28} />
        </span>
        <div className="min-w-0">
          <h2 className="font-display text-[19px] font-semibold leading-tight tracking-[-0.025em]">Купить Telegram Stars</h2>
          <p className="mt-1 text-[13px] leading-relaxed text-text-2">Себе или в подарок по @username{boot.delivery.gifts_enabled ? "" : " (подарки временно недоступны)"}</p>
        </div>
      </div>

      {!product ? (
        <p className="relative mt-4 text-[13.5px] text-text-2">Своё количество сейчас недоступно — выберите готовый пакет ниже.</p>
      ) : (
        <div className="relative mt-4">
          <label htmlFor="own-amount" className="mb-2 flex items-center gap-1.5 px-1 text-[13px] font-semibold text-text-2">
            <SlidersHorizontal className="size-4 text-accent" /> Своё количество
          </label>
          <div className={cn("flex items-center gap-2 rounded-2xl bg-surface px-4 ring-1 ring-inset transition", valid || !raw ? "ring-line focus-within:ring-accent" : "ring-danger")}>
            <TelegramStar size={20} />
            <input
              id="own-amount"
              inputMode="numeric"
              pattern="[0-9]*"
              value={raw}
              onChange={(e) => setRaw(e.target.value.replace(/\D/g, "").slice(0, 7))}
              onKeyDown={(e) => e.key === "Enter" && buy()}
              className="h-13 min-w-0 flex-1 bg-transparent font-display text-[22px] font-bold tracking-[-0.03em] outline-none tabular"
              aria-describedby="own-amount-hint"
            />
            <span className="text-right text-[13px] text-text-3 tabular">
              {price ? (
                <b className="text-[16px] text-text">{formatMoney(price, boot.currency)}</b>
              ) : valid && estimate !== null ? (
                <span className={cn(quote.isFetching && "animate-pulse")}>≈ {formatMoney(estimate.toFixed(2), boot.currency)}</span>
              ) : null}
            </span>
          </div>
          <p id="own-amount-hint" className={cn("mt-1.5 px-1 text-[12px]", valid || !raw ? "text-text-3" : "text-danger")}>
            {quote.isError && valid ? errorMessage(quote.error) : `От ${formatStars(min)} до ${formatStars(max)} звёзд · ${formatRate(product.price_per_star, boot.currency)} за звезду`}
          </p>
          <div className="mt-3 flex gap-2">
            {QUICK.filter((q) => q >= min && q <= max).map((q) => (
              <button
                key={q}
                onClick={() => {
                  haptic.select();
                  setRaw(String(q));
                }}
                className={cn(
                  "flex-1 rounded-xl py-2 text-[13px] font-semibold ring-1 ring-inset transition tabular",
                  stars === q ? "bg-accent/15 text-text ring-accent" : "bg-surface/70 text-text-2 ring-line hover:ring-line-strong",
                )}
              >
                {formatStars(q)}
              </button>
            ))}
          </div>
          <Button block size="lg" className="mt-4" disabled={!valid} onClick={buy} iconRight={<ArrowRight className="size-5" />}>
            {valid ? `Купить ${formatStars(stars)} ⭐` : "Купить"}
          </Button>
        </div>
      )}
    </section>
  );
}

export function Catalog({ products }: { products: Product[] }) {
  const boot = useBoot();
  const packages = products.filter((p) => p.kind === "package");
  const custom = products.find((p) => p.kind === "custom");
  if (products.length === 0) {
    return (
      <section id="catalog" className="scroll-mt-20">
        <div className="rounded-[26px] bg-surface p-8 text-center ring-1 ring-line">
          <div className="font-display text-[16px] font-semibold">Продажи временно приостановлены</div>
          <p className="mt-1.5 text-[13.5px] text-text-2">Загляните чуть позже — мы скоро вернёмся ✨</p>
        </div>
      </section>
    );
  }
  return (
    <>
      <div id="catalog" className="scroll-mt-20">
        <BuyStarsCard product={custom} />
      </div>
      {packages.length > 0 && (
        <section aria-label="Готовые пакеты">
          <SectionHeader title={boot.content.catalog_title || "Готовые пакеты"} subtitle={boot.content.catalog_subtitle} />
          <motion.div
            className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-40px" }}
            variants={{ show: { transition: { staggerChildren: 0.05 } } }}
          >
            {packages.map((p) => (
              <PackageCard key={p.id} product={p} currency={boot.currency} />
            ))}
          </motion.div>
        </section>
      )}
    </>
  );
}
