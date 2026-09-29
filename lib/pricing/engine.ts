import type { EstimateInput, EstimateResult, PricingConfig } from "./types";

export class PricingError extends Error {}

function roundTo(value: number, step: number) {
  if (step <= 1) return Math.round(value);
  return Math.round(value / step) * step;
}

/**
 * Расчёт предварительной стоимости строительства.
 *
 * base        = площадь × цена м² выбранной технологии
 * этажность   = base × (коэффициент типа дома − 1)
 * комплектация = (base + этажность) × (коэффициент комплектации − 1)
 * спальни     = (спальни − базовое количество) × надбавка за спальню
 * опции       = Σ фиксированных цен + Σ (цена за м² × площадь)
 * итог        = сумма, округлённая до шага округления
 *
 * Функция чистая: одинаково работает на сервере (итоговый расчёт для заявки)
 * и в браузере (мгновенный пересчёт в конфигураторе) — все цены приходят из БД.
 */
export function calculateEstimate(config: PricingConfig, input: EstimateInput): EstimateResult {
  const houseType = config.houseTypes.find((h) => h.code === input.houseType);
  if (!houseType) throw new PricingError("Неизвестный тип дома");
  const technology = config.technologies.find((t) => t.slug === input.technology);
  if (!technology) throw new PricingError("Неизвестная технология строительства");
  const pack = config.packages.find((p) => p.code === input.package);
  if (!pack) throw new PricingError("Неизвестная комплектация");

  const { params } = config;
  const area = Math.min(Math.max(input.area, params.areaMin), params.areaMax);

  const base = area * technology.pricePerM2;
  const houseTypeAdjustment = base * (houseType.multiplier - 1);
  const structural = base + houseTypeAdjustment;
  const packageAdjustment = structural * (pack.multiplier - 1);
  const bedroomsAdjustment = Math.max(0, input.bedrooms - params.bedroomBaseCount) * params.bedroomSurcharge;

  const selected = new Set(input.options);
  const options = config.options
    .filter((o) => selected.has(o.code))
    .map((o) => ({
      code: o.code,
      label: o.name,
      amount: o.pricingType === "PER_M2" ? o.price * area : o.price,
    }));
  const optionsTotal = options.reduce((sum, o) => sum + o.amount, 0);

  const raw = structural + packageAdjustment + bedroomsAdjustment + optionsTotal;
  const total = roundTo(raw, params.roundingStep);
  const spread = params.spreadPercent / 100;

  return {
    base: Math.round(base),
    houseTypeAdjustment: Math.round(houseTypeAdjustment),
    packageAdjustment: Math.round(packageAdjustment),
    bedroomsAdjustment: Math.round(bedroomsAdjustment),
    optionsTotal: Math.round(optionsTotal),
    options: options.map((o) => ({ ...o, amount: Math.round(o.amount) })),
    total,
    rangeMin: roundTo(total * (1 - spread), params.roundingStep),
    rangeMax: roundTo(total * (1 + spread), params.roundingStep),
    labels: { houseType: houseType.name, technology: technology.name, package: pack.name },
  };
}
