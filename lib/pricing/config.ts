import "server-only";
import { cache } from "react";
import { prisma } from "@/lib/db";
import type { PricingConfig, PricingParams } from "./types";

export const PRICE_PARAM_KEYS = {
  areaMin: "area_min",
  areaMax: "area_max",
  bedroomBaseCount: "bedroom_base_count",
  bedroomSurcharge: "bedroom_surcharge",
  roundingStep: "rounding_step",
  spreadPercent: "estimate_spread_percent",
} as const satisfies Record<keyof PricingParams, string>;

const DEFAULT_PARAMS: PricingParams = {
  areaMin: 50,
  areaMax: 400,
  bedroomBaseCount: 3,
  bedroomSurcharge: 150000,
  roundingStep: 10000,
  spreadPercent: 7,
};

export const getPricingConfig = cache(async (): Promise<PricingConfig> => {
  const [houseTypes, technologies, packages, options, settings] = await Promise.all([
    prisma.houseType.findMany({ where: { active: true }, orderBy: { sortOrder: "asc" } }),
    prisma.technology.findMany({ where: { active: true }, orderBy: { sortOrder: "asc" } }),
    prisma.completionPackage.findMany({ where: { active: true }, orderBy: { sortOrder: "asc" } }),
    prisma.option.findMany({ where: { active: true }, orderBy: { sortOrder: "asc" } }),
    prisma.priceSetting.findMany(),
  ]);

  const byKey = new Map(settings.map((s) => [s.key, s.value]));
  const get = (k: keyof PricingParams) => byKey.get(PRICE_PARAM_KEYS[k]) ?? DEFAULT_PARAMS[k];
  const params: PricingParams = {
    areaMin: get("areaMin"),
    areaMax: get("areaMax"),
    bedroomBaseCount: get("bedroomBaseCount"),
    bedroomSurcharge: get("bedroomSurcharge"),
    roundingStep: get("roundingStep"),
    spreadPercent: get("spreadPercent"),
  };

  return {
    houseTypes: houseTypes.map((h) => ({ code: h.code, name: h.name, description: h.description, floors: h.floors, multiplier: h.multiplier })),
    technologies: technologies.map((t) => ({ slug: t.slug, name: t.name, shortDescription: t.shortDescription, pricePerM2: t.pricePerM2 })),
    packages: packages.map((p) => ({ code: p.code, name: p.name, description: p.description, includes: p.includes, multiplier: p.multiplier })),
    options: options.map((o) => ({ code: o.code, name: o.name, description: o.description, pricingType: o.pricingType, price: o.price })),
    params,
  };
});
