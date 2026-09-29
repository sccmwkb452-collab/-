"use client";

import { AnimatePresence, motion } from "framer-motion";
import { SearchX, SlidersHorizontal, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { pluralize } from "@/lib/utils";
import type { ProjectCardData } from "@/types/project";
import { FilterPanel } from "./filter-panel";
import { applyFilters, countActive, EMPTY_FILTERS, filtersToParams, parseFilters, SORT_OPTIONS, type CatalogFilters } from "./filters";
import { ProjectCard } from "./project-card";

export function ProjectCatalog({ projects }: { projects: ProjectCardData[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();
  const [filters, setFilters] = useState<CatalogFilters>(() => parseFilters(new URLSearchParams(searchParams.toString())));

  const priceBounds = useMemo<[number, number]>(() => {
    if (!projects.length) return [0, 0];
    const prices = projects.map((p) => p.priceFrom);
    return [Math.floor(Math.min(...prices) / 100000) * 100000, Math.ceil(Math.max(...prices) / 100000) * 100000];
  }, [projects]);

  const visible = useMemo(() => applyFilters(projects, filters), [projects, filters]);
  const active = countActive(filters);

  const update = (next: CatalogFilters) => {
    setFilters(next);
    const query = filtersToParams(next).toString();
    startTransition(() => router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false }));
  };
  const reset = () => update({ ...EMPTY_FILTERS, sort: filters.sort });
  const countLabel = `${visible.length} ${pluralize(visible.length, ["проект", "проекта", "проектов"])}`;

  if (!projects.length) {
    return (
      <div className="container-page pb-24">
        <div className="rounded-3xl border border-dashed border-foreground/15 p-12 text-center">
          <p className="text-xl font-semibold">Каталог пополняется</p>
          <p className="mt-2 text-muted-foreground">Пока здесь нет опубликованных проектов. Рассчитайте стоимость своего дома в конструкторе.</p>
          <Button asChild className="mt-6"><a href="/calculator">Открыть калькулятор</a></Button>
        </div>
      </div>
    );
  }

  return (
    <div className="container-page grid gap-10 pb-24 lg:grid-cols-[18rem_1fr] xl:gap-14">
      <aside className="hidden lg:block" aria-label="Фильтры проектов">
        <div className="sticky top-24">
          <div className="mb-6 flex items-center justify-between">
            <p className="font-semibold">Фильтры</p>
            {active > 0 && (
              <button type="button" onClick={reset} className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline cursor-pointer">
                Сбросить
              </button>
            )}
          </div>
          <FilterPanel filters={filters} priceBounds={priceBounds} onChange={update} />
        </div>
      </aside>

      <div>
        <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground" aria-live="polite">
            Найдено: <span className="font-semibold text-foreground">{countLabel}</span>
          </p>
          <div className="flex items-center gap-2">
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="sm" className="lg:hidden">
                  <SlidersHorizontal />
                  Фильтры
                  {active > 0 && <span className="flex size-5 items-center justify-center rounded-full bg-accent text-[11px] text-white">{active}</span>}
                </Button>
              </SheetTrigger>
              <SheetContent side="bottom" className="px-5 pt-6 pb-5">
                <SheetTitle>Фильтры</SheetTitle>
                <SheetDescription className="sr-only">Подбор проекта по параметрам</SheetDescription>
                <div className="-mx-5 overflow-y-auto px-5">
                  <FilterPanel filters={filters} priceBounds={priceBounds} onChange={update} />
                </div>
                <div className="flex gap-2 border-t border-border pt-4">
                  <Button variant="outline" onClick={reset} disabled={!active}>Сбросить</Button>
                  <SheetTrigger asChild>
                    <Button className="flex-1">Показать {countLabel}</Button>
                  </SheetTrigger>
                </div>
              </SheetContent>
            </Sheet>
            <Select value={filters.sort} onValueChange={(sort) => update({ ...filters, sort })}>
              <SelectTrigger className="h-9 w-auto min-w-48 rounded-full text-sm" aria-label="Сортировка">
                <SelectValue />
              </SelectTrigger>
              <SelectContent align="end">
                {SORT_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {active > 0 && (
          <div className="mb-8 flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={reset}>
              <X />
              Сбросить все фильтры
            </Button>
          </div>
        )}

        {visible.length ? (
          <motion.ul layout className="grid gap-x-6 gap-y-12 md:grid-cols-2 2xl:grid-cols-3">
            <AnimatePresence mode="popLayout">
              {visible.map((p, i) => (
                <motion.li
                  key={p.id}
                  layout
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.97 }}
                  transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                >
                  <ProjectCard project={p} priority={i < 2} />
                </motion.li>
              ))}
            </AnimatePresence>
          </motion.ul>
        ) : (
          <div className="flex flex-col items-center rounded-3xl border border-dashed border-foreground/15 px-6 py-20 text-center">
            <SearchX className="size-10 text-accent" aria-hidden />
            <p className="mt-5 text-xl font-semibold">Под эти параметры проектов нет</p>
            <p className="mt-2 max-w-md text-muted-foreground">
              Попробуйте ослабить фильтры или рассчитайте стоимость индивидуального дома в конструкторе.
            </p>
            <div className="mt-7 flex flex-col gap-2 sm:flex-row">
              <Button onClick={reset}>Сбросить фильтры</Button>
              <Button asChild variant="outline"><a href="/calculator">Рассчитать свой дом</a></Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
