import "server-only";
import { prisma } from "@/lib/db";
import { getPricingConfig } from "@/lib/pricing/config";
import { calculateEstimate, PricingError } from "@/lib/pricing/engine";
import type { CalculatorInput } from "@/lib/validation/lead";

/** Серверный (доверенный) расчёт: цены берутся только из БД, данные клиента — только параметры. */
export async function computeEstimate(input: CalculatorInput) {
  const config = await getPricingConfig();
  const validOptions = new Set(config.options.map((o) => o.code));
  const options = [...new Set(input.options)].filter((o) => validOptions.has(o));
  const estimate = calculateEstimate(config, { ...input, options });
  const project = input.projectSlug
    ? await prisma.project.findFirst({ where: { slug: input.projectSlug, status: "PUBLISHED" }, select: { id: true, title: true } })
    : null;
  const area = Math.min(Math.max(input.area, config.params.areaMin), config.params.areaMax);
  return { estimate, project, options, area };
}

export { PricingError };
