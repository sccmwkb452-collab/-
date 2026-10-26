"use client";

import { useCallback, useEffect, useState } from "react";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|; )pac_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function toLogin() {
  if (typeof window === "undefined" || window.location.pathname.startsWith("/login")) return;
  const next = window.location.pathname + window.location.search;
  window.location.replace(`/login?next=${encodeURIComponent(next)}`);
}

export async function request<T>(method: string, path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  const response = await fetch(`/api/v1${path}`, { method, headers, body: payload, credentials: "same-origin", cache: "no-store", ...init });
  if (response.status === 401 && !path.startsWith("/auth/login")) {
    toLogin();
  }
  if (!response.ok) {
    let code = "http_error";
    let message = `Ошибка ${response.status}`;
    let details: Record<string, unknown> | undefined;
    try {
      const data = await response.json();
      code = data?.error?.code ?? code;
      message = data?.error?.message ?? message;
      details = data?.error?.details;
    } catch {
      if (response.status >= 500) message = "Сервер недоступен. Проверьте, что backend запущен.";
    }
    throw new ApiError(response.status, code, message, details);
  }
  const type = response.headers.get("content-type") ?? "";
  if (type.includes("application/json")) return (await response.json()) as T;
  return (await response.blob()) as unknown as T;
}

export const api = {
  get: <T,>(path: string) => request<T>("GET", path),
  post: <T,>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T,>(path: string, body?: unknown) => request<T>("PUT", path, body ?? {}),
  patch: <T,>(path: string, body?: unknown) => request<T>("PATCH", path, body ?? {}),
  del: <T,>(path: string) => request<T>("DELETE", path),
};

export async function download(path: string, fallbackName: string) {
  const response = await fetch(`/api/v1${path}`, { credentials: "same-origin" });
  if (!response.ok) throw new ApiError(response.status, "download", "Не удалось скачать файл");
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const name = disposition.match(/filename="?([^"]+)"?/)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export type Loadable<T> = {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  reload: () => void;
  setData: (value: T) => void;
};

/** Small fetch hook: data / error / loading, reload on demand. Keeps the previous
 * data while a reload is in flight so screens do not flash. */
export function useApi<T>(path: string | null): Loadable<T> {
  const [tick, setTick] = useState(0);
  const key = path ? `${path}#${tick}` : null;
  const [state, setState] = useState<{ key: string | null; data?: T; error?: ApiError }>({ key: null });

  useEffect(() => {
    if (!path || !key) return;
    let cancelled = false;
    api
      .get<T>(path)
      .then((value) => {
        if (!cancelled) setState({ key, data: value });
      })
      .catch((err: ApiError) => {
        if (!cancelled) setState((prev) => ({ key, data: prev.data, error: err }));
      });
    return () => {
      cancelled = true;
    };
  }, [path, key]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const setData = useCallback((value: T) => setState((prev) => ({ ...prev, data: value })), []);
  return { data: state.data, error: state.error, loading: key !== null && state.key !== key, reload, setData };
}
