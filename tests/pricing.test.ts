import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { calculateEstimate, PricingError } from "../lib/pricing/engine";
import type { PricingConfig } from "../lib/pricing/types";

const config: PricingConfig = {
  houseTypes: [
    { code: "one-story", name: "Одноэтажный", description: "", floors: 1, multiplier: 1.08 },
    { code: "two-story", name: "Двухэтажный", description: "", floors: 2, multiplier: 1 },
  ],
  technologies: [{ slug: "gazobeton", name: "Газобетон", shortDescription: "", pricePerM2: 65000 }],
  packages: [
    { code: "box", name: "Коробка", description: "", includes: [], multiplier: 0.65 },
    { code: "turnkey", name: "Под ключ", description: "", includes: [], multiplier: 1 },
  ],
  options: [
    { code: "terrace", name: "Терраса", description: "", pricingType: "FIXED", price: 350000 },
    { code: "floor", name: "Тёплый пол", description: "", pricingType: "PER_M2", price: 1800 },
  ],
  params: { areaMin: 50, areaMax: 400, bedroomBaseCount: 3, bedroomSurcharge: 150000, roundingStep: 10000, spreadPercent: 7 },
};

describe("calculateEstimate", () => {
  it("считает базовую стоимость под ключ", () => {
    const r = calculateEstimate(config, { houseType: "two-story", area: 156, bedrooms: 3, technology: "gazobeton", package: "turnkey", options: [] });
    assert.equal(r.base, 10_140_000);
    assert.equal(r.total, 10_140_000);
    assert.equal(r.packageAdjustment, 0);
  });

  it("применяет коэффициенты этажности и комплектации", () => {
    const r = calculateEstimate(config, { houseType: "one-story", area: 100, bedrooms: 3, technology: "gazobeton", package: "box", options: [] });
    assert.equal(r.base, 6_500_000);
    assert.equal(r.houseTypeAdjustment, 520_000);
    assert.equal(r.packageAdjustment, Math.round(7_020_000 * -0.35));
    assert.equal(r.total, 4_560_000);
  });

  it("добавляет опции (фиксированные и за м²) и надбавку за спальни", () => {
    const r = calculateEstimate(config, { houseType: "two-story", area: 150, bedrooms: 5, technology: "gazobeton", package: "turnkey", options: ["terrace", "floor", "unknown"] });
    assert.equal(r.bedroomsAdjustment, 300_000);
    assert.equal(r.optionsTotal, 350_000 + 270_000);
    assert.equal(r.options.length, 2);
    assert.equal(r.total, 9_750_000 + 300_000 + 620_000);
  });

  it("ограничивает площадь настройками и округляет результат", () => {
    const r = calculateEstimate(config, { houseType: "two-story", area: 10, bedrooms: 2, technology: "gazobeton", package: "turnkey", options: [] });
    assert.equal(r.base, 50 * 65000);
    assert.equal(r.total % 10000, 0);
    assert.ok(r.rangeMin < r.total && r.rangeMax > r.total);
  });

  it("отклоняет неизвестные параметры", () => {
    assert.throws(() => calculateEstimate(config, { houseType: "x", area: 100, bedrooms: 3, technology: "gazobeton", package: "turnkey", options: [] }), PricingError);
    assert.throws(() => calculateEstimate(config, { houseType: "two-story", area: 100, bedrooms: 3, technology: "x", package: "turnkey", options: [] }), PricingError);
  });
});
