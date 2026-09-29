import { prisma } from "@/lib/db";
import { computeEstimate, PricingError } from "@/lib/leads/calculate";
import { rateLimit } from "@/lib/security/rate-limit";
import { getClientIp, isSameOrigin, jsonError } from "@/lib/security/request";
import { z } from "zod";
import { calculatorInputSchema } from "@/lib/validation/lead";

export async function POST(req: Request) {
  if (!isSameOrigin(req)) return jsonError("Запрос отклонён", 403);
  const limit = rateLimit(`calc:${getClientIp(req)}`, 30, 60_000);
  if (!limit.ok) return jsonError("Слишком много запросов", 429, { retryAfter: limit.retryAfter });

  const body = await req.json().catch(() => null);
  const parsed = calculatorInputSchema.safeParse(body);
  if (!parsed.success) return jsonError("Проверьте параметры расчёта", 400, { fieldErrors: z.flattenError(parsed.error).fieldErrors });

  try {
    const { estimate, project, options, area } = await computeEstimate(parsed.data);
    const calc = await prisma.calculation.create({
      data: {
        input: { ...parsed.data, area, options },
        breakdown: estimate,
        estimatedPrice: estimate.total,
        projectId: project?.id ?? null,
      },
      select: { id: true },
    });
    return Response.json({ ok: true, id: calc.id, estimate });
  } catch (error) {
    if (error instanceof PricingError) return jsonError(error.message, 400);
    console.error("[calculations]", error);
    return jsonError("Не удалось выполнить расчёт", 500);
  }
}
