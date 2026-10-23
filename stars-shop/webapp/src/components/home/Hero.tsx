import { TelegramStar } from "@starshop/shared";
import { motion } from "motion/react";
import { ArrowRight, Radar, ReceiptText, WalletCards } from "lucide-react";
import { useBoot } from "../BootContext";
import { HeroVisual } from "../art/HeroVisual";
import { Button } from "../ui/Button";

const BENEFIT_ICONS = [WalletCards, ReceiptText, Radar];

export function Hero({ onBuy }: { onBuy: () => void }) {
  const { content } = useBoot();
  const hero = content.hero;
  // "Твои звёзды. Твои возможности." -> second sentence gets the gradient.
  const [first, ...rest] = hero.title.split(/(?<=\.)\s+/);
  return (
    <section className="relative overflow-hidden rounded-[32px] bg-surface ring-1 ring-inset ring-line shadow-card">
      <div className="pointer-events-none absolute inset-0" aria-hidden>
        <div className="absolute -left-24 -top-24 size-72 rounded-full bg-accent/25 blur-[90px]" />
        <div className="absolute -right-20 top-10 size-64 rounded-full bg-accent-2/25 blur-[90px]" />
        <div className="absolute -bottom-28 left-1/3 size-64 rounded-full bg-accent-3/15 blur-[90px]" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,var(--c-line)_1px,transparent_1px),linear-gradient(to_bottom,var(--c-line)_1px,transparent_1px)] [background-size:32px_32px] [mask-image:radial-gradient(ellipse_at_top,black_20%,transparent_70%)]" />
      </div>
      <div className="relative grid items-center gap-2 p-5 pt-4 sm:grid-cols-[1.1fr_1fr] sm:p-8">
        <div className="order-2 sm:order-1">
          <motion.span
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-1.5 rounded-full bg-surface-2/80 px-3 py-1.5 text-[12.5px] font-semibold text-text-2 ring-1 ring-inset ring-line backdrop-blur"
          >
            <TelegramStar size={15} />
            {hero.eyebrow}
          </motion.span>
          <motion.h1
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="mt-4 font-display text-[31px] font-bold leading-[1.08] tracking-[-0.035em] text-text sm:text-[42px]"
          >
            {first}
            {rest.length > 0 && (
              <>
                <br />
                <span className="text-gradient">{rest.join(" ")}</span>
              </>
            )}
          </motion.h1>
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.12 }} className="mt-3 max-w-[440px] text-[15px] leading-relaxed text-text-2">
            {hero.subtitle}
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }} className="mt-5">
            <Button size="lg" block onClick={onBuy} iconRight={<ArrowRight className="size-5" />} className="overflow-hidden sm:w-auto">
              <span className="pointer-events-none absolute inset-y-0 left-0 w-1/3 animate-[sheen_3.6s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-white/25 to-transparent" aria-hidden />
              {hero.cta_label}
            </Button>
          </motion.div>
          <ul className="mt-5 grid grid-cols-3 gap-2">
            {hero.benefits.slice(0, 3).map((b, i) => {
              const Icon = BENEFIT_ICONS[i % BENEFIT_ICONS.length];
              return (
                <li key={b} className="flex flex-col items-start gap-1.5 rounded-2xl bg-surface-2/70 p-3 ring-1 ring-inset ring-line">
                  <Icon className="size-[18px] text-accent-3" aria-hidden />
                  <span className="text-[12.5px] font-semibold leading-tight text-text">{b}</span>
                </li>
              );
            })}
          </ul>
        </div>
        <div className="order-1 sm:order-2">
          <HeroVisual />
        </div>
      </div>
    </section>
  );
}
