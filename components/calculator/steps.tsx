"use client";

import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { CONSTRUCTION_PERIODS, type ConstructionPeriodCode } from "@/lib/constants";
import { calculateEstimate } from "@/lib/pricing/engine";
import type { PricingConfig } from "@/lib/pricing/types";
import { cn, formatNumber, formatPrice } from "@/lib/utils";
import { ChoiceCard } from "./choice-card";
import { HouseIcon } from "./house-icon";
import type { CalculatorState } from "./types";

interface StepProps {
  state: CalculatorState;
  config: PricingConfig;
  update: (patch: Partial<CalculatorState>) => void;
}

function millions(value: number) {
  return `≈ ${(value / 1_000_000).toFixed(1).replace(".", ",")} млн ₽`;
}

export function StepHouseType({ state, config, update }: StepProps) {
  return (
    <div role="radiogroup" aria-label="Тип дома" className="grid gap-4 sm:grid-cols-3">
      {config.houseTypes.map((h) => (
        <ChoiceCard
          key={h.code}
          selected={state.houseType === h.code}
          onSelect={() => update({ houseType: h.code })}
          title={h.name}
          description={h.description}
          visual={<HouseIcon type={h.code} className="h-20 w-full" />}
        />
      ))}
    </div>
  );
}

export function StepArea({ state, config, update }: StepProps) {
  const { areaMin, areaMax } = config.params;
  const commit = (input: HTMLInputElement) => {
    const n = Math.round(Number(input.value.replace(",", ".")));
    if (!Number.isFinite(n) || n <= 0) {
      input.value = String(state.area);
      return;
    }
    const next = Math.min(Math.max(n, areaMin), areaMax);
    input.value = String(next);
    update({ area: next });
  };
  const presets = [80, 120, 150, 200, 250].filter((p) => p >= areaMin && p <= areaMax);

  return (
    <div className="rounded-3xl border border-border bg-white p-6 sm:p-10">
      <div className="flex items-end justify-between gap-6">
        <p className="text-6xl font-semibold tracking-tight tabular sm:text-8xl" aria-hidden>
          {state.area}
          <span className="ml-2 text-2xl text-muted-foreground sm:text-4xl">м²</span>
        </p>
        <label className="flex flex-col gap-2 text-sm text-muted-foreground">
          Точное значение
          <span className="relative">
            <Input
              type="number"
              inputMode="numeric"
              min={areaMin}
              max={areaMax}
              key={state.area}
              defaultValue={state.area}
              onBlur={(e) => commit(e.currentTarget)}
              onKeyDown={(e) => e.key === "Enter" && commit(e.currentTarget)}
              className="w-32 pr-10 text-lg font-semibold tabular"
              aria-label="Площадь дома в квадратных метрах"
            />
            <span className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 text-sm">м²</span>
          </span>
        </label>
      </div>
      <Slider
        className="mt-10"
        min={areaMin}
        max={areaMax}
        step={1}
        value={[state.area]}
        onValueChange={([v]) => update({ area: v })}
        aria-label="Площадь дома"
      />
      <div className="mt-1 flex justify-between text-xs text-muted-foreground tabular">
        <span>{areaMin} м²</span>
        <span>{areaMax} м²</span>
      </div>
      <div className="mt-8 flex flex-wrap gap-2">
        {presets.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => update({ area: p })}
            className={cn(
              "h-10 rounded-full border px-4 text-sm font-medium transition cursor-pointer",
              state.area === p ? "border-primary bg-primary text-primary-foreground" : "border-foreground/12 hover:border-foreground/35",
            )}
          >
            {p} м²
          </button>
        ))}
      </div>
    </div>
  );
}

export function StepBedrooms({ state, update }: StepProps) {
  const choices = [2, 3, 4, 5];
  return (
    <div role="radiogroup" aria-label="Количество спален" className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {choices.map((n) => (
        <ChoiceCard
          key={n}
          selected={state.bedrooms === n}
          onSelect={() => update({ bedrooms: n })}
          title={n === 5 ? "5 и более" : `${n} спальни`}
          visual={<span className="block text-6xl font-semibold tracking-tight tabular">{n === 5 ? "5+" : n}</span>}
        />
      ))}
    </div>
  );
}

export function StepTechnology({ state, config, update }: StepProps) {
  return (
    <div role="radiogroup" aria-label="Технология" className="grid gap-4 sm:grid-cols-2">
      {config.technologies.map((t) => (
        <ChoiceCard
          key={t.slug}
          selected={state.technology === t.slug}
          onSelect={() => update({ technology: t.slug })}
          title={t.name}
          description={t.shortDescription}
          aside={`${formatNumber(t.pricePerM2)} ₽ / м² под ключ`}
        />
      ))}
    </div>
  );
}

export function StepPackage({ state, config, update }: StepProps) {
  return (
    <div role="radiogroup" aria-label="Комплектация" className="grid gap-4 sm:grid-cols-2">
      {config.packages.map((p) => {
        const estimate =
          state.houseType && state.technology
            ? calculateEstimate(config, { houseType: state.houseType, area: state.area, bedrooms: state.bedrooms, technology: state.technology, package: p.code, options: [] }).total
            : null;
        return (
          <ChoiceCard
            key={p.code}
            selected={state.package === p.code}
            onSelect={() => update({ package: p.code })}
            title={p.name}
            description={p.description}
            aside={estimate ? millions(estimate) : undefined}
          >
            <ul className="mt-4 space-y-1.5 text-[13px] text-foreground/75">
              {p.includes.map((inc) => (
                <li key={inc} className="flex gap-2">
                  <span className="mt-1.5 size-1 shrink-0 rounded-full bg-accent" />
                  {inc}
                </li>
              ))}
            </ul>
          </ChoiceCard>
        );
      })}
    </div>
  );
}

export function StepOptions({ state, config, update }: StepProps) {
  const toggle = (code: string) =>
    update({ options: state.options.includes(code) ? state.options.filter((c) => c !== code) : [...state.options, code] });
  return (
    <div role="group" aria-label="Дополнительные опции" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {config.options.map((o) => (
        <ChoiceCard
          key={o.code}
          role="checkbox"
          selected={state.options.includes(o.code)}
          onSelect={() => toggle(o.code)}
          title={o.name}
          description={o.description}
          aside={o.pricingType === "PER_M2" ? `+${formatPrice(o.price * state.area)} · ${formatNumber(o.price)} ₽/м²` : `+${formatPrice(o.price)}`}
          className="p-5 sm:p-5"
        />
      ))}
    </div>
  );
}

export function StepPeriod({ state, update }: StepProps) {
  return (
    <div role="radiogroup" aria-label="Сроки строительства" className="grid gap-4 sm:grid-cols-2">
      {CONSTRUCTION_PERIODS.map((p) => (
        <ChoiceCard
          key={p.code}
          selected={state.period === p.code}
          onSelect={() => update({ period: p.code as ConstructionPeriodCode })}
          title={p.label}
          description={p.hint}
        />
      ))}
    </div>
  );
}
