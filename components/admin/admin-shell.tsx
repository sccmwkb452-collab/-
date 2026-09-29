"use client";

import { ExternalLink, LogOut, Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { logoutAction } from "@/lib/actions/auth";
import { cn } from "@/lib/utils";
import { ADMIN_NAV } from "./nav";

interface ShellProps {
  companyName: string;
  admin: { name: string; email: string };
  newLeads: number;
  children: React.ReactNode;
}

function NavLinks({ newLeads, onNavigate }: { newLeads: number; onNavigate?: boolean }) {
  const pathname = usePathname();
  return (
    <ul className="space-y-1">
      {ADMIN_NAV.map((item) => {
        const active = "exact" in item && item.exact ? pathname === item.href : pathname.startsWith(item.href);
        const link = (
          <Link
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
              active ? "bg-primary text-primary-foreground" : "text-foreground/70 hover:bg-secondary hover:text-foreground",
            )}
          >
            <item.icon className="size-4" />
            {item.label}
            {item.href === "/admin/leads" && newLeads > 0 && (
              <span className={cn("ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold tabular", active ? "bg-white/15" : "bg-accent text-white")}>{newLeads}</span>
            )}
          </Link>
        );
        return <li key={item.href}>{onNavigate ? <SheetClose asChild>{link}</SheetClose> : link}</li>;
      })}
    </ul>
  );
}

function Footer({ admin }: { admin: ShellProps["admin"] }) {
  return (
    <div className="space-y-2 border-t border-border pt-4">
      <Link href="/" target="_blank" className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground">
        <ExternalLink className="size-4" />
        Открыть сайт
      </Link>
      <div className="flex items-center gap-3 px-3 py-2">
        <span className="flex size-9 items-center justify-center rounded-full bg-sand text-sm font-semibold">{admin.name.slice(0, 1)}</span>
        <span className="min-w-0 flex-1 text-sm">
          <span className="block truncate font-medium">{admin.name}</span>
          <span className="block truncate text-xs text-muted-foreground">{admin.email}</span>
        </span>
        <form action={logoutAction}>
          <Button type="submit" variant="ghost" size="icon-sm" aria-label="Выйти" title="Выйти">
            <LogOut className="size-4" />
          </Button>
        </form>
      </div>
    </div>
  );
}

export function AdminShell({ companyName, admin, newLeads, children }: ShellProps) {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16rem_1fr]">
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-border bg-white p-4 lg:flex">
        <Link href="/admin" className="px-3 py-3 text-sm font-extrabold tracking-[0.14em] uppercase">
          {companyName}
          <span className="ml-2 rounded bg-secondary px-1.5 py-0.5 text-[10px] tracking-normal text-muted-foreground normal-case">admin</span>
        </Link>
        <nav aria-label="Админ-навигация" className="mt-6 flex-1">
          <NavLinks newLeads={newLeads} />
        </nav>
        <Footer admin={admin} />
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-white/90 px-4 backdrop-blur lg:hidden">
          <Link href="/admin" className="text-sm font-extrabold tracking-[0.14em] uppercase">{companyName}</Link>
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Меню">
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="bg-white p-4">
              <SheetTitle className="px-3 pt-2">Меню</SheetTitle>
              <SheetDescription className="sr-only">Разделы админ-панели</SheetDescription>
              <nav aria-label="Админ-навигация" className="flex-1">
                <NavLinks newLeads={newLeads} onNavigate />
              </nav>
              <Footer admin={admin} />
            </SheetContent>
          </Sheet>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10">{children}</main>
      </div>
    </div>
  );
}
