"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { getDummyHash, verifyPassword } from "@/lib/auth/password";
import { createSession, destroySession } from "@/lib/auth/session";
import { prisma } from "@/lib/db";
import { rateLimit } from "@/lib/security/rate-limit";
import { loginSchema } from "@/lib/validation/admin";

export interface LoginState {
  error?: string;
  email?: string;
}


export async function loginAction(_prev: LoginState, formData: FormData): Promise<LoginState> {
  const parsed = loginSchema.safeParse({ email: formData.get("email"), password: formData.get("password") });
  const email = String(formData.get("email") ?? "").slice(0, 120);
  if (!parsed.success) return { error: "Введите email и пароль", email };

  const h = await headers();
  const ip = h.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
  const byIp = rateLimit(`login:ip:${ip}`, 10, 15 * 60_000);
  const byEmail = rateLimit(`login:email:${parsed.data.email}`, 5, 15 * 60_000);
  if (!byIp.ok || !byEmail.ok) return { error: "Слишком много попыток. Попробуйте через 15 минут.", email };

  const admin = await prisma.admin.findUnique({ where: { email: parsed.data.email } });
  const valid = await verifyPassword(parsed.data.password, admin?.passwordHash ?? (await getDummyHash()));
  if (!admin || !valid) return { error: "Неверный email или пароль", email };

  await prisma.admin.update({ where: { id: admin.id }, data: { lastLoginAt: new Date() } });
  await prisma.adminSession.deleteMany({ where: { adminId: admin.id, expiresAt: { lt: new Date() } } });
  await createSession(admin.id);
  redirect("/admin");
}

export async function logoutAction() {
  await destroySession();
  redirect("/admin/login");
}
