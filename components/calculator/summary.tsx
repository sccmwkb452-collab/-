"use client";

import { ChevronUp } from "lucide-react";
import Image from "next/image";
import { CONSTRUCTION_PERIODS } from "@/lib/constants";
import type { EstimateResult, PricingConfig } from "@/lib/pricing/types";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { AnimatedPrice } from "./animated-price";
import type { CalculatorState, ProjectContext } from "./types";

interface SummaryProps {
  state: CalculatorState;
  config: PricingConfig;
  estimate: EstimateResult | null;
  project: ProjectContext | null;
}

function bedroomsLabel(n: number) {
  return n >= 5 ? "5+ спален" : `${n} ${n === 1 ? "спальня" : "спальни"}`;
}

export function summaryRows(state: CalculatorState, config: PricingConfig) {
  const ht = config.houseTypes.find((h) => h.code === state.houseType);
  return [
    { label: "Площадь", value: `${state.area} м²` },
    { label: "Тип", value: ht ? (ht.code === "mansard" ? "С мансардой" : `${ht.floors} ${ht.floors === 1 ? "этаж" : "этажа"}`) : null },
    { label: "Спальни", value: bedroomsLabel(state.bedrooms) },
    { label: "Технология", value: config.technologies.find((t) => t.slug === state.technology)?.name ?? null },
    { label: "Комплектация", value: config.packages.find((p) => p.code === state.package)?.name ?? null },
    { label: "Сроки", value: CONSTRUCTION_PERIODS.find((p) => p.code === state.period)?.label ?? null },
  ];
}

function SummaryBody({ state, config, estimate, project }: SummaryProps) {
  const rows = summaryRows(state, config);
  const options = config.options.filter((o) => state.options.includes(o.code));
  return (
    <>
      {project && (
        <div className="mb-6 flex items-center gap-3 rounded-2xl bg-secondary p-2.5">
          {project.cover && (
            <span className="relative size-14 shrink-0 overflow-hidden rounded-xl">
              <Image src={project.cover} alt="" fill sizes="56px" className="object-cover" />
            </span>
          )}
          <span className="text-sm">
            <span className="block text-xs text-muted-foreground">Проект</span>
            <span className="font-semibold">{project.title}</span>
          </span>
        </div>
      )}
      <dl className="space-y-3 text-[15px]">
        {rows.map((r) => (
          <div key={r.label} className="flex justify-between gap-4">
            <dt className="text-muted-foreground">{r.label}</dt>
            <dd className={r.value ? "text-right font-medium" : "text-muted-foreground/50"}>{r.value ?? "—"}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-6 border-t border-border pt-5">
        <p className="text-sm text-muted-foreground">Дополнительно</p>
        {options.length ? (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {options.map((o) => (
              <li key={o.code} className="rounded-full bg-secondary px-3 py-1 text-[13px] font-medium">{o.name}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-[15px] text-muted-foreground/50">Не выбрано</p>
        )}
      </div>
      <div className="mt-6 rounded-2xl bg-primary p-5 text-primary-foreground">
        <p className="text-sm text-white/55">Предварительно</p>
        {estimate ? (
          <AnimatedPrice value={estimate.total} className="mt-1 block text-3xl font-semibold tracking-tight" />
        ) : (
          <p className="mt-1 text-lg font-medium text-white/60">Выберите тип дома и технологию</p>
        )}
      </div>
    </>
  );
}

export function DesktopSummary(props: SummaryProps) {
  return (
    <aside className="hidden lg:block" aria-label="Параметры вашего дома">
      <div className="sticky top-24 rounded-3xl border border-border bg-white p-7">
        <p className="eyebrow">Ваш дом</p>
        <div className="mt-6">
          <SummaryBody {...props} />
        </div>
      </div>
    </aside>
  );
}

export function MobileSummaryBar({ action, ...props }: SummaryProps & { action: React.ReactNode }) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden">
      <div className="flex items-center gap-3 px-4 py-3">
        <Sheet>
          <SheetTrigger asChild>
            <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left cursor-pointer" aria-label="Показать параметры дома">
              <span className="min-w-0">
                <span className="block text-[11px] text-muted-foreground">Предварительно · {props.state.area} м²</span>
                {props.estimate ? (
                  <AnimatedPrice value={props.estimate.total} className="block truncate text-lg font-semibold" />
                ) : (
                  <span className="block text-sm font-medium text-muted-foreground">Заполните параметры</span>
                )}
              </span>
              <ChevronUp className="size-4 shrink-0 text-muted-foreground" />
            </button>
          </SheetTrigger>
          <SheetContent side="bottom" className="overflow-y-auto px-5 pt-6 pb-8">
            <SheetTitle>Ваш дом</SheetTitle>
            <SheetDescription className="sr-only">Выбранные параметры и предварительная стоимость</SheetDescription>
            <SummaryBody {...props} />
          </SheetContent>
        </Sheet>
        {action}
      </div>
    </div>
  );
}
