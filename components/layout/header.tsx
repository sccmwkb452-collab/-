"use client";

import { ArrowRight, Menu, Phone } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { MAIN_NAV } from "@/lib/navigation";
import { cn, phoneHref } from "@/lib/utils";
import { Logo } from "./logo";

interface HeaderProps {
  companyName: string;
  logoUrl: string | null;
  phone: string;
  workingHours: string;
}

export function Header({ companyName, logoUrl, phone, workingHours }: HeaderProps) {
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);
  const overlay = pathname === "/";
  const transparent = overlay && !scrolled;

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-40 transition-all duration-500 ease-[var(--ease-premium)]",
        transparent ? "bg-transparent" : "border-b border-border/60 bg-background/80 backdrop-blur-xl backdrop-saturate-150",
      )}
    >
      <div className={cn("container-page flex items-center gap-6 transition-all duration-500", scrolled ? "h-16" : "h-20")}>
        <Logo name={companyName} logoUrl={logoUrl} inverted={transparent} />

        <nav aria-label="Основная навигация" className="mx-auto hidden lg:block">
          <ul className="flex items-center gap-1">
            {MAIN_NAV.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "relative rounded-full px-4 py-2 text-sm font-medium transition-colors",
                      transparent ? "text-white/80 hover:text-white" : "text-foreground/70 hover:text-foreground",
                      active && (transparent ? "text-white" : "text-foreground"),
                    )}
                  >
                    {item.label}
                    {active && <span className="absolute inset-x-4 -bottom-0.5 h-px bg-accent" />}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="ml-auto flex items-center gap-2 lg:ml-0 lg:gap-5">
          <a
            href={phoneHref(phone)}
            className={cn("hidden flex-col items-end leading-tight xl:flex", transparent ? "text-white" : "text-foreground")}
          >
            <span className="text-sm font-semibold tabular">{phone}</span>
            <span className={cn("text-[11px]", transparent ? "text-white/60" : "text-muted-foreground")}>{workingHours}</span>
          </a>
          <Button asChild variant={transparent ? "light" : "default"} size="sm" className="hidden sm:inline-flex">
            <Link href="/calculator">
              Рассчитать стоимость
              <ArrowRight />
            </Link>
          </Button>
          <Button asChild variant={transparent ? "light" : "default"} size="sm" className="sm:hidden">
            <Link href="/calculator">Расчёт</Link>
          </Button>

          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className={cn("lg:hidden", transparent && "text-white hover:bg-white/10")} aria-label="Открыть меню">
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="p-6">
              <SheetTitle className="sr-only">Меню</SheetTitle>
              <SheetDescription className="sr-only">Навигация по сайту</SheetDescription>
              <Logo name={companyName} logoUrl={logoUrl} />
              <nav aria-label="Мобильная навигация" className="mt-6">
                <ul className="flex flex-col">
                  {[...MAIN_NAV, { href: "/faq", label: "Вопросы и ответы" }, { href: "/contacts", label: "Контакты" }].map((item) => (
                    <li key={item.href}>
                      <SheetClose asChild>
                        <Link
                          href={item.href}
                          className={cn(
                            "flex items-center justify-between border-b border-border/70 py-4 text-lg font-semibold",
                            pathname.startsWith(item.href) && "text-accent",
                          )}
                        >
                          {item.label}
                          <ArrowRight className="size-4 opacity-40" />
                        </Link>
                      </SheetClose>
                    </li>
                  ))}
                </ul>
              </nav>
              <div className="mt-auto space-y-3">
                <a href={phoneHref(phone)} className="flex items-center gap-3 rounded-2xl bg-secondary p-4">
                  <Phone className="size-5 text-accent" />
                  <span>
                    <span className="block font-semibold tabular">{phone}</span>
                    <span className="text-xs text-muted-foreground">{workingHours}</span>
                  </span>
                </a>
                <SheetClose asChild>
                  <Button asChild size="lg" className="w-full">
                    <Link href="/calculator">Рассчитать стоимость</Link>
                  </Button>
                </SheetClose>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
