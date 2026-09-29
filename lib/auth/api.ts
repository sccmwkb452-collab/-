import "server-only";
import { getCurrentAdmin } from "./session";
import { isSameOrigin, jsonError } from "@/lib/security/request";

/** Проверка для admin API: авторизация + same-origin для мутирующих запросов. */
export async function guardAdminApi(req: Request, { mutation = true } = {}) {
  if (mutation && !isSameOrigin(req)) return { admin: null, response: jsonError("Запрос отклонён", 403) };
  const admin = await getCurrentAdmin();
  if (!admin) return { admin: null, response: jsonError("Требуется авторизация", 401) };
  return { admin, response: null };
}
