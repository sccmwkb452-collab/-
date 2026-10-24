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
const DEMO_KEY = "starshop.demo_key";
let devInitData: Promise<string> | null = null;
let demoKey: string | null = null;

/** A public DEMO site opened in a regular browser (PUBLIC_DEMO=true on the server). */
const publicDemo = !isTelegram && import.meta.env.VITE_PUBLIC_DEMO === "1";

/** Whether requests can be signed: inside Telegram, as a demo visitor, or with the local dev helper. */
export const canAuthenticate = isTelegram || publicDemo || import.meta.env.VITE_DEV_AUTH === "1";

/** The anonymous identity of this browser on a public DEMO site: a random key
 * kept in localStorage (or for this page only when storage is blocked). */
function visitorKey(): string {
  if (demoKey) return demoKey;
  try {
    const saved = localStorage.getItem(DEMO_KEY);
    if (saved && /^[A-Za-z0-9_-]{22,128}$/.test(saved)) return (demoKey = saved);
  } catch {
    /* storage blocked */
  }
  demoKey = newIdempotencyKey() + newIdempotencyKey();
  try {
    localStorage.setItem(DEMO_KEY, demoKey);
  } catch {
    /* storage blocked */
  }
  return demoKey;
}

/** The Authorization header: signed launch data inside Telegram, a demo key on
 * a public DEMO site. In local development the backend can sign test data when
 * DEV_AUTH_ENABLED=true and VITE_DEV_AUTH=1. */
async function authorization(): Promise<string> {
  if (isTelegram && tg) return `tma ${tg.initData}`;
  if (publicDemo) return `demo ${visitorKey()}`;
  if (import.meta.env.VITE_DEV_AUTH === "1") {
    devInitData ??= fetch(`${BASE}/dev/init-data?telegram_id=${import.meta.env.VITE_DEV_TELEGRAM_ID ?? 100001}`)
      .then((r) => (r.ok ? r.json() : { init_data: "" }))
      .then((d: { init_data: string }) => d.init_data)
      .catch(() => "");
    const data = await devInitData;
    return data ? `tma ${data}` : "";
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
    const auth = await authorization();
    if (auth) headers.Authorization = auth;
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
