import { Logo, LogoMark } from "@starshop/shared";
import { AnimatePresence, motion } from "motion/react";
import { Wrench } from "lucide-react";
import { Suspense, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router";
import { BootContext } from "./components/BootContext";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { BottomNav, isTabPath } from "./components/Layout";
import { ErrorState } from "./components/ui/States";
import { errorMessage } from "./lib/api";
import { useBootstrap } from "./lib/queries";
import { lazyPage } from "./lib/lazy";
import { isTelegram, startParam, tg } from "./lib/telegram";
import { applyAccents } from "./lib/theme";
import { Home } from "./pages/Home";

// Secondary screens load on demand: a lighter first paint on slow networks.
const Checkout = lazyPage(() => import("./pages/Checkout").then((m) => m.Checkout));
const DemoPay = lazyPage(() => import("./pages/DemoPay").then((m) => m.DemoPay));
const Terms = lazyPage(() => import("./pages/Info").then((m) => m.Terms));
const Lucky = lazyPage(() => import("./pages/Lucky").then((m) => m.Lucky));
const NotFound = lazyPage(() => import("./pages/NotFound").then((m) => m.NotFound));
const OrderDetailPage = lazyPage(() => import("./pages/OrderDetail").then((m) => m.OrderDetailPage));
const Orders = lazyPage(() => import("./pages/Orders").then((m) => m.Orders));
const Profile = lazyPage(() => import("./pages/Profile").then((m) => m.Profile));
const Referrals = lazyPage(() => import("./pages/Referrals").then((m) => m.Referrals));
const Support = lazyPage(() => import("./pages/Support").then((m) => m.Support));
const TicketPage = lazyPage(() => import("./pages/Support").then((m) => m.TicketPage));

function useTelegramBackButton() {
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const webApp = tg;
    if (!webApp || !isTelegram) return;
    const atRoot = isTabPath(location.pathname);
    const onBack = () => (window.history.state?.idx > 0 ? navigate(-1) : navigate("/", { replace: true }));
    if (atRoot) {
      webApp.BackButton.hide();
      return;
    }
    webApp.BackButton.show();
    webApp.BackButton.onClick(onBack);
    return () => webApp.BackButton.offClick(onBack);
  }, [location.pathname, navigate]);
}

/** Deep links: startapp=order_<number> | catalog | lucky | support | referrals */
function useStartParam() {
  const navigate = useNavigate();
  const handled = useRef(false);
  useEffect(() => {
    if (handled.current) return;
    handled.current = true;
    const param = startParam();
    if (!param) return;
    if (param.startsWith("order_")) navigate(`/orders?number=${encodeURIComponent(param.slice(6))}`);
    else if (param === "catalog") navigate("/catalog");
    else if (param === "lucky") navigate("/lucky");
    else if (param === "support") navigate("/support");
    else if (param === "referrals") navigate("/referrals");
  }, [navigate]);
}

/** First load. A cold server start can take several seconds: after a while
 * the customer is told what is going on instead of looking at a bare logo. */
function Splash() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 4000);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-5" aria-busy="true">
      <div className="relative">
        <span className="absolute inset-0 rounded-[18px] bg-accent/40 animate-[pulse-ring_1.6s_ease-out_infinite]" />
        <LogoMark size={56} />
      </div>
      <div className="h-1 w-24 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full w-1/2 animate-[shimmer_1.2s_infinite] rounded-full bg-accent-gradient" />
      </div>
      <p className={`max-w-[260px] text-center text-[13px] leading-relaxed text-text-3 transition-opacity duration-500 ${slow ? "opacity-100" : "opacity-0"}`} aria-live="polite">
        {slow ? "Подключаемся к магазину… Первый запуск может занять несколько секунд." : "\u00a0"}
      </p>
    </div>
  );
}

function PageFallback() {
  return (
    <div className="space-y-3 px-4 pt-20" aria-busy="true">
      <div className="h-40 animate-pulse rounded-[28px] bg-surface-2" />
      <div className="h-24 animate-pulse rounded-[28px] bg-surface-2" />
    </div>
  );
}

export function App() {
  const boot = useBootstrap();
  const location = useLocation();
  const navigate = useNavigate();
  useTelegramBackButton();
  useStartParam();

  useEffect(() => {
    if (boot.data) {
      applyAccents(boot.data.brand);
      document.title = `${boot.data.brand.name} — Telegram Stars`;
    }
  }, [boot.data]);

  if (boot.isPending) return <Splash />;
  if (boot.isError || !boot.data)
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <ErrorState text={errorMessage(boot.error)} onRetry={() => boot.refetch()} />
      </div>
    );
  if (boot.data.maintenance.enabled)
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center px-8 text-center">
        <Logo name={boot.data.brand.name} logoUrl={boot.data.brand.logo_url} size={40} />
        <div className="mt-10 flex size-16 items-center justify-center rounded-[22px] bg-surface-2 ring-1 ring-line">
          <Wrench className="size-7 text-accent" />
        </div>
        <h1 className="mt-5 font-display text-[20px] font-semibold">Технические работы</h1>
        <p className="mt-2 max-w-[300px] text-[14.5px] leading-relaxed text-text-2">{boot.data.maintenance.message}</p>
      </div>
    );

  return (
    <BootContext.Provider value={boot.data}>
      <div className="mx-auto min-h-dvh w-full max-w-[1080px] pl-[var(--safe-left)] pr-[var(--safe-right)] pt-[var(--safe-top)]">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <ErrorBoundary resetKey={location.pathname} onHome={() => navigate("/", { replace: true })}>
              <Suspense fallback={<PageFallback />}>
                <Routes location={location}>
                  <Route path="/" element={<Home />} />
                  <Route path="/catalog" element={<Home scrollTo="catalog" />} />
                  <Route path="/checkout/:productId" element={<Checkout />} />
                  <Route path="/lucky" element={<Lucky />} />
                  <Route path="/orders" element={<Orders />} />
                  <Route path="/orders/:id" element={<OrderDetailPage />} />
                  <Route path="/profile" element={<Profile />} />
                  <Route path="/referrals" element={<Referrals />} />
                  <Route path="/support" element={<Support />} />
                  <Route path="/support/:id" element={<TicketPage />} />
                  <Route path="/info/terms" element={<Terms />} />
                  {/* Old links: the refund rules are part of the terms page. */}
                  <Route path="/info/refund" element={<Navigate to="/info/terms#refund" replace />} />
                  <Route path="/pay/demo/:paymentId" element={<DemoPay />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          </motion.div>
        </AnimatePresence>
        {isTabPath(location.pathname) && <BottomNav />}
      </div>
    </BootContext.Provider>
  );
}
