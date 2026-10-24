import { Logo } from "@starshop/shared";
import { useIsFetching } from "@tanstack/react-query";
import { ChevronLeft, Clover, House, ReceiptText, UserRound } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router";
import { useMe } from "../lib/queries";
import { haptic, isTelegram, tg } from "../lib/telegram";
import { useBoot } from "./BootContext";
import { DemoBadge } from "./ui/Badge";
import { IconButton } from "./ui/Button";
import { Spinner } from "./ui/Spinner";
import { cn } from "./ui/cn";

export function Avatar({ name, photo, size = 32 }: { name: string; photo?: string | null; size?: number }) {
  // A photo that fails to load falls back to the initial, never to a stock image.
  const [failed, setFailed] = useState<string | null>(null);
  if (photo && failed !== photo)
    return (
      <img
        src={photo}
        alt=""
        width={size}
        height={size}
        className="shrink-0 rounded-full object-cover ring-1 ring-line"
        style={{ width: size, height: size }}
        referrerPolicy="no-referrer"
        onError={() => setFailed(photo)}
      />
    );
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full bg-accent-gradient font-display font-semibold text-white"
      style={{ width: size, height: size, fontSize: Math.max(12, Math.round(size * 0.4)) }}
      aria-hidden
    >
      {(name.replace(/^@/, "").trim()[0] ?? "★").toUpperCase()}
    </span>
  );
}

function FetchIndicator() {
  const fetching = useIsFetching();
  return <Spinner className={cn("size-4 text-text-3 transition-opacity", fetching ? "opacity-100" : "opacity-0")} />;
}

/** Home header: brand, live fetch indicator, orders, profile chip. */
export function HomeHeader() {
  const boot = useBoot();
  const me = useMe();
  const navigate = useNavigate();
  const tgUser = tg?.initDataUnsafe.user;
  const name = me.data?.user.first_name || tgUser?.first_name || "Профиль";
  const photo = me.data?.user.photo_url ?? tgUser?.photo_url;
  return (
    <header className="sticky top-0 z-30 mb-2 flex items-center justify-between gap-3 bg-bg/90 px-4 py-3 backdrop-blur-xl">
      <Link to="/" className="flex min-w-0 items-center gap-2" aria-label={boot.brand.name}>
        <Logo name={boot.brand.name} logoUrl={boot.brand.logo_url} size={34} className="min-w-0" />
        {boot.mode === "demo" && <DemoBadge className="shrink-0" />}
      </Link>
      <div className="flex shrink-0 items-center gap-2">
        <FetchIndicator />
        <IconButton label="Мои заказы" onClick={() => navigate("/orders")}>
          <ReceiptText className="size-[19px]" />
        </IconButton>
        <button
          onClick={() => navigate("/profile")}
          className="flex h-10 items-center gap-2 rounded-2xl bg-surface-2 py-1 pl-1 pr-3 ring-1 ring-inset ring-line transition hover:bg-surface-3 active:scale-95 max-[380px]:pr-1"
          aria-label="Мой профиль"
        >
          <Avatar name={name} photo={photo} />
          <span className="max-w-[92px] truncate text-[14px] font-semibold max-[380px]:hidden">{name}</span>
        </button>
      </div>
    </header>
  );
}

/** Sub-page header. Inside Telegram the native BackButton is used. */
export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  const navigate = useNavigate();
  return (
    <header className="sticky top-0 z-30 mb-3 flex items-center gap-2 bg-bg/90 px-4 py-3 backdrop-blur-xl">
      {!isTelegram && (
        <IconButton label="Назад" onClick={() => (window.history.state?.idx > 0 ? navigate(-1) : navigate("/"))}>
          <ChevronLeft className="size-5" />
        </IconButton>
      )}
      <div className="min-w-0 flex-1 px-1">
        <h1 className="truncate font-display text-[19px] font-semibold tracking-[-0.025em]">{title}</h1>
        {subtitle && <p className="truncate text-[12.5px] text-text-3">{subtitle}</p>}
      </div>
      <FetchIndicator />
      {right}
    </header>
  );
}

export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <main className={cn("px-4 pb-[calc(2rem+var(--safe-bottom)+var(--nav-h,0px))]", className)}>{children}</main>;
}

const TABS = ["/", "/catalog", "/lucky", "/orders", "/profile", "/referrals"];

/** Screens with the bottom navigation (and without the Telegram back button). */
export function isTabPath(path: string): boolean {
  return TABS.includes(path.length > 1 ? path.replace(/\/$/, "") : path);
}

const NAV_HEIGHT = 62;

/** Bottom navigation: Главная · Lucky · Заказы · Профиль. */
export function BottomNav() {
  const boot = useBoot();
  useEffect(() => {
    // Sticky action bars and page paddings move up by the height of the bar.
    const root = document.documentElement;
    root.style.setProperty("--nav-h", `${NAV_HEIGHT}px`);
    return () => {
      root.style.removeProperty("--nav-h");
    };
  }, []);
  const items = [
    { to: "/", label: "Главная", icon: House, end: true },
    ...(boot.lucky.available ? [{ to: "/lucky", label: "Lucky", icon: Clover, end: false }] : []),
    { to: "/orders", label: "Заказы", icon: ReceiptText, end: false },
    { to: "/profile", label: "Профиль", icon: UserRound, end: false },
  ];
  return (
    <nav
      aria-label="Разделы"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-bg/92 pb-[var(--safe-bottom)] backdrop-blur-xl"
    >
      <div className="mx-auto flex max-w-[620px] px-2" style={{ height: NAV_HEIGHT }}>
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            replace
            onClick={() => haptic.select()}
            className={({ isActive }) =>
              cn(
                "flex flex-1 flex-col items-center justify-center gap-1 text-[11px] font-semibold transition-colors",
                isActive ? "text-accent" : "text-text-3 hover:text-text-2",
              )
            }
          >
            {({ isActive }) => (
              <>
                <span className={cn("flex h-7 w-12 items-center justify-center rounded-full transition-colors", isActive && "bg-accent/14")}>
                  <Icon className="size-[20px]" strokeWidth={isActive ? 2.4 : 2} />
                </span>
                {label}
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
