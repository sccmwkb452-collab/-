"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { assertAdmin } from "@/lib/auth/session";
import { prisma } from "@/lib/db";
import { houseTypePriceSchema, optionSchema, packagePriceSchema, priceParamSchema, technologyPriceSchema } from "@/lib/validation/admin";
import { handleActionError, type ActionResult } from "./result";

function revalidatePricing() {
  revalidatePath("/admin/pricing");
  revalidatePath("/calculator");
  revalidatePath("/technology");
  revalidatePath("/");
}

function firstIssue(error: z.ZodError) {
  const issue = error.issues[0];
  return issue ? `${issue.path.join(".")}: ${issue.message}` : "Некорректные данные";
}

export async function saveTechnologiesAction(input: unknown): Promise<ActionResult> {
  try {
    await assertAdmin();
    const parsed = z.array(technologyPriceSchema).max(20).safeParse(input);
    if (!parsed.success) return { ok: false, error: firstIssue(parsed.error) };
    await prisma.$transaction(parsed.data.map(({ id, ...data }) => prisma.technology.update({ where: { id }, data })));
    revalidatePricing();
    return { ok: true, message: "Цены технологий сохранены" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function savePackagesAction(input: unknown): Promise<ActionResult> {
  try {
    await assertAdmin();
    const parsed = z.array(packagePriceSchema).max(20).safeParse(input);
    if (!parsed.success) return { ok: false, error: firstIssue(parsed.error) };
    await prisma.$transaction(parsed.data.map(({ id, ...data }) => prisma.completionPackage.update({ where: { id }, data })));
    revalidatePricing();
    return { ok: true, message: "Комплектации сохранены" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function saveHouseTypesAction(input: unknown): Promise<ActionResult> {
  try {
    await assertAdmin();
    const parsed = z.array(houseTypePriceSchema).max(20).safeParse(input);
    if (!parsed.success) return { ok: false, error: firstIssue(parsed.error) };
    await prisma.$transaction(parsed.data.map(({ id, ...data }) => prisma.houseType.update({ where: { id }, data })));
    revalidatePricing();
    return { ok: true, message: "Коэффициенты этажности сохранены" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function saveOptionAction(input: unknown): Promise<ActionResult<{ id: string }>> {
  try {
    await assertAdmin();
    const parsed = optionSchema.safeParse(input);
    if (!parsed.success) return { ok: false, error: firstIssue(parsed.error) };
    const { id, ...data } = parsed.data;
    const conflict = await prisma.option.findFirst({ where: { code: data.code, ...(id ? { NOT: { id } } : {}) }, select: { id: true } });
    if (conflict) return { ok: false, error: "Опция с таким кодом уже существует" };
    const saved = id ? await prisma.option.update({ where: { id }, data }) : await prisma.option.create({ data });
    revalidatePricing();
    return { ok: true, message: id ? "Опция сохранена" : "Опция добавлена", data: { id: saved.id } };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function deleteOptionAction(id: string): Promise<ActionResult> {
  try {
    await assertAdmin();
    await prisma.option.delete({ where: { id: z.string().min(1).parse(id) } });
    revalidatePricing();
    return { ok: true, message: "Опция удалена" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function savePriceParamsAction(input: unknown): Promise<ActionResult> {
  try {
    await assertAdmin();
    const parsed = z.array(priceParamSchema).max(30).safeParse(input);
    if (!parsed.success) return { ok: false, error: firstIssue(parsed.error) };
    const map = new Map(parsed.data.map((p) => [p.key, p.value]));
    const min = map.get("area_min");
    const max = map.get("area_max");
    if (min !== undefined && max !== undefined && min >= max) return { ok: false, error: "Минимальная площадь должна быть меньше максимальной" };
    const existing = await prisma.priceSetting.findMany({ select: { key: true } });
    const known = new Set(existing.map((e) => e.key));
    await prisma.$transaction(parsed.data.filter((p) => known.has(p.key)).map((p) => prisma.priceSetting.update({ where: { key: p.key }, data: { value: p.value } })));
    revalidatePricing();
    return { ok: true, message: "Параметры расчёта сохранены" };
  } catch (error) {
    return handleActionError(error);
  }
}
