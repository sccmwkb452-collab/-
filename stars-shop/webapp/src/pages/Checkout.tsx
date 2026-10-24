import type { OrderDetail, PaymentInfo, RecipientCheck } from "@starshop/shared";
import { formatMoney } from "@starshop/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, AtSign, BadgeCheck, CircleAlert, CircleHelp, Gift, Lock, Pencil, Search, Sparkles, TicketPercent, User, UserX } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { useBoot } from "../components/BootContext";
import { Avatar, Page, PageHeader } from "../components/Layout";
import { AmountPicker, BottomBar, PackageHero, PackageSwitcher, PaymentMethods, QuoteSummary, StepIndicator } from "../components/checkout/parts";
import { Badge, DemoBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Field } from "../components/ui/Field";
import { Segmented } from "../components/ui/Segmented";
import { Skeleton } from "../components/ui/Skeleton";
import { EmptyState } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { ApiError, api, canAuthenticate, errorMessage, newIdempotencyKey } from "../lib/api";
import { useInvalidateOrders, useMe, useQuote } from "../lib/queries";
import { openExternal, openPayment, requestWriteAccess, setClosingConfirmation } from "../lib/telegram";

const USERNAME_RE = /^[A-Za-z][A-Za-z0-9_]{3,31}$/;

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** The checked recipient, shown as it is: a confirmed account with its name and
 * photo, an account that could not be confirmed, or one that does not exist. */
function RecipientResult({ check, confirmed, onConfirm, onChange }: { check: RecipientCheck; confirmed: boolean; onConfirm: (v: boolean) => void; onChange: () => void }) {
  const tone = check.status === "verified" ? "ring-success/35" : check.status === "not_found" ? "ring-danger/35" : "ring-info/35";
  return (
    <div className={`rounded-[22px] bg-surface p-4 ring-1 ring-inset ${tone}`} aria-live="polite">
      <div className="flex items-center gap-3">
        {check.status === "not_found" ? (
          <span className="flex size-12 shrink-0 items-center justify-center rounded-full bg-danger/12 ring-1 ring-inset ring-danger/25">
            <UserX className="size-6 text-danger" />
          </span>
        ) : (
          <Avatar name={check.display_name || check.username} photo={check.status === "verified" ? check.photo_url : null} size={48} />
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate text-[15.5px] font-semibold">{check.status === "verified" && check.display_name ? check.display_name : `@${check.username}`}</div>
          <div className="truncate text-[13px] text-text-3">{check.status === "verified" && check.display_name ? `@${check.username}` : "username получателя"}</div>
        </div>
        <button onClick={onChange} className="inline-flex shrink-0 items-center gap-1 rounded-xl px-2.5 py-1.5 text-[13px] font-semibold text-accent hover:bg-accent/10">
          <Pencil className="size-3.5" /> Изменить
        </button>
      </div>
      <div className="mt-3">
        {check.status === "verified" ? (
          <Badge tone="success" icon={<BadgeCheck className="size-3.5" />}>
            {check.is_self ? "Это ваш аккаунт" : "Аккаунт найден"}
          </Badge>
        ) : check.status === "not_found" ? (
          <Badge tone="danger" icon={<UserX className="size-3.5" />}>
            Аккаунт не найден
          </Badge>
        ) : (
          <Badge tone="info" icon={<CircleHelp className="size-3.5" />}>
            Не удалось проверить
          </Badge>
        )}
      </div>
      {check.message && <p className="mt-2 text-[13px] leading-relaxed text-text-2">{check.message}</p>}
      {check.status === "unverified" && (
        <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-2xl bg-info/8 p-3 ring-1 ring-inset ring-info/25">
          <input type="checkbox" checked={confirmed} onChange={(e) => onConfirm(e.target.checked)} className="mt-0.5 size-5 shrink-0 accent-[var(--c-accent)]" />
          <span className="text-[13px] leading-relaxed text-text-2">
            Я проверил(а): <b className="text-text">@{check.username}</b> — нужный аккаунт. Звёзды, отправленные на чужой username, вернуть нельзя.
          </span>
        </label>
      )}
    </div>
  );
}

export function Checkout() {
  const boot = useBoot();
  const { productId } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const me = useMe();
  const invalidateOrders = useInvalidateOrders();

  const product = boot.catalog.find((p) => String(p.id) === productId);
  const step = Math.min(2, Math.max(0, Number(params.get("step") ?? 0)));
  const goStep = (s: number) => setParams((prev) => ({ ...Object.fromEntries(prev), step: String(s) }));

  // --- step 1: amount
  const isCustom = product?.kind === "custom";
  const minStars = Math.max(product?.min_stars ?? 1, boot.delivery.min_stars);
  const maxStars = Math.min(product?.max_stars ?? boot.delivery.max_stars, boot.delivery.max_stars);
  const [custom, setCustom] = useState(() => {
    const asked = Number(params.get("stars"));
    return Number.isInteger(asked) && asked > 0 ? Math.min(maxStars, Math.max(minStars, asked)) : Math.min(maxStars, Math.max(minStars, 500));
  });
  const stars = isCustom ? custom : product?.stars_amount ?? 0;
  const amountValid = !isCustom || (custom >= minStars && custom <= maxStars);

  // --- step 2: recipient
  const qc = useQueryClient();
  const [recipientType, setRecipientType] = useState<"self" | "username">(() => (params.get("to") === "gift" ? "username" : "self"));
  const [username, setUsername] = useState("");
  const [recipientError, setRecipientError] = useState<string | null>(null);
  const [check, setCheck] = useState<RecipientCheck | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const myUsername = me.data?.user.username ?? null;
  const selfBlocked = recipientType === "self" && boot.delivery.requires_username && me.data && !myUsername;
  const cleanUsername = username.trim().replace(/^@/, "").replace(/^(https?:\/\/)?t\.me\//i, "").replace(/\/$/, "");

  const checkRecipient = useMutation({
    mutationFn: (name: string) =>
      qc.fetchQuery({
        queryKey: ["recipient", name.toLowerCase()],
        queryFn: () => api<RecipientCheck>("/recipients/check", { method: "POST", body: { username: name } }),
        staleTime: 60_000,
      }),
    onSuccess: (r) => {
      setRecipientError(null);
      setConfirmed(false);
      setCheck(r);
    },
    onError: (e) => {
      setCheck(null);
      setRecipientError(errorMessage(e));
    },
  });
  const runCheck = () => {
    if (!cleanUsername) return setRecipientError("Введите username получателя");
    if (!USERNAME_RE.test(cleanUsername)) return setRecipientError("5–32 символа: латиница, цифры и «_», начинается с буквы");
    checkRecipient.mutate(cleanUsername);
  };
  const resetRecipient = () => {
    setCheck(null);
    setConfirmed(false);
    setRecipientError(null);
  };
  const recipientReady =
    recipientType === "self"
      ? !selfBlocked
      : check !== null && check.username.toLowerCase() === cleanUsername.toLowerCase() && (check.status === "verified" || (check.status === "unverified" && confirmed));

  // --- step 3: payment
  const [provider, setProvider] = useState(boot.payment_methods[0]?.id ?? "");
  const [promoInput, setPromoInput] = useState("");
  const [promo, setPromo] = useState("");
  const [promoOpen, setPromoOpen] = useState(false);
  const [useBonus, setUseBonus] = useState(false);
  const debouncedStars = useDebounced(stars, 350);

  const quoteInput = product && amountValid ? { product_id: product.id, stars_amount: isCustom ? debouncedStars : null, promo_code: promo || undefined, use_bonus: useBonus, payment_provider: provider } : null;
  const quote = useQuote(quoteInput);
  const bonusAvailable = Number(quote.data?.bonus_available ?? me.data?.bonus.balance ?? 0);

  useEffect(() => {
    if (quote.data?.promo && !quote.data.promo.valid && promo) {
      setPromo("");
      toast(quote.data.promo.message ?? "Промокод не применён", "error");
    }
  }, [quote.data, promo, toast]);

  // A fresh idempotency key whenever the order contents change.
  const orderInput = useMemo(
    () => ({
      product_id: product?.id ?? 0,
      stars_amount: isCustom ? stars : null,
      recipient: recipientType === "self" ? { type: "self" as const } : { type: "username" as const, username: cleanUsername },
      payment_provider: provider,
      promo_code: promo || null,
      use_bonus: useBonus,
    }),
    [product?.id, isCustom, stars, recipientType, cleanUsername, provider, promo, useBonus],
  );
  const inputFingerprint = JSON.stringify(orderInput);
  const idemKey = useMemo(() => newIdempotencyKey(), [inputFingerprint]);
  const orderRef = useRef<OrderDetail | null>(null);

  const pay = useMutation({
    mutationFn: async () => {
      await requestWriteAccess(); // for status notifications in the chat; optional
      const order = await api<OrderDetail>("/orders", { method: "POST", body: orderInput, headers: { "Idempotency-Key": idemKey } });
      orderRef.current = order;
      const payment = await api<PaymentInfo>(`/orders/${order.id}/payment`, { method: "POST", body: { provider } });
      return { order, payment };
    },
    onSuccess: ({ order, payment }) => {
      invalidateOrders();
      if (payment.pay_url_kind === "internal") {
        navigate(`/pay/demo/${payment.id}`, { replace: true });
        return;
      }
      if (payment.pay_url) openPayment(payment.pay_url, payment.pay_url_kind, () => invalidateOrders());
      navigate(`/orders/${order.id}?paying=1`, { replace: true });
    },
    onError: (e) => {
      toast(errorMessage(e), "error");
      if (orderRef.current && !(e instanceof ApiError && e.status === 422)) {
        // The order exists; payment can be retried from the order screen.
        navigate(`/orders/${orderRef.current.id}`, { replace: true });
      }
    },
  });

  useEffect(() => {
    setClosingConfirmation(pay.isPending);
    return () => setClosingConfirmation(false);
  }, [pay.isPending]);

  if (!product) {
    return (
      <>
        <PageHeader title="Оформление" />
        <Page>
          <EmptyState icon={<Sparkles className="size-7 text-accent" />} title="Пакет недоступен" text="Возможно, он был изменён. Выберите пакет в каталоге." action={<Button onClick={() => navigate("/catalog")}>К каталогу</Button>} />
        </Page>
      </>
    );
  }

  if (!canAuthenticate) {
    return (
      <>
        <PageHeader title="Оформление" />
        <Page>
          <EmptyState
            icon={<Lock className="size-7 text-accent" />}
            title="Откройте магазин в Telegram"
            text="Покупка доступна в мини-приложении Telegram: так мы безопасно узнаём ваш аккаунт без паролей."
            action={boot.bot_username && <Button onClick={() => openExternal(`https://t.me/${boot.bot_username}`)}>Открыть бота</Button>}
          />
        </Page>
      </>
    );
  }

  const recipientLabel =
    recipientType === "self"
      ? myUsername
        ? `Себе · @${myUsername}`
        : "Себе"
      : check?.status === "verified" && check.display_name
        ? `${check.display_name} · @${check.username}`
        : `@${cleanUsername}`;
  const paymentMethod = boot.payment_methods.find((m) => m.id === provider);
  const canNext1 = amountValid && stars > 0;
  const canNext2 = recipientReady;

  return (
    <>
      <PageHeader title="Оформление" subtitle={boot.mode === "demo" ? "DEMO-режим · тестовая оплата" : undefined} right={boot.mode === "demo" ? <DemoBadge /> : undefined} />
      <Page>
        <StepIndicator step={step} />
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={step} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}>
            {step === 0 && (
              <section aria-label="Выбор пакета">
                <PackageHero
                  stars={stars}
                  price={isCustom ? quote.data?.subtotal ?? null : product.price}
                  perStar={isCustom ? product.price_per_star : product.price_per_star}
                  currency={boot.currency}
                  estimate={isCustom && quote.isFetching}
                />
                {isCustom ? (
                  <AmountPicker value={custom} min={minStars} max={maxStars} onChange={setCustom} />
                ) : (
                  <PackageSwitcher products={boot.catalog} currentId={product.id} currency={boot.currency} onPick={(id) => navigate(`/checkout/${id}`, { replace: true })} />
                )}
                {!amountValid && (
                  <p className="mt-3 flex items-center gap-1.5 px-1 text-[13px] text-danger">
                    <CircleAlert className="size-4" /> Укажите от {minStars} до {maxStars} звёзд
                  </p>
                )}
                <BottomBar>
                  <Button size="lg" block disabled={!canNext1} onClick={() => goStep(1)} iconRight={<ArrowRight className="size-5" />}>
                    Далее
                  </Button>
                </BottomBar>
              </section>
            )}

            {step === 1 && (
              <section aria-label="Получатель" className="space-y-4">
                <h2 className="px-1 font-display text-[20px] font-semibold tracking-[-0.025em]">Кому отправить звёзды?</h2>
                {boot.delivery.gifts_enabled && (
                  <Segmented
                    label="Получатель"
                    value={recipientType}
                    onChange={(v) => {
                      setRecipientType(v);
                      setRecipientError(null);
                    }}
                    options={[
                      { id: "self", label: "Купить себе" },
                      { id: "username", label: "В подарок" },
                    ]}
                  />
                )}
                {recipientType === "self" ? (
                  <div className="flex items-center gap-3 rounded-[22px] bg-surface p-4 ring-1 ring-inset ring-line">
                    <Avatar name={me.data?.user.first_name ?? "Я"} photo={me.data?.user.photo_url} size={46} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[15.5px] font-semibold">{me.data ? `${me.data.user.first_name} ${me.data.user.last_name ?? ""}` : "Ваш аккаунт"}</div>
                      <div className="truncate text-[13px] text-text-3">{myUsername ? `@${myUsername}` : "username не задан"}</div>
                    </div>
                    {!selfBlocked && <BadgeCheck className="size-6 text-success" />}
                  </div>
                ) : check && check.username.toLowerCase() === cleanUsername.toLowerCase() ? (
                  <RecipientResult check={check} confirmed={confirmed} onConfirm={setConfirmed} onChange={resetRecipient} />
                ) : (
                  <div className="space-y-3">
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        runCheck();
                      }}
                    >
                      <Field
                        name="recipient"
                        label="Username получателя"
                        leading={<AtSign className="size-[18px]" />}
                        placeholder="username"
                        autoCapitalize="off"
                        autoCorrect="off"
                        spellCheck={false}
                        enterKeyHint="search"
                        value={username}
                        onChange={(e) => {
                          setUsername(e.target.value);
                          resetRecipient();
                        }}
                        error={recipientError}
                        hint="Публичный @username из профиля Telegram получателя"
                      />
                      <Button type="submit" variant="secondary" block className="mt-3" loading={checkRecipient.isPending} icon={<Search className="size-4" />} disabled={!cleanUsername}>
                        Проверить получателя
                      </Button>
                    </form>
                    {checkRecipient.isPending && (
                      <div className="flex items-center gap-3 rounded-[22px] bg-surface p-4 ring-1 ring-inset ring-line" aria-busy="true">
                        <Skeleton className="size-12 rounded-full" />
                        <div className="flex-1 space-y-2">
                          <Skeleton className="h-4 w-32" />
                          <Skeleton className="h-3 w-20" />
                        </div>
                      </div>
                    )}
                  </div>
                )}
                {selfBlocked && (
                  <div className="flex gap-3 rounded-[20px] bg-warning/10 p-4 text-[13.5px] leading-relaxed text-text-2 ring-1 ring-inset ring-warning/25">
                    <CircleAlert className="mt-0.5 size-5 shrink-0 text-warning" />
                    <span>
                      Для зачисления звёзд нужен публичный username. Задайте его в <b>Настройки → Имя пользователя</b> и откройте магазин заново
                      {boot.delivery.gifts_enabled && " — или отправьте звёзды другому человеку"}.
                    </span>
                  </div>
                )}
                <div className="flex gap-3 rounded-[20px] bg-surface-2/60 p-4 text-[12.5px] leading-relaxed text-text-3 ring-1 ring-inset ring-line">
                  <Lock className="mt-0.5 size-4 shrink-0" />
                  Мы не запрашиваем пароль, код входа или другие данные аккаунта. Никому их не сообщайте.
                </div>
                <BottomBar>
                  <Button size="lg" block disabled={!canNext2 || checkRecipient.isPending} onClick={() => goStep(2)} iconRight={<ArrowRight className="size-5" />}>
                    {recipientType === "username" && !check ? "Сначала проверьте получателя" : "Далее"}
                  </Button>
                </BottomBar>
              </section>
            )}

            {step === 2 && (
              <section aria-label="Подтверждение" className="space-y-4">
                <h2 className="px-1 font-display text-[20px] font-semibold tracking-[-0.025em]">Проверьте заказ</h2>
                <QuoteSummary quote={quote.data} loading={quote.isFetching} recipient={recipientLabel} paymentTitle={paymentMethod?.title} />
                {quote.isError && <p className="px-1 text-[13px] text-danger">{errorMessage(quote.error)}</p>}

                <PaymentMethods methods={boot.payment_methods} value={provider} onChange={setProvider} />

                <div className="rounded-[20px] bg-surface ring-1 ring-inset ring-line">
                  {!promoOpen && !promo ? (
                    <button className="flex w-full items-center gap-3 p-4 text-left text-[14px] font-semibold" onClick={() => setPromoOpen(true)}>
                      <TicketPercent className="size-5 text-accent-2" /> У меня есть промокод
                    </button>
                  ) : promo && quote.data?.promo?.valid ? (
                    <div className="flex items-center gap-3 p-4">
                      <TicketPercent className="size-5 text-success" />
                      <span className="flex-1 text-[14px] font-semibold">
                        Промокод <span className="text-success">{promo.toUpperCase()}</span> применён
                      </span>
                      <button className="text-[13px] font-semibold text-text-3 hover:text-text" onClick={() => setPromo("")}>
                        Убрать
                      </button>
                    </div>
                  ) : (
                    <form
                      className="flex items-center gap-2 p-2 pl-4"
                      onSubmit={(e) => {
                        e.preventDefault();
                        if (promoInput.trim()) setPromo(promoInput.trim());
                      }}
                    >
                      <TicketPercent className="size-5 shrink-0 text-accent-2" />
                      <input value={promoInput} onChange={(e) => setPromoInput(e.target.value.toUpperCase())} placeholder="Промокод" maxLength={32} className="h-11 min-w-0 flex-1 bg-transparent text-[15px] font-semibold uppercase outline-none placeholder:normal-case placeholder:text-text-3" aria-label="Промокод" autoFocus />
                      <Button size="sm" variant="secondary" type="submit" loading={Boolean(promo) && quote.isFetching}>
                        Применить
                      </Button>
                    </form>
                  )}
                </div>

                {boot.referral.enabled && bonusAvailable > 0 && (
                  <label className="flex cursor-pointer items-center gap-3 rounded-[20px] bg-surface p-4 ring-1 ring-inset ring-line">
                    <Gift className="size-5 text-gold" />
                    <span className="flex-1">
                      <span className="block text-[14px] font-semibold">Списать бонусы</span>
                      <span className="block text-[12.5px] text-text-3">
                        Доступно {formatMoney(bonusAvailable, boot.currency)} · до {boot.referral.max_bonus_spend_percent}% заказа
                      </span>
                    </span>
                    <input type="checkbox" className="peer sr-only" checked={useBonus} onChange={(e) => setUseBonus(e.target.checked)} />
                    <span className="relative h-7 w-12 rounded-full bg-surface-3 transition peer-checked:bg-accent peer-focus-visible:ring-2 peer-focus-visible:ring-accent after:absolute after:left-1 after:top-1 after:size-5 after:rounded-full after:bg-white after:shadow after:transition peer-checked:after:translate-x-5" aria-hidden />
                  </label>
                )}

                <p className="px-1 text-[12.5px] leading-relaxed text-text-3">
                  Нажимая «Оплатить», вы соглашаетесь с{" "}
                  <Link to="/info/terms" className="font-semibold text-accent">
                    условиями покупки и возврата
                  </Link>
                  . Заказ уйдёт в работу после подтверждения оплаты провайдером.
                </p>

                <BottomBar>
                  <Button
                    size="lg"
                    block
                    disabled={!quote.data || quote.isPlaceholderData || quote.data.stars_amount !== stars || !provider || quote.isError || boot.payment_methods.length === 0}
                    loading={pay.isPending}
                    onClick={() => pay.mutate()}
                    icon={<Lock className="size-[18px]" />}
                  >
                    {quote.data ? `Оплатить ${formatMoney(quote.data.total, quote.data.currency)}` : "Оплатить"}
                  </Button>
                  <p className="mt-2 flex items-center justify-center gap-1.5 text-[11.5px] text-text-3">
                    <User className="size-3.5" /> {recipientLabel}
                  </p>
                </BottomBar>
              </section>
            )}
          </motion.div>
        </AnimatePresence>
      </Page>
    </>
  );
}
