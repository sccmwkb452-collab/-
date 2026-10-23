import type { ApiErrorBody } from "@starshop/shared";

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

const BASE = "/api/v1/admin";
const CSRF_KEY = "pulsar.admin.csrf";
let csrf: string | null = null;
try {
  csrf = sessionStorage.getItem(CSRF_KEY);
} catch {
  csrf = null;
}

export function setCsrf(token: string | null): void {
  csrf = token;
  try {
    if (token) sessionStorage.setItem(CSRF_KEY, token);
    else sessionStorage.removeItem(CSRF_KEY);
  } catch {
    /* storage unavailable */
  }
}

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();
export function onUnauthorized(fn: Listener): () => void {
  unauthorizedListeners.add(fn);
  return () => unauthorizedListeners.delete(fn);
}

/** Session = HttpOnly cookie set by the server; mutating calls also carry
 * the CSRF token returned at login. */
export async function api<T>(path: string, options: { method?: string; body?: unknown; timeoutMs?: number } = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrf) headers["X-CSRF-Token"] = csrf;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 25000);
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      method,
      headers,
      credentials: "same-origin",
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(0, "network", "Нет соединения с сервером");
  } finally {
    clearTimeout(timer);
  }
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const err = (payload as ApiErrorBody | null)?.error;
    if (response.status === 401 && !path.startsWith("/auth/")) unauthorizedListeners.forEach((fn) => fn());
    throw new ApiError(response.status, err?.code ?? "http_error", err?.message ?? `Ошибка ${response.status}`, err?.details);
  }
  return payload as T;
}

export function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Что-то пошло не так";
}

export function exportUrl(path: string, params: Record<string, string | undefined>): string {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]);
  return `${BASE}${path}${q.size ? `?${q}` : ""}`;
}
