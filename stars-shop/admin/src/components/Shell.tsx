import { LogoMark } from "@starshop/shared";
import {
  BadgePercent,
  ChartNoAxesColumn,
  FileText,
  LogOut,
  Menu,
  MessagesSquare,
  Moon,
  Package,
  ReceiptText,
  ScrollText,
  Settings,
  Sun,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router";
import { can, useAdmin, useAuth } from "../lib/auth";
import { applyTheme, initialTheme } from "../lib/theme";
import type { Role } from "../lib/types";
import { cn } from "./ui";

const NAV: { to: string; label: string; icon: typeof Package; role: Role }[] = [
  { to: "/", label: "Обзор", icon: ChartNoAxesColumn, role: "manager" },
  { to: "/orders", label: "Заказы", icon: ReceiptText, role: "support" },
  { to: "/catalog", label: "Каталог", icon: Package, role: "support" },
  { to: "/users", label: "Пользователи", icon: Users, role: "support" },
  { to: "/support", label: "Поддержка", icon: MessagesSquare, role: "support" },
  { to: "/promo", label: "Промокоды", icon: BadgePercent, role: "support" },
  { to: "/referrals", label: "Рефералы", icon: UserPlus, role: "support" },
  { to: "/content", label: "Контент", icon: FileText, role: "manager" },
  { to: "/settings", label: "Настройки", icon: Settings, role: "support" },
  { to: "/audit", label: "Журнал действий", icon: ScrollText, role: "manager" },
];

const ROLE_LABEL: Record<Role, string> = { owner: "Владелец", manager: "Менеджер", support: "Поддержка" };

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const admin = useAdmin();
  return (
    <nav className="space-y-0.5" aria-label="Разделы">
      {NAV.filter((n) => can(admin, n.role)).map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === "/"}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13.5px] font-semibold transition",
              isActive ? "bg-accent/14 text-text ring-1 ring-inset ring-accent/30" : "text-text-2 hover:bg-surface-2 hover:text-text",
            )
          }
        >
          <n.icon className="size-[18px]" aria-hidden />
          {n.label}
        </NavLink>
      ))}
    </nav>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const admin = useAdmin();
  const { logout } = useAuth();
  const [theme, setTheme] = useState(initialTheme);
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => applyTheme(theme), [theme]);
  useEffect(() => setOpen(false), [location.pathname]);

  const footer = (
    <div className="space-y-3 border-t border-line pt-4">
      <div className="flex items-center gap-3 px-1">
        <span className="flex size-9 items-center justify-center rounded-full bg-accent-gradient text-[13px] font-bold text-white">{(admin.display_name || admin.username || "A")[0]?.toUpperCase()}</span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold">{admin.display_name || (admin.username ? `@${admin.username}` : admin.telegram_id)}</div>
          <div className="text-[11.5px] text-text-3">{ROLE_LABEL[admin.role]}</div>
        </div>
      </div>
      <div className="flex gap-2">
        <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} className="flex h-9 flex-1 items-center justify-center gap-2 rounded-xl bg-surface-2 text-[12.5px] font-semibold text-text-2 ring-1 ring-inset ring-line hover:text-text">
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          {theme === "dark" ? "Светлая" : "Тёмная"}
        </button>
        <button onClick={() => void logout()} aria-label="Выйти" title="Выйти" className="flex size-9 items-center justify-center rounded-xl bg-surface-2 text-text-2 ring-1 ring-inset ring-line hover:text-danger">
          <LogOut className="size-4" />
        </button>
      </div>
    </div>
  );

  const brand = (
    <div className="flex items-center gap-2.5 px-1">
      <LogoMark size={30} />
      <div>
        <div className="font-display text-[14px] font-semibold leading-tight">Pulsar</div>
        <div className="text-[11px] text-text-3">Админ-панель</div>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 border-r border-line bg-surface/60 p-4 lg:flex">
        {brand}
        <div className="flex-1 overflow-y-auto">
          <Nav />
        </div>
        {footer}
      </aside>
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-bg/90 px-4 py-3 backdrop-blur-xl lg:hidden">
        {brand}
        <button onClick={() => setOpen(true)} aria-label="Меню" className="rounded-xl p-2 ring-1 ring-line">
          <Menu className="size-5" />
        </button>
      </header>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex w-[280px] flex-col gap-6 bg-surface p-4 shadow-2xl">
            <div className="flex items-center justify-between">
              {brand}
              <button onClick={() => setOpen(false)} aria-label="Закрыть меню" className="rounded-lg p-1.5 text-text-3">
                <X className="size-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <Nav onNavigate={() => setOpen(false)} />
            </div>
            {footer}
          </div>
        </div>
      )}
      <main className="min-w-0 px-4 py-6 sm:px-8 sm:py-8">
        <div className="mx-auto max-w-[1240px]">{children}</div>
      </main>
    </div>
  );
}
