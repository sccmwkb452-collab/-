import type { ApiErrorBody } from "@starshop/shared";
import { isTelegram, tg } from "./telegram";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

const BASE = "/api/v1";
let devInitData: Promise<string> | null = null;

/** Whether requests can be signed: inside Telegram, or with the local dev helper. */
export const canAuthenticate = isTelegram || import.meta.env.VITE_DEV_AUTH === "1";

/** Signed launch data. Outside Telegram (local development only) the backend
 * can sign test data when DEV_AUTH_ENABLED=true and VITE_DEV_AUTH=1. */
async function initData(): Promise<string> {
  if (isTelegram && tg) return tg.initData;
  if (import.meta.env.VITE_DEV_AUTH === "1") {
    devInitData ??= fetch(`${BASE}/dev/init-data?telegram_id=${import.meta.env.VITE_DEV_TELEGRAM_ID ?? 100001}`)
      .then((r) => (r.ok ? r.json() : { init_data: "" }))
      .then((d: { init_data: string }) => d.init_data)
      .catch(() => "");
    return devInitData;
  }
  return "";
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; headers?: Record<string, string>; timeoutMs?: number; auth?: boolean } = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 20000);
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.auth !== false) {
    const data = await initData();
    if (data) headers.Authorization = `tma ${data}`;
  }
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      method: options.method ?? "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === "AbortError";
    throw new ApiError(0, aborted ? "timeout" : "network", aborted ? "Сервер отвечает слишком долго. Проверьте интернет и попробуйте ещё раз" : "Нет соединения. Проверьте интернет");
  } finally {
    clearTimeout(timer);
  }
  if (response.status === 204) return undefined as T;
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const err = (payload as ApiErrorBody | null)?.error;
    throw new ApiError(response.status, err?.code ?? "http_error", err?.message ?? "Что-то пошло не так. Попробуйте ещё раз", err?.details);
  }
  return payload as T;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return "Что-то пошло не так. Попробуйте ещё раз";
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID().replace(/-/g, "");
  return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
}
