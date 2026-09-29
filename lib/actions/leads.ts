"use server";

import type { LeadStatus } from "@prisma/client";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { assertAdmin } from "@/lib/auth/session";
import { prisma } from "@/lib/db";
import { handleActionError, type ActionResult } from "./result";

const statusSchema = z.enum(["NEW", "IN_PROGRESS", "CONTACTED", "CALCULATION", "CONTRACT", "COMPLETED", "REJECTED"]);
const idSchema = z.string().min(1).max(40);

export async function updateLeadStatusAction(leadId: string, status: LeadStatus): Promise<ActionResult> {
  try {
    const admin = await assertAdmin();
    const id = idSchema.parse(leadId);
    const next = statusSchema.parse(status);
    const lead = await prisma.lead.findUnique({ where: { id }, select: { status: true } });
    if (!lead) return { ok: false, error: "Заявка не найдена" };
    if (lead.status === next) return { ok: true };
    await prisma.$transaction([
      prisma.lead.update({ where: { id }, data: { status: next } }),
      prisma.leadEvent.create({ data: { leadId: id, type: "STATUS_CHANGED", fromStatus: lead.status, toStatus: next, adminId: admin.id } }),
    ]);
    revalidatePath("/admin/leads");
    revalidatePath(`/admin/leads/${id}`);
    return { ok: true, message: "Статус обновлён" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function addLeadCommentAction(leadId: string, text: string): Promise<ActionResult> {
  try {
    const admin = await assertAdmin();
    const id = idSchema.parse(leadId);
    const message = z.string().trim().min(1, "Введите комментарий").max(2000).safeParse(text);
    if (!message.success) return { ok: false, error: message.error.issues[0]?.message ?? "Некорректный комментарий" };
    await prisma.$transaction([
      prisma.leadEvent.create({ data: { leadId: id, type: "COMMENT", message: message.data, adminId: admin.id } }),
      prisma.lead.update({ where: { id }, data: { managerComment: message.data } }),
    ]);
    revalidatePath(`/admin/leads/${id}`);
    return { ok: true, message: "Комментарий добавлен" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function deleteLeadAction(leadId: string): Promise<ActionResult> {
  try {
    await assertAdmin();
    await prisma.lead.delete({ where: { id: idSchema.parse(leadId) } });
    revalidatePath("/admin/leads");
    return { ok: true, message: "Заявка удалена" };
  } catch (error) {
    return handleActionError(error);
  }
}
