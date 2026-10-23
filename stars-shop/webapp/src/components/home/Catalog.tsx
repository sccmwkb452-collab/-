import type { Product } from "@starshop/shared";
import { formatMoney, formatRate, formatStars, TelegramStar } from "@starshop/shared";
import { motion } from "motion/react";
import { Flame, SlidersHorizontal } from "lucide-react";
import { useNavigate } from "react-router";
import { haptic } from "../../lib/telegram";
import { useBoot } from "../BootContext";
import { StarArt } from "../art/StarArt";
import { SectionHeader } from "../ui/Card";
import { Skeleton } from "../ui/Skeleton";
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

function CustomCard({ product, currency }: { product: Product; currency: string }) {
  const navigate = useNavigate();
  const boot = useBoot();
  const min = Math.max(product.min_stars ?? 1, boot.delivery.min_stars);
  const max = Math.min(product.max_stars ?? boot.delivery.max_stars, boot.delivery.max_stars);
  return (
    <motion.button
      variants={item}
      whileTap={{ scale: 0.985 }}
      onClick={() => navigate(`/checkout/${product.id}`)}
      className="group relative col-span-2 flex items-center gap-4 overflow-hidden rounded-[26px] bg-surface p-4 text-left ring-1 ring-inset ring-line shadow-card transition hover:ring-line-strong sm:col-span-3 lg:col-span-4"
    >
      <div className="pointer-events-none absolute -right-10 -top-10 size-40 rounded-full bg-accent-2/20 blur-3xl" aria-hidden />
      <div className="relative flex size-16 shrink-0 items-center justify-center rounded-[20px] bg-surface-2 ring-1 ring-line">
        <TelegramStar size={34} />
        <SlidersHorizontal className="absolute -bottom-1 -right-1 size-6 rounded-lg bg-accent p-1 text-white" aria-hidden />
      </div>
      <div className="relative min-w-0 flex-1">
        <div className="font-display text-[16px] font-semibold tracking-[-0.02em]">{product.title || "Своё количество"}</div>
        <div className="mt-1 text-[13px] text-text-2">
          от {formatStars(min)} до {formatStars(max)} Stars · {formatRate(product.price_per_star, currency)} за звезду
        </div>
      </div>
      <span className="relative inline-flex h-9 shrink-0 items-center rounded-xl bg-surface-2 px-3.5 text-[13px] font-bold ring-1 ring-inset ring-line transition group-hover:bg-accent group-hover:text-white">Выбрать</span>
    </motion.button>
  );
}

export function Catalog({ products, loading }: { products: Product[]; loading?: boolean }) {
  const boot = useBoot();
  const packages = products.filter((p) => p.kind === "package");
  const custom = products.filter((p) => p.kind === "custom");
  return (
    <section id="catalog" className="scroll-mt-20">
      <SectionHeader title={boot.content.catalog_title} subtitle={boot.content.catalog_subtitle} />
      {loading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-[214px] rounded-[26px]" />
          ))}
        </div>
      ) : products.length === 0 ? (
        <div className="rounded-[26px] bg-surface p-8 text-center text-[14px] text-text-2 ring-1 ring-line">Пакеты скоро появятся. Загляните чуть позже ✨</div>
      ) : (
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
          {custom.map((p) => (
            <CustomCard key={p.id} product={p} currency={boot.currency} />
          ))}
        </motion.div>
      )}
    </section>
  );
}
