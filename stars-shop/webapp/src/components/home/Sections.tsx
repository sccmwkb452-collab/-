import type { OrderSummary } from "@starshop/shared";
import { formatMoney, formatShortDate, formatStars, LogoMark, TelegramStar } from "@starshop/shared";
import { ArrowUpRight, ChevronRight, Gem, Info, Megaphone, ReceiptText, RefreshCw, TriangleAlert } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { canAuthenticate, errorMessage } from "../../lib/api";
import { useOrders } from "../../lib/queries";
import { openExternal } from "../../lib/telegram";
import { useBoot } from "../BootContext";
import { LuckyBadge, StatusBadge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card, SectionHeader } from "../ui/Card";
import { Skeleton } from "../ui/Skeleton";
import { cn } from "../ui/cn";

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

export function OrderRow({ order }: { order: OrderSummary }) {
  const navigate = useNavigate();
  const boot = useBoot();
  return (
    <button onClick={() => navigate(`/orders/${order.id}`)} className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition hover:bg-surface-2/60">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-surface-2 ring-1 ring-line">
        {order.premium_months ? <Gem className="size-5 text-accent" /> : <TelegramStar size={24} />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2 text-[14.5px] font-semibold tabular">
          <span className="truncate">{order.premium_months ? `Premium · ${order.premium_months} мес.` : `${formatStars(order.stars_amount)} Stars`}</span>
          {order.kind === "lucky" && <LuckyBadge />}
          {order.kind === "withdrawal" && <span className="rounded-md bg-success/14 px-1.5 text-[10px] font-bold uppercase text-success ring-1 ring-inset ring-success/30">Вывод</span>}
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

export function RecentOrders() {
  const navigate = useNavigate();
  const recent = useOrders("all", 3, canAuthenticate);
  return (
    <section aria-label="Последние заказы">
      <SectionHeader
        title="Последние заказы"
        action={
          recent.data?.items.length ? (
            <Link to="/orders" className="text-[13.5px] font-semibold text-accent">
              Все
            </Link>
          ) : undefined
        }
      />
      {!canAuthenticate ? (
        <Card className="p-5 text-[13.5px] leading-relaxed text-text-2">Заказы видны в мини-приложении Telegram.</Card>
      ) : recent.isPending ? (
        <Card className="divide-y divide-line overflow-hidden" aria-busy="true">
          {[0, 1].map((i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-3.5">
              <Skeleton className="size-11 rounded-2xl" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-24" />
              </div>
            </div>
          ))}
        </Card>
      ) : recent.isError ? (
        <Card className="flex items-center gap-3 p-4">
          <TriangleAlert className="size-5 shrink-0 text-danger" />
          <span className="flex-1 text-[13.5px] text-text-2">{errorMessage(recent.error)}</span>
          <Button size="sm" variant="secondary" icon={<RefreshCw className="size-4" />} onClick={() => recent.refetch()}>
            Повторить
          </Button>
        </Card>
      ) : recent.data.items.length === 0 ? (
        <Card className="flex items-center gap-4 p-5">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-surface-2 ring-1 ring-line">
            <ReceiptText className="size-5 text-text-3" />
          </span>
          <span className="flex-1 text-[13.5px] leading-relaxed text-text-2">Заказов пока нет. Выберите пакет или своё количество звёзд выше.</span>
        </Card>
      ) : (
        <Card className="divide-y divide-line overflow-hidden">
          {recent.data.items.map((o) => (
            <OrderRow key={o.id} order={o} />
          ))}
          <button onClick={() => navigate("/orders")} className="flex w-full items-center justify-center gap-1 py-3 text-[13.5px] font-semibold text-accent">
            Все заказы <ChevronRight className="size-4" />
          </button>
        </Card>
      )}
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
          Условия покупки
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
