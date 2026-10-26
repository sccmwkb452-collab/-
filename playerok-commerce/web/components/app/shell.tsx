"use client";

import {
  AlertTriangle,
  Bell,
  Bot,
  ChartLine,
  FileText,
  ImageIcon,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  Package,
  ScrollText,
  Search,
  Settings,
  Shield,
  ShieldAlert,
  ShoppingCart,
  Store,
  Users,
  Wallet,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api";
import { cn } from "@/lib/format";
import { logout, useSession } from "@/lib/session";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }>; permission?: string };

const NAV: { title: string; items: NavItem[] }[] = [
  { title: "Обзор", items: [{ href: "/", label: "Главная панель", icon: LayoutDashboard }] },
  {
    title: "Продажи",
    items: [
      { href: "/orders", label: "Заказы", icon: ShoppingCart },
      { href: "/messages", label: "Сообщения покупателей", icon: MessageSquare },
      { href: "/listings", label: "Объявления", icon: FileText },
      { href: "/products", label: "Товары", icon: Package },
    ],
  },
  {
    title: "Деньги и рынок",
    items: [
      { href: "/analytics", label: "Аналитика и отчёты", icon: ChartLine },
      { href: "/pricing", label: "Прибыль и цены", icon: Wallet },
      { href: "/research", label: "Поиск товаров", icon: Search },
      { href: "/suppliers", label: "Поставщики", icon: Store },
      { href: "/images", label: "Генератор изображений", icon: ImageIcon },
    ],
  },
  {
    title: "Автоматизация",
    items: [
      { href: "/autosettings", label: "Автонастройки", icon: Bot },
      { href: "/notifications", label: "Уведомления", icon: Bell },
      { href: "/history", label: "Журнал операций", icon: ScrollText },
      { href: "/errors", label: "Ошибки интеграций", icon: AlertTriangle },
    ],
  },
  {
    title: "Система",
    items: [
      { href: "/security", label: "Безопасность", icon: Shield },
      { href: "/users", label: "Пользователи", icon: Users, permission: "users.manage" },
      { href: "/settings", label: "Настройки", icon: Settings },
    ],
  },
];

type Health = { mode: "test" | "live"; kill_switch: { active: boolean; reason: string }; worker: { ok: boolean }; bot: { ok: boolean } };

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(href + "/");
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { can } = useSession();
  return (
    <nav className="scrollbar-thin flex-1 overflow-y-auto px-3 pb-6" aria-label="Разделы панели">
      {NAV.map((group) => (
        <div key={group.title} className="mt-5 first:mt-2">
          <p className="mb-1.5 px-2.5 text-[11px] font-medium tracking-wider text-subtle uppercase">{group.title}</p>
          <ul className="flex flex-col gap-0.5">
            {group.items
              .filter((item) => !item.permission || can(item.permission))
              .map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13.5px] transition-colors",
                        active
                          ? "bg-primary/12 font-medium text-foreground shadow-[inset_2px_0_0_var(--primary)]"
                          : "text-muted-foreground hover:bg-surface-2 hover:text-foreground",
                      )}
                    >
                      <item.icon className={cn("size-4 shrink-0", active ? "text-highlight" : "text-subtle group-hover:text-muted-foreground")} />
                      <span className="truncate">{item.label}</span>
                    </Link>
                  </li>
                );
              })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5 px-5 py-4">
      <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-primary to-highlight text-sm font-bold text-white shadow-lg shadow-primary/20">
        P
      </span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold">PlayerOK Commerce</span>
        <span className="block text-[11px] text-muted-foreground">Панель управления</span>
      </span>
    </Link>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const { me } = useSession();
  const health = useApi<Health>("/health/details");
  const pathname = usePathname();

  React.useEffect(() => {
    const id = setInterval(health.reload, 60_000);
    return () => clearInterval(id);
  }, [health.reload]);

  const h = health.data;
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-border bg-[#0b101b] lg:flex">
        <Brand />
        <Sidebar />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 flex-col border-r border-border bg-[#0b101b] animate-in-soft">
            <div className="flex items-center justify-between pr-3">
              <Brand />
              <Button variant="ghost" size="icon-sm" onClick={() => setOpen(false)} aria-label="Закрыть меню">
                <X />
              </Button>
            </div>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur-md sm:px-6">
          <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setOpen(true)} aria-label="Открыть меню">
            <Menu />
          </Button>
          <div className="flex min-w-0 flex-1 items-center gap-2">
            {h && (
              <Link href="/security" className="flex min-w-0 items-center gap-2">
                {h.mode === "live" ? (
                  <Badge tone="success">● Боевой режим</Badge>
                ) : (
                  <Badge tone="warning" className="min-w-0">
                    <span className="truncate">
                      Тестовый режим<span className="hidden md:inline"> — закупки и публикации не выполняются</span>
                    </span>
                  </Badge>
                )}
                {h.kill_switch.active && (
                  <Badge tone="danger">
                    <ShieldAlert /> <span className="hidden sm:inline">Автоматизация </span>остановлена
                  </Badge>
                )}
              </Link>
            )}
          </div>
          {h && (
            <div className="hidden items-center gap-3 text-xs text-muted-foreground md:flex">
              <span className="flex items-center gap-1.5">
                <span className={cn("size-1.5 rounded-full", h.worker.ok ? "bg-success" : "bg-danger")} /> Воркер {h.worker.ok ? "работает" : "не отвечает"}
              </span>
              <span className="flex items-center gap-1.5">
                <span className={cn("size-1.5 rounded-full", h.bot.ok ? "bg-success" : "bg-danger")} /> Бот {h.bot.ok ? "работает" : "не отвечает"}
              </span>
            </div>
          )}
          <div className="flex items-center gap-2 border-l border-border pl-3">
            <div className="hidden text-right leading-tight sm:block">
              <p className="text-[13px] font-medium">{me?.display_name ?? "…"}</p>
              <p className="text-[11px] text-muted-foreground">{me?.role_name}</p>
            </div>
            <Button variant="ghost" size="icon-sm" onClick={logout} aria-label="Выйти" title="Выйти">
              <LogOut />
            </Button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 lg:px-8 animate-in-soft" key={pathname}>
          {children}
        </main>
      </div>
    </div>
  );
}
