import { Logo, LogoMark } from "@starshop/shared";
import { AnimatePresence, motion } from "motion/react";
import { Wrench } from "lucide-react";
import { lazy, Suspense, useEffect, useRef } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router";
import { BootContext } from "./components/BootContext";
import { ErrorState } from "./components/ui/States";
import { errorMessage } from "./lib/api";
import { useBootstrap } from "./lib/queries";
import { isTelegram, startParam, tg } from "./lib/telegram";
import { applyAccents } from "./lib/theme";
import { Home } from "./pages/Home";

// Secondary screens load on demand: a lighter first paint on slow networks.
const Checkout = lazy(() => import("./pages/Checkout").then((m) => ({ default: m.Checkout })));
const DemoPay = lazy(() => import("./pages/DemoPay").then((m) => ({ default: m.DemoPay })));
const Info = lazy(() => import("./pages/Info").then((m) => ({ default: m.Info })));
const NotFound = lazy(() => import("./pages/NotFound").then((m) => ({ default: m.NotFound })));
const OrderDetailPage = lazy(() => import("./pages/OrderDetail").then((m) => ({ default: m.OrderDetailPage })));
const Orders = lazy(() => import("./pages/Orders").then((m) => ({ default: m.Orders })));
const Profile = lazy(() => import("./pages/Profile").then((m) => ({ default: m.Profile })));
const Support = lazy(() => import("./pages/Support").then((m) => ({ default: m.Support })));
const TicketPage = lazy(() => import("./pages/Support").then((m) => ({ default: m.TicketPage })));

function useTelegramBackButton() {
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const webApp = tg;
    if (!webApp || !isTelegram) return;
    const atRoot = location.pathname === "/" || location.pathname === "/catalog";
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

/** Deep links: startapp=order_<number> | catalog | support */
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
    else if (param === "support") navigate("/support");
  }, [navigate]);
}

function Splash() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-5">
      <div className="relative">
        <span className="absolute inset-0 rounded-[18px] bg-accent/40 animate-[pulse-ring_1.6s_ease-out_infinite]" />
        <LogoMark size={56} />
      </div>
      <div className="h-1 w-24 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full w-1/2 animate-[shimmer_1.2s_infinite] rounded-full bg-accent-gradient" />
      </div>
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
            <Suspense fallback={<PageFallback />}>
            <Routes location={location}>
              <Route path="/" element={<Home />} />
              <Route path="/catalog" element={<Home scrollTo="catalog" />} />
              <Route path="/checkout/:productId" element={<Checkout />} />
              <Route path="/orders" element={<Orders />} />
              <Route path="/orders/:id" element={<OrderDetailPage />} />
              <Route path="/profile" element={<Profile />} />
              <Route path="/support" element={<Support />} />
              <Route path="/support/:id" element={<TicketPage />} />
              <Route path="/info/:page" element={<Info />} />
              <Route path="/pay/demo/:paymentId" element={<DemoPay />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
            </Suspense>
          </motion.div>
        </AnimatePresence>
      </div>
    </BootContext.Provider>
  );
}
