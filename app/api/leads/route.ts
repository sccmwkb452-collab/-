import type { Prisma } from "@prisma/client";
import { after } from "next/server";
import { z } from "zod";
import { budgetLabel, LEAD_SOURCE_LABELS, periodLabel } from "@/lib/constants";
import { prisma } from "@/lib/db";
import { computeEstimate, PricingError } from "@/lib/leads/calculate";
import { notifyNewLead } from "@/lib/notifications";
import { rateLimit } from "@/lib/security/rate-limit";
import { getClientIp, isSameOrigin, jsonError } from "@/lib/security/request";
import { normalizePhone } from "@/lib/utils";
import { leadRequestSchema } from "@/lib/validation/lead";

export async function POST(req: Request) {
  if (!isSameOrigin(req)) return jsonError("Запрос отклонён", 403);
  const ip = getClientIp(req);
  const minute = rateLimit(`lead:m:${ip}`, 5, 60_000);
  const hour = rateLimit(`lead:h:${ip}`, 20, 60 * 60_000);
  if (!minute.ok || !hour.ok) return jsonError("Слишком много заявок. Попробуйте позже.", 429);

  const body = await req.json().catch(() => null);
  const parsed = leadRequestSchema.safeParse(body);
  if (!parsed.success) {
    const flat = z.flattenError(parsed.error);
    const contactIssues = parsed.error.issues.filter((i) => i.path[0] === "contact");
    const fieldErrors: Record<string, string[]> = {};
    for (const issue of contactIssues) {
      const key = String(issue.path[1] ?? "form");
      (fieldErrors[key] ??= []).push(issue.message);
    }
    return jsonError("Проверьте правильность заполнения формы", 400, { fieldErrors: { ...flat.fieldErrors, ...fieldErrors } });
  }

  const data = parsed.data;
  const { contact } = data;

  // Honeypot: боты заполняют скрытое поле — отвечаем успехом, ничего не сохраняя.
  if (contact.website) return Response.json({ ok: true, id: "ok" });

  const base = {
    name: contact.name,
    phone: normalizePhone(contact.phone),
    email: contact.email ?? null,
    telegram: contact.telegram ?? null,
    comment: contact.comment ?? null,
    region: contact.region ?? null,
    budget: contact.budget ?? null,
    consentAt: new Date(),
    ip,
    userAgent: req.headers.get("user-agent")?.slice(0, 300) ?? null,
  };

  try {
    let leadData: Prisma.LeadUncheckedCreateInput;
    let projectTitle: string | null = null;

    if (data.source === "CALCULATOR") {
      const { estimate, project, options, area } = await computeEstimate(data.calculator);
      projectTitle = project?.title ?? null;
      const input = { ...data.calculator, area, options };

      let calculationId: string | null = null;
      if (data.calculationId) {
        const existing = await prisma.calculation.findUnique({ where: { id: data.calculationId }, include: { lead: { select: { id: true } } } });
        if (existing && !existing.lead) calculationId = existing.id;
      }
      if (!calculationId) {
        const calc = await prisma.calculation.create({
          data: { input, breakdown: estimate, estimatedPrice: estimate.total, projectId: project?.id ?? null },
        });
        calculationId = calc.id;
      }

      leadData = {
        ...base,
        source: "CALCULATOR",
        houseType: estimate.labels.houseType,
        area,
        bedrooms: data.calculator.bedrooms,
        technology: estimate.labels.technology,
        package: estimate.labels.package,
        options: estimate.options.map((o) => o.label),
        estimatedPrice: estimate.total,
        constructionPeriod: data.calculator.period,
        breakdown: estimate,
        projectId: project?.id ?? null,
        calculationId,
      };
    } else {
      const project = data.projectSlug
        ? await prisma.project.findFirst({
            where: { slug: data.projectSlug, status: "PUBLISHED" },
            include: { houseType: true, technology: true },
          })
        : null;
      projectTitle = project?.title ?? null;
      leadData = {
        ...base,
        source: data.source,
        projectId: project?.id ?? null,
        houseType: project?.houseType.name ?? null,
        area: project?.area ?? null,
        bedrooms: project?.bedrooms ?? null,
        technology: project?.technology?.name ?? null,
        estimatedPrice: project?.priceFrom ?? null,
        options: [],
      };
    }

    const lead = await prisma.lead.create({
      data: { ...leadData, events: { create: { type: "CREATED", message: `Заявка создана: ${LEAD_SOURCE_LABELS[leadData.source ?? "CALCULATOR"]}` } } },
    });

    after(() =>
      notifyNewLead({
        id: lead.id,
        name: lead.name,
        phone: lead.phone,
        email: lead.email,
        telegram: lead.telegram,
        comment: lead.comment,
        region: lead.region,
        project: projectTitle,
        houseType: lead.houseType,
        area: lead.area,
        bedrooms: lead.bedrooms,
        technology: lead.technology,
        package: lead.package,
        options: lead.options,
        estimatedPrice: lead.estimatedPrice,
        period: lead.constructionPeriod ? periodLabel(lead.constructionPeriod) : null,
        budget: lead.budget ? budgetLabel(lead.budget) : null,
        source: LEAD_SOURCE_LABELS[lead.source],
      }),
    );

    return Response.json({ ok: true, id: lead.id });
  } catch (error) {
    if (error instanceof PricingError) return jsonError(error.message, 400);
    console.error("[leads]", error);
    return jsonError("Не удалось сохранить заявку. Попробуйте ещё раз или позвоните нам.", 500);
  }
}
