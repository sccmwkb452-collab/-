import { z } from "zod";
import { UnauthorizedError } from "@/lib/auth/session";

export type ActionResult<T = undefined> =
  | { ok: true; message?: string; data?: T }
  | { ok: false; error: string; fieldErrors?: Record<string, string[] | undefined> };

export function validationError(error: z.ZodError): ActionResult<never> {
  return { ok: false, error: "Проверьте правильность заполнения", fieldErrors: z.flattenError(error).fieldErrors as Record<string, string[] | undefined> };
}

export function handleActionError(error: unknown): ActionResult<never> {
  if (error instanceof UnauthorizedError) return { ok: false, error: "Сессия истекла. Войдите снова." };
  console.error("[admin action]", error);
  return { ok: false, error: "Не удалось сохранить изменения" };
}
