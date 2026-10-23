import type { OrderDetail, PaymentInfo } from "@starshop/shared";
import { formatMoney, formatStars, newClientSeed, TelegramStar } from "@starshop/shared";
import { useMutation } from "@tanstack/react-query";
import { CircleAlert, Clover, Lock, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import mascot from "../assets/promo/slide-3-icon.webp?no-inline";
import { useBoot } from "../components/BootContext";
import { Page, PageHeader } from "../components/Layout";
import { BottomBar, PaymentMethods, SummaryRow } from "../components/checkout/parts";
import { ChanceDial, LUCKY_FRAME } from "../components/lucky/LuckyParts";
import { DemoBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Skeleton } from "../components/ui/Skeleton";
import { EmptyState } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { cn } from "../components/ui/cn";
import { ApiError, api, canAuthenticate, errorMessage, newIdempotencyKey } from "../lib/api";
import { useInvalidateOrders, useMe, useQuote } from "../lib/queries";
import { haptic, openExternal, openPayment, requestWriteAccess, setClosingConfirmation } from "../lib/telegram";

const PRESETS = [10, 25, 50, 75];

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Lucky Buy: pick a package and a chance, pay that share of the price, win the whole package. */
export function Lucky() {
  const boot = useBoot();
  const navigate = useNavigate();
  const toast = useToast();
  const me = useMe();
  const invalidateOrders = useInvalidateOrders();
  const cfg = boot.lucky;

  const packages = boot.catalog.filter((p) => p.kind === "package");
  const [productId, setProductId] = useState(() => (packages.find((p) => p.is_popular) ?? packages[0])?.id);
  const product = packages.find((p) => p.id === productId) ?? packages[0];
  const [chance, setChance] = useState(() => Math.min(cfg.max_chance, Math.max(cfg.min_chance, 25)));
  const debouncedChance = useDebounced(chance, 250);
  const [provider, setProvider] = useState(boot.payment_methods[0]?.id ?? "");
  const [consent, setConsent] = useState(false);
  const [clientSeed, setClientSeed] = useState(newClientSeed);

  const quote = useQuote(product && cfg.available ? { product_id: product.id, payment_provider: provider, lucky: { chance: debouncedChance } } : null);
  const myUsername = me.data?.user.username ?? null;
  const selfBlocked = boot.delivery.requires_username && me.data && !myUsername;

  // A fresh idempotency key whenever the attempt changes.
  const orderInput = useMemo(
    () => ({ product_id: product?.id ?? 0, recipient: { type: "self" as const }, payment_provider: provider, lucky: { chance } }),
    [product?.id, provider, chance],
  );
  const inputFingerprint = JSON.stringify(orderInput);
  const idemKey = useMemo(() => newIdempotencyKey(), [inputFingerprint]);
  const orderRef = useRef<OrderDetail | null>(null);

  const play = useMutation({
    mutationFn: async () => {
      await requestWriteAccess(); // for the result message in the chat; optional
      const order = await api<OrderDetail>("/orders", { method: "POST", body: orderInput, headers: { "Idempotency-Key": idemKey } });
      orderRef.current = order;
      // The seed is sent only now, after the server has committed to its own seed (its hash is in `order`).
      const payment = await api<PaymentInfo>(`/orders/${order.id}/payment`, { method: "POST", body: { provider, client_seed: clientSeed } });
      return { order, payment };
    },
    onSuccess: ({ order, payment }) => {
      invalidateOrders();
      if (payment.pay_url_kind === "internal") {
        navigate(`/pay/demo/${payment.id}`, { replace: true });
        return;
      }
      if (payment.pay_url) openPayment(payment.pay_url, payment.pay_url_kind);
      navigate(`/orders/${order.id}?paying=1`, { replace: true });
    },
    onError: (e) => {
      toast(errorMessage(e), "error");
      if (orderRef.current && !(e instanceof ApiError && e.status === 422)) navigate(`/orders/${orderRef.current.id}`, { replace: true });
    },
  });

  useEffect(() => {
    setClosingConfirmation(play.isPending);
    return () => setClosingConfirmation(false);
  }, [play.isPending]);

  const header = <PageHeader title="Lucky Buy" subtitle={boot.mode === "demo" ? "DEMO-режим · тестовая оплата" : "Испытай удачу"} right={boot.mode === "demo" ? <DemoBadge /> : undefined} />;

  if (!cfg.available || !product) {
    return (
      <>
        {header}
        <Page>
          <EmptyState
            icon={<Clover className="size-7 text-accent" />}
            title="Lucky Buy сейчас недоступен"
            text="Звёзды можно купить в каталоге по обычной цене."
            action={<Button onClick={() => navigate("/catalog")}>К каталогу</Button>}
          />
        </Page>
      </>
    );
  }

  if (!canAuthenticate) {
    return (
      <>
        {header}
        <Page>
          <EmptyState
            icon={<Lock className="size-7 text-accent" />}
            title="Откройте магазин в Telegram"
            text="Lucky Buy доступен в мини-приложении Telegram: так мы безопасно узнаём ваш аккаунт без паролей."
            action={boot.bot_username && <Button onClick={() => openExternal(`https://t.me/${boot.bot_username}`)}>Открыть бота</Button>}
          />
        </Page>
      </>
    );
  }

  const c = boot.currency;
  const lq = quote.data?.lucky;
  const q = lq ? quote.data : undefined;
  const presets = PRESETS.filter((p) => p >= cfg.min_chance && p <= cfg.max_chance);
  const canPlay = Boolean(q) && consent && !selfBlocked && Boolean(provider) && !quote.isError && boot.payment_methods.length > 0;

  return (
    <>
      {header}
      <Page className="mx-auto max-w-[620px] space-y-4">
        <section className="relative overflow-hidden rounded-[28px] px-5 pb-5 pt-6 text-white" style={LUCKY_FRAME}>
          <img src={mascot} alt="" aria-hidden className="pointer-events-none absolute -right-4 -top-2 h-[96px] w-auto opacity-90 [mask-image:radial-gradient(ellipse_50%_64%_at_50%_58%,#000_60%,transparent_100%)]" />
          <div className="relative">
            <div className="font-display text-[22px] font-extrabold uppercase tracking-[-0.01em]">Lucky Buy</div>
            <p className="mt-1 max-w-[calc(100%-96px)] text-[13.5px] leading-snug text-[#CFE2FF]">Платишь долю цены — выигрываешь пакет целиком. Шанс выбираешь сам.</p>
          </div>
          <div className="relative mt-4">
            <ChanceDial chance={chance} stars={product.stars_amount ?? 0} />
          </div>
          <label className="relative mt-4 block">
            <span className="sr-only">Шанс выигрыша, %</span>
            <input
              type="range"
              min={cfg.min_chance}
              max={cfg.max_chance}
              step={1}
              value={chance}
              onChange={(e) => setChance(Number(e.target.value))}
              className="w-full accent-[#00CFFF]"
            />
          </label>
          <div className="relative mt-1 flex justify-between text-[11.5px] text-[#9FC3FF] tabular">
            <span>{cfg.min_chance}%</span>
            <span>{cfg.max_chance}%</span>
          </div>
          {presets.length > 0 && (
            <div className="relative mt-3 flex gap-2">
              {presets.map((p) => (
                <button
                  key={p}
                  onClick={() => {
                    haptic.select();
                    setChance(p);
                  }}
                  className={cn(
                    "flex-1 rounded-xl py-2 text-[13.5px] font-semibold ring-1 ring-inset transition tabular",
                    p === chance ? "bg-[#0866FF] text-white ring-[#7FD3FF]/60" : "bg-white/8 text-[#CFE2FF] ring-white/15 hover:bg-white/12",
                  )}
                >
                  {p}%
                </button>
              ))}
            </div>
          )}
        </section>

        <section>
          <div className="mb-2.5 px-1 text-[13px] font-semibold text-text-2">Приз</div>
          <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0">
            {packages.map((p) => {
              const active = p.id === product.id;
              return (
                <button
                  key={p.id}
                  onClick={() => {
                    haptic.select();
                    setProductId(p.id);
                  }}
                  aria-pressed={active}
                  className={cn("flex shrink-0 items-center gap-2 rounded-2xl px-3.5 py-2.5 text-left ring-1 ring-inset transition", active ? "bg-accent/15 ring-accent" : "bg-surface ring-line hover:ring-line-strong")}
                >
                  <TelegramStar size={18} />
                  <span>
                    <span className="block text-[14px] font-bold leading-tight tabular">{formatStars(p.stars_amount)}</span>
                    <span className="block text-[11.5px] text-text-3 tabular">{formatMoney(p.price, c)}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        {q && lq ? (
          <div className={cn("rounded-[24px] bg-surface px-5 py-2 ring-1 ring-inset ring-line transition-opacity", quote.isFetching && "opacity-60")}>
            <div className="divide-y divide-line">
              <SummaryRow
                label="Приз"
                value={
                  <span className="inline-flex items-center gap-1.5">
                    <TelegramStar size={16} /> {formatStars(q.stars_amount)} Stars · {formatMoney(lq.prize_value, c)}
                  </span>
                }
              />
              <SummaryRow label="Шанс выигрыша" value={`${lq.chance}%`} />
              <SummaryRow label={Number(lq.fee_percent) > 0 ? `Цена попытки, включая сбор ${lq.fee_percent}%` : "Цена попытки"} value={formatMoney(q.subtotal, c)} />
              <SummaryRow label="Комиссия" value={Number(q.fee) > 0 ? formatMoney(q.fee, c) : "Без комиссии"} />
              <SummaryRow label="Итого" value={formatMoney(q.total, c)} strong />
            </div>
          </div>
        ) : quote.isError ? (
          <p className="rounded-[20px] bg-danger/10 p-4 text-[13.5px] text-danger ring-1 ring-inset ring-danger/25">{errorMessage(quote.error)}</p>
        ) : (
          <Skeleton className="h-[230px] rounded-[24px]" />
        )}

        <PaymentMethods methods={boot.payment_methods} value={provider} onChange={setProvider} />

        <div className="flex gap-3 rounded-[20px] bg-surface p-4 ring-1 ring-inset ring-line">
          <ShieldCheck className="mt-0.5 size-5 shrink-0 text-[#00CFFF]" />
          <div className="min-w-0 flex-1 text-[12.5px] leading-relaxed text-text-2">
            <span className="block text-[14px] font-semibold text-text">Честный розыгрыш</span>
            Хэш сида сервера появится в заказе до оплаты, сам сид — после розыгрыша. Результат можно проверить.
            <span className="mt-1.5 flex items-center gap-2 text-text-3">
              Ваш сид: <span className="truncate font-mono text-text-2">{clientSeed}</span>
              <button onClick={() => setClientSeed(newClientSeed())} className="shrink-0 text-text-3 hover:text-text" aria-label="Новый сид">
                <RefreshCw className="size-3.5" />
              </button>
            </span>
          </div>
        </div>

        {selfBlocked && (
          <div className="flex gap-3 rounded-[20px] bg-warning/10 p-4 text-[13.5px] leading-relaxed text-text-2 ring-1 ring-inset ring-warning/25">
            <CircleAlert className="mt-0.5 size-5 shrink-0 text-warning" />
            <span>
              Для зачисления выигрыша нужен публичный username. Задайте его в <b>Настройки → Имя пользователя</b> и откройте магазин заново.
            </span>
          </div>
        )}

        <label className="flex cursor-pointer items-start gap-3 rounded-[20px] bg-surface p-4 ring-1 ring-inset ring-line">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 size-5 shrink-0 accent-[var(--c-accent)]" />
          <span className="text-[13px] leading-relaxed text-text-2">
            Мне есть 18 лет. Я понимаю, что это игра на удачу: при проигрыше оплата попытки не возвращается. Приз зачисляется на мой аккаунт{myUsername ? ` @${myUsername}` : ""}.{" "}
            <Link to="/info/terms" className="font-semibold text-accent">
              Условия
            </Link>
          </span>
        </label>

        <BottomBar>
          <Button
            size="lg"
            block
            disabled={!canPlay}
            loading={play.isPending}
            onClick={() => play.mutate()}
            variant="lucky"
            icon={<Sparkles className="size-5" />}
          >
            {q ? `Испытать удачу · ${formatMoney(q.total, c)}` : "Испытать удачу"}
          </Button>
          {!consent && q && <p className="mt-2 text-center text-[11.5px] text-text-3">Отметьте согласие с условиями выше</p>}
        </BottomBar>
      </Page>
    </>
  );
}
