import type { OrderSummary } from "@starshop/shared";
import { formatMoney, formatShortDate, formatStars, LogoMark, TelegramStar } from "@starshop/shared";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUpRight, ChevronDown, ChevronRight, CircleHelp, Info, MessageCircle, Megaphone, ShieldCheck, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { openExternal } from "../../lib/telegram";
import { useBoot } from "../BootContext";
import { LuckyBadge, StatusBadge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card, SectionHeader } from "../ui/Card";
import { NamedIcon } from "../ui/Icon";
import { cn } from "../ui/cn";

const reveal = { initial: { opacity: 0, y: 16 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: "-40px" }, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] as const } };

export function Announcements() {
  const { content } = useBoot();
  if (!content.announcements.length) return null;
  const tone = { info: "text-accent", success: "text-success", warning: "text-warning" } as const;
  return (
    <div className="space-y-2">
      {content.announcements.map((a) => (
        <div key={a.id} className="flex items-start gap-3 rounded-2xl bg-surface px-4 py-3 text-[13.5px] ring-1 ring-inset ring-line">
          {a.tone === "warning" ? <TriangleAlert className={cn("mt-0.5 size-4 shrink-0", tone[a.tone])} /> : <Megaphone className={cn("mt-0.5 size-4 shrink-0", tone[a.tone])} />}
          <span className="flex-1 text-text-2">{a.text}</span>
          {a.link && (
            <button className="shrink-0 font-semibold text-accent" onClick={() => openExternal(a.link!)}>
              Подробнее
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

export function PromoBanners() {
  const { content } = useBoot();
  if (!content.promo_banners.length) return null;
  return (
    <div className="no-scrollbar -mx-4 flex snap-x gap-3 overflow-x-auto px-4">
      {content.promo_banners.map((b) => (
        <div
          key={b.id}
          className="relative min-w-[82%] snap-start overflow-hidden rounded-[26px] p-5 ring-1 ring-inset ring-line sm:min-w-[48%]"
          style={{ background: `linear-gradient(135deg, color-mix(in oklab, ${b.accent} 30%, var(--c-surface)) 0%, var(--c-surface) 70%)` }}
        >
          <div className="absolute -right-8 -top-8 size-32 rounded-full blur-3xl" style={{ background: b.accent, opacity: 0.35 }} aria-hidden />
          <div className="relative font-display text-[17px] font-semibold tracking-[-0.02em]">{b.title}</div>
          {b.subtitle && <p className="relative mt-1.5 text-[13.5px] leading-relaxed text-text-2">{b.subtitle}</p>}
          {b.cta_label && b.link && (
            <Button size="sm" variant="secondary" className="relative mt-4" iconRight={<ArrowUpRight className="size-4" />} onClick={() => openExternal(b.link!)}>
              {b.cta_label}
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}

export function HowItWorks() {
  const { content } = useBoot();
  return (
    <section>
      <SectionHeader title="Как это работает" subtitle="Три шага — и звёзды у получателя" />
      <div className="grid gap-3 sm:grid-cols-3">
        {content.how_it_works.map((step, i) => (
          <motion.div key={step.title} {...reveal} transition={{ ...reveal.transition, delay: i * 0.06 }}>
            <Card className="relative h-full overflow-hidden p-5">
              <span className="absolute right-4 top-3 font-display text-[44px] font-bold leading-none text-text/[0.05]">{i + 1}</span>
              <div className="flex size-11 items-center justify-center rounded-2xl bg-accent-gradient text-white shadow-glow">
                <NamedIcon name={step.icon} className="size-5" />
              </div>
              <h3 className="mt-4 text-[16px] font-semibold tracking-[-0.01em]">{step.title}</h3>
              <p className="mt-1.5 text-[13.5px] leading-relaxed text-text-2">{step.text}</p>
            </Card>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

export function WhyUs() {
  const { content } = useBoot();
  return (
    <section>
      <SectionHeader title="Почему выбирают нас" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {content.why_us.map((f, i) => (
          <motion.div key={f.title} {...reveal} transition={{ ...reveal.transition, delay: i * 0.05 }}>
            <Card className="h-full p-4">
              <NamedIcon name={f.icon} className="size-6 text-accent-3" />
              <h3 className="mt-3 text-[14.5px] font-semibold leading-snug tracking-[-0.01em]">{f.title}</h3>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-text-2">{f.text}</p>
            </Card>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

export function PaymentsInfo() {
  const boot = useBoot();
  return (
    <section>
      <SectionHeader title="Оплата и возврат" />
      <Card className="divide-y divide-line">
        <div className="p-5">
          <div className="flex flex-wrap gap-2">
            {boot.payment_methods.map((m) => (
              <span key={m.id} className="inline-flex items-center gap-1.5 rounded-xl bg-surface-2 px-3 py-2 text-[13px] font-semibold ring-1 ring-inset ring-line">
                {m.title}
                {Number(m.fee_percent) > 0 && <span className="text-text-3">· {m.fee_percent}%</span>}
              </span>
            ))}
            {boot.payment_methods.length === 0 && <span className="text-[13.5px] text-text-2">Способы оплаты временно недоступны</span>}
          </div>
          <p className="mt-3 flex gap-2 text-[13.5px] leading-relaxed text-text-2">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" />
            {boot.content.legal.payment_info}
          </p>
        </div>
        <div className="p-5">
          <h3 className="text-[14.5px] font-semibold">Возврат средств</h3>
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-text-2">{boot.content.legal.refund_policy}</p>
          <div className="mt-3 flex gap-4 text-[13.5px] font-semibold">
            <Link to="/info/terms" className="inline-flex items-center gap-1 text-accent">
              Условия покупки <ChevronRight className="size-4" />
            </Link>
            <Link to="/info/refund" className="inline-flex items-center gap-1 text-accent">
              Правила возврата <ChevronRight className="size-4" />
            </Link>
          </div>
        </div>
      </Card>
    </section>
  );
}

export function OrderRow({ order }: { order: OrderSummary }) {
  const navigate = useNavigate();
  const boot = useBoot();
  return (
    <button onClick={() => navigate(`/orders/${order.id}`)} className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition hover:bg-surface-2/60">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-surface-2 ring-1 ring-line">
        <TelegramStar size={24} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2 text-[14.5px] font-semibold tabular">
          {formatStars(order.stars_amount)} Stars
          {order.kind === "lucky" && <LuckyBadge />}
          <span className="text-[12px] font-medium text-text-3">#{order.number}</span>
        </span>
        <span className="mt-0.5 block truncate text-[12.5px] text-text-3">
          {order.recipient.masked} · {formatShortDate(order.created_at, boot.timezone)}
        </span>
      </span>
      <span className="flex flex-col items-end gap-1.5">
        <span className="text-[14px] font-semibold tabular">{formatMoney(order.total, order.currency)}</span>
        <StatusBadge status={order.status} />
      </span>
    </button>
  );
}

export function RecentOrders({ orders }: { orders: OrderSummary[] }) {
  if (!orders.length) return null;
  return (
    <section>
      <SectionHeader
        title="Последние заказы"
        action={
          <Link to="/orders" className="text-[13.5px] font-semibold text-accent">
            Все
          </Link>
        }
      />
      <Card className="divide-y divide-line overflow-hidden">
        {orders.map((o) => (
          <OrderRow key={o.id} order={o} />
        ))}
      </Card>
    </section>
  );
}

export function Faq() {
  const { content } = useBoot();
  const [open, setOpen] = useState<number | null>(0);
  return (
    <section>
      <SectionHeader title="Вопросы и ответы" />
      <Card className="divide-y divide-line overflow-hidden">
        {content.faq.map((item, i) => {
          const expanded = open === i;
          return (
            <div key={item.q}>
              <button
                className="flex w-full items-center gap-3 px-5 py-4 text-left"
                aria-expanded={expanded}
                aria-controls={`faq-${i}`}
                onClick={() => setOpen(expanded ? null : i)}
              >
                <CircleHelp className="size-[18px] shrink-0 text-text-3" />
                <span className="flex-1 text-[14.5px] font-semibold leading-snug">{item.q}</span>
                <ChevronDown className={cn("size-5 shrink-0 text-text-3 transition-transform duration-300", expanded && "rotate-180")} />
              </button>
              <AnimatePresence initial={false}>
                {expanded && (
                  <motion.div id={`faq-${i}`} initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }} className="overflow-hidden">
                    <p className="px-5 pb-4 pl-[52px] text-[13.5px] leading-relaxed text-text-2">{item.a}</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </Card>
    </section>
  );
}

export function SupportCard() {
  const { content } = useBoot();
  const navigate = useNavigate();
  const s = content.support;
  return (
    <section>
      <Card className="relative overflow-hidden p-5">
        <div className="pointer-events-none absolute -right-12 -top-12 size-44 rounded-full bg-accent/20 blur-3xl" aria-hidden />
        <div className="relative flex items-start gap-4">
          <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-surface-2 ring-1 ring-line">
            <MessageCircle className="size-6 text-accent" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="font-display text-[16px] font-semibold tracking-[-0.02em]">Нужна помощь?</h3>
            <p className="mt-1 text-[13.5px] leading-relaxed text-text-2">
              {s.hours}. {s.response_time}.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button size="sm" onClick={() => navigate("/support")}>
                Написать в поддержку
              </Button>
              {s.telegram && (
                <Button size="sm" variant="secondary" onClick={() => openExternal(`https://t.me/${s.telegram.replace(/^@/, "")}`)}>
                  @{s.telegram.replace(/^@/, "")}
                </Button>
              )}
            </div>
          </div>
        </div>
      </Card>
    </section>
  );
}

export function Footer() {
  const boot = useBoot();
  return (
    <footer className="mt-4 space-y-4 px-2 pb-4 text-center">
      <div className="flex items-center justify-center gap-2 text-text-3">
        <LogoMark size={22} />
        <span className="font-display text-[13px] font-semibold text-text-2">{boot.brand.name}</span>
      </div>
      <div className="flex justify-center gap-4 text-[12.5px] font-semibold text-text-3">
        <Link to="/info/terms" className="hover:text-text">
          Условия
        </Link>
        <Link to="/info/refund" className="hover:text-text">
          Возврат
        </Link>
        <Link to="/support" className="hover:text-text">
          Поддержка
        </Link>
      </div>
      {boot.mode === "demo" && (
        <p className="mx-auto flex max-w-[360px] items-start justify-center gap-1.5 text-[12px] leading-relaxed text-warning">
          <Info className="mt-0.5 size-3.5 shrink-0" />
          DEMO-режим: оплата и доставка тестовые, реальные Stars не отправляются.
        </p>
      )}
      <p className="mx-auto max-w-[400px] text-[11.5px] leading-relaxed text-text-3">
        Telegram и Telegram Stars — товарные знаки Telegram. {boot.brand.name} — независимый сервис и не аффилирован с Telegram.
      </p>
    </footer>
  );
}
