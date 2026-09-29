"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { hashPassword, verifyPassword } from "@/lib/auth/password";
import { assertAdmin } from "@/lib/auth/session";
import { prisma } from "@/lib/db";
import { adminCreateSchema, faqSchema, passwordSchema, settingsSchema } from "@/lib/validation/admin";
import { handleActionError, validationError, type ActionResult } from "./result";

export async function saveSettingsAction(input: unknown): Promise<ActionResult> {
  try {
    await assertAdmin();
    const parsed = settingsSchema.safeParse(input);
    if (!parsed.success) return validationError(parsed.error);
    await prisma.siteSetting.upsert({ where: { id: 1 }, update: parsed.data, create: { id: 1, ...parsed.data } });
    revalidatePath("/", "layout");
    return { ok: true, message: "Настройки сохранены" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function removeLogoAction(): Promise<ActionResult> {
  try {
    await assertAdmin();
    await prisma.siteSetting.update({ where: { id: 1 }, data: { logoUrl: null } });
    revalidatePath("/", "layout");
    return { ok: true, message: "Логотип удалён" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function changePasswordAction(input: { current: string; next: string }): Promise<ActionResult> {
  try {
    const admin = await assertAdmin();
    const next = passwordSchema.safeParse(input.next);
    if (!next.success) return { ok: false, error: next.error.issues[0]?.message ?? "Слабый пароль", fieldErrors: { next: next.error.issues.map((i) => i.message) } };
    const row = await prisma.admin.findUnique({ where: { id: admin.id } });
    if (!row || !(await verifyPassword(String(input.current ?? ""), row.passwordHash))) {
      return { ok: false, error: "Текущий пароль указан неверно", fieldErrors: { current: ["Неверный пароль"] } };
    }
    await prisma.admin.update({ where: { id: admin.id }, data: { passwordHash: await hashPassword(next.data) } });
    return { ok: true, message: "Пароль изменён" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function createAdminAction(input: unknown): Promise<ActionResult> {
  try {
    await assertAdmin();
    const parsed = adminCreateSchema.safeParse(input);
    if (!parsed.success) return validationError(parsed.error);
    const exists = await prisma.admin.findUnique({ where: { email: parsed.data.email } });
    if (exists) return { ok: false, error: "Администратор с таким email уже есть", fieldErrors: { email: ["Email занят"] } };
    await prisma.admin.create({ data: { name: parsed.data.name, email: parsed.data.email, passwordHash: await hashPassword(parsed.data.password) } });
    revalidatePath("/admin/settings");
    return { ok: true, message: "Администратор добавлен" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function deleteAdminAction(id: string): Promise<ActionResult> {
  try {
    const me = await assertAdmin();
    const target = z.string().min(1).parse(id);
    if (target === me.id) return { ok: false, error: "Нельзя удалить собственную учётную запись" };
    await prisma.admin.delete({ where: { id: target } });
    revalidatePath("/admin/settings");
    return { ok: true, message: "Администратор удалён" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function saveFaqAction(input: unknown): Promise<ActionResult> {
  try {
    await assertAdmin();
    const parsed = faqSchema.safeParse(input);
    if (!parsed.success) return validationError(parsed.error);
    const { id, ...data } = parsed.data;
    if (id) await prisma.faq.update({ where: { id }, data });
    else await prisma.faq.create({ data });
    revalidatePath("/admin/settings");
    revalidatePath("/faq");
    revalidatePath("/");
    return { ok: true, message: id ? "Вопрос сохранён" : "Вопрос добавлен" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function deleteFaqAction(id: string): Promise<ActionResult> {
  try {
    await assertAdmin();
    await prisma.faq.delete({ where: { id: z.string().min(1).parse(id) } });
    revalidatePath("/admin/settings");
    revalidatePath("/faq");
    return { ok: true, message: "Вопрос удалён" };
  } catch (error) {
    return handleActionError(error);
  }
}
