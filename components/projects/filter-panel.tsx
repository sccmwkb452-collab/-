"use client";

import { Slider } from "@/components/ui/slider";
import { cn, formatNumber } from "@/lib/utils";
import { AREA_BUCKETS, BEDROOM_OPTIONS, FEATURE_OPTIONS, FLOOR_OPTIONS, type CatalogFilters } from "./filters";

interface FilterPanelProps {
  filters: CatalogFilters;
  priceBounds: [number, number];
  onChange: (next: CatalogFilters) => void;
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "h-10 rounded-full border px-4 text-sm font-medium transition-all duration-300 cursor-pointer",
        active ? "border-primary bg-primary text-primary-foreground" : "border-foreground/12 bg-white hover:border-foreground/35",
      )}
    >
      {children}
    </button>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="border-b border-border py-6 first:pt-0 last:border-0">
      <legend className="mb-4 text-xs font-semibold tracking-[0.14em] text-muted-foreground uppercase">{title}</legend>
      <div className="flex flex-wrap gap-2">{children}</div>
    </fieldset>
  );
}

export function FilterPanel({ filters, priceBounds, onChange }: FilterPanelProps) {
  const toggle = (key: "area" | "floors" | "bedrooms" | "features", value: string) => {
    const current = filters[key];
    onChange({ ...filters, [key]: current.includes(value) ? current.filter((v) => v !== value) : [...current, value] });
  };
  const [minBound, maxBound] = priceBounds;
  const priceValue: [number, number] = [filters.priceMin ?? minBound, filters.priceMax ?? maxBound];
  const step = 100000;

  return (
    <div>
      <Group title="Площадь">
        {AREA_BUCKETS.map((o) => (
          <Chip key={o.value} active={filters.area.includes(o.value)} onClick={() => toggle("area", o.value)}>{o.label}</Chip>
        ))}
      </Group>
      <Group title="Этажность">
        {FLOOR_OPTIONS.map((o) => (
          <Chip key={o.value} active={filters.floors.includes(o.value)} onClick={() => toggle("floors", o.value)}>{o.label}</Chip>
        ))}
      </Group>
      <Group title="Спальни">
        {BEDROOM_OPTIONS.map((o) => (
          <Chip key={o.value} active={filters.bedrooms.includes(o.value)} onClick={() => toggle("bedrooms", o.value)}>{o.label}</Chip>
        ))}
      </Group>
      {maxBound > minBound && (
        <fieldset className="border-b border-border py-6">
          <legend className="mb-4 text-xs font-semibold tracking-[0.14em] text-muted-foreground uppercase">Цена, ₽</legend>
          <div className="flex justify-between text-sm font-medium tabular">
            <span>от {formatNumber(priceValue[0])}</span>
            <span>до {formatNumber(priceValue[1])}</span>
          </div>
          <Slider
            className="mt-2"
            min={minBound}
            max={maxBound}
            step={step}
            value={priceValue}
            minStepsBetweenThumbs={1}
            aria-label="Диапазон цены"
            onValueChange={([min, max]) =>
              onChange({ ...filters, priceMin: min <= minBound ? null : min, priceMax: max >= maxBound ? null : max })
            }
          />
        </fieldset>
      )}
      <Group title="Дополнительно">
        {FEATURE_OPTIONS.map((o) => (
          <Chip key={o.value} active={filters.features.includes(o.value)} onClick={() => toggle("features", o.value)}>{o.label}</Chip>
        ))}
      </Group>
    </div>
  );
}
