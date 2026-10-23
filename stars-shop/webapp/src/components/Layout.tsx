import { Logo } from "@starshop/shared";
import { useIsFetching } from "@tanstack/react-query";
import { ChevronLeft, ReceiptText } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { useMe } from "../lib/queries";
import { isTelegram, tg } from "../lib/telegram";
import { useBoot } from "./BootContext";
import { DemoBadge } from "./ui/Badge";
import { IconButton } from "./ui/Button";
import { Spinner } from "./ui/Spinner";
import { cn } from "./ui/cn";

export function Avatar({ name, photo, size = 32 }: { name: string; photo?: string | null; size?: number }) {
  if (photo) return <img src={photo} alt="" width={size} height={size} className="rounded-full object-cover ring-1 ring-line" style={{ width: size, height: size }} referrerPolicy="no-referrer" />;
  return (
    <span className="inline-flex items-center justify-center rounded-full bg-accent-gradient font-display text-[13px] font-semibold text-white" style={{ width: size, height: size }}>
      {(name.trim()[0] ?? "★").toUpperCase()}
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
      <Link to="/" className="flex items-center gap-2" aria-label={boot.brand.name}>
        <Logo name={boot.brand.name} logoUrl={boot.brand.logo_url} size={34} />
        {boot.mode === "demo" && <DemoBadge />}
      </Link>
      <div className="flex items-center gap-2">
        <FetchIndicator />
        <IconButton label="Мои заказы" onClick={() => navigate("/orders")}>
          <ReceiptText className="size-[19px]" />
        </IconButton>
        <button
          onClick={() => navigate("/profile")}
          className="flex h-10 items-center gap-2 rounded-2xl bg-surface-2 py-1 pl-1 pr-3 ring-1 ring-inset ring-line transition hover:bg-surface-3 active:scale-95"
          aria-label="Мой профиль"
        >
          <Avatar name={name} photo={photo} />
          <span className="max-w-[92px] truncate text-[14px] font-semibold">{name}</span>
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
  return <main className={cn("px-4 pb-[calc(2rem+var(--safe-bottom))]", className)}>{children}</main>;
}
