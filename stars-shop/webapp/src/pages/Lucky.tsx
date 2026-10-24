import type { OrderDetail, PaymentInfo } from "@starshop/shared";
import { formatMoney, formatStars, newClientSeed, TelegramStar } from "@starshop/shared";
import { useMutation } from "@tanstack/react-query";
import { CircleAlert, Clover, Lock, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import mascot from "../assets/lucky/mascot.webp?no-inline";
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

/** The same rounding as the server (services/lucky.stake_for): the share of
 * the prize plus the fee, rounded up to whole Stars. Only a hint for the
 * slider: the price itself always comes from the server quote. */
function stakeFor(prize: number, chance: number, feePercent: string): number {
  const fee100 = Math.round(Number(feePercent) * 100);
  const num = prize * chance * (10_000 + fee100);
  return Math.floor((num + 999_999) / 1_000_000);
}

function lowestChance(prize: number, min: number, max: number, minStake: number, fee: string): number | null {
  for (let c = min; c <= max; c += 1) if (stakeFor(prize, c, fee) >= minStake) return c;
  return null;
}

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

  // Prizes: the packages chosen in the admin panel that can be played for at least the minimum stake.
  const packages = boot.catalog.filter(
    (p) =>
      p.kind === "package" &&
      (cfg.prize_ids.length === 0 || cfg.prize_ids.includes(p.id)) &&
      lowestChance(p.stars_amount ?? 0, cfg.min_chance, cfg.max_chance, cfg.min_stake, cfg.fee_percent) !== null,
  );
  const [productId, setProductId] = useState(() => (packages.find((p) => p.is_popular) ?? packages[0])?.id);
  const product = packages.find((p) => p.id === productId) ?? packages[0];
  const prizeStars = product?.stars_amount ?? 0;
  const minChance = product ? (lowestChance(prizeStars, cfg.min_chance, cfg.max_chance, cfg.min_stake, cfg.fee_percent) ?? cfg.max_chance) : cfg.min_chance;
  const [wanted, setChance] = useState(() => Math.min(cfg.max_chance, Math.max(cfg.min_chance, 25)));
  const chance = Math.min(cfg.max_chance, Math.max(minChance, wanted));
  const debouncedChance = useDebounced(chance, 250);
  const methods = cfg.payment_methods;
  const [provider, setProvider] = useState(methods[0]?.id ?? "");
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
      if (payment.pay_url)
        openPayment(payment.pay_url, payment.pay_url_kind, (status) => {
          invalidateOrders();
          if (status === "failed") toast("Оплата не прошла. Попробуйте ещё раз из заказа", "error");
        });
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

  const header = <PageHeader title="Lucky Buy" subtitle={boot.mode === "demo" ? "DEMO-режим · тестовая оплата" : "Испытай удачу за Stars"} right={boot.mode === "demo" ? <DemoBadge /> : undefined} />;

  if (!cfg.available || !product) {
    return (
      <>
        {header}
        <Page>
          <EmptyState
            icon={<Clover className="size-7 text-accent" />}
            title="Lucky Buy сейчас недоступен"
            text={cfg.available ? "Сейчас нет пакетов, которые можно выиграть. Загляните позже." : "Звёзды можно купить в каталоге по обычной цене."}
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

  const lq = quote.data?.lucky;
  const q = lq ? quote.data : undefined;
  const presets = PRESETS.filter((p) => p >= minChance && p <= cfg.max_chance);
  const canPlay = Boolean(q) && consent && !selfBlocked && Boolean(provider) && !quote.isError && methods.length > 0;

  return (
    <>
      {header}
      <Page className="mx-auto max-w-[620px] space-y-4">
        <section className="relative overflow-hidden rounded-[28px] px-5 pb-5 pt-6 text-white" style={LUCKY_FRAME}>
          <img src={mascot} alt="" aria-hidden className="pointer-events-none absolute -right-4 -top-2 h-[96px] w-auto opacity-90 [mask-image:radial-gradient(ellipse_50%_64%_at_50%_58%,#000_60%,transparent_100%)]" />
          <div className="relative">
            <div className="font-display text-[22px] font-extrabold uppercase tracking-[-0.01em]">Lucky Buy</div>
            <p className="mt-1 max-w-[calc(100%-96px)] text-[13.5px] leading-snug text-[#CFE2FF]">
              Платишь часть звёзд приза — и пробуешь выиграть пакет целиком. Шанс выбираешь сам, попытка от {formatStars(cfg.min_stake)} ⭐.
            </p>
          </div>
          <div className="relative mt-4">
            <ChanceDial chance={chance} stars={product.stars_amount ?? 0} />
          </div>
          <label className="relative mt-4 block">
            <span className="sr-only">Шанс выигрыша, %</span>
            <input
              type="range"
              min={minChance}
              max={cfg.max_chance}
              step={1}
              value={chance}
              onChange={(e) => setChance(Number(e.target.value))}
              className="w-full accent-[#00CFFF]"
            />
          </label>
          <div className="relative mt-1 flex justify-between text-[11.5px] text-[#9FC3FF] tabular">
            <span>{minChance}%</span>
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
                    <span className="block text-[11.5px] text-text-3">Stars</span>
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
                    <TelegramStar size={16} /> {formatStars(q.stars_amount)} Stars
                  </span>
                }
              />
              <SummaryRow label="Шанс выигрыша" value={`${lq.chance}%`} />
              <SummaryRow label={Number(lq.fee_percent) > 0 ? `Цена попытки, включая сбор ${lq.fee_percent}%` : "Цена попытки"} value={formatMoney(q.subtotal, q.currency)} />
              {Number(q.fee) > 0 && <SummaryRow label="Комиссия способа оплаты" value={formatMoney(q.fee, q.currency)} />}
              <SummaryRow label="Итого" value={formatMoney(q.total, q.currency)} strong />
            </div>
          </div>
        ) : quote.isError ? (
          <p className="rounded-[20px] bg-danger/10 p-4 text-[13.5px] text-danger ring-1 ring-inset ring-danger/25">{errorMessage(quote.error)}</p>
        ) : (
          <Skeleton className="h-[230px] rounded-[24px]" />
        )}

        <PaymentMethods methods={methods} value={provider} onChange={setProvider} />

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
            {q ? `Испытать удачу · ${formatMoney(q.total, q.currency)}` : "Испытать удачу"}
          </Button>
          {!consent && q && <p className="mt-2 text-center text-[11.5px] text-text-3">Отметьте согласие с условиями выше</p>}
        </BottomBar>
      </Page>
    </>
  );
}
