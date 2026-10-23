import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError, onUnauthorized, setCsrf } from "./api";
import type { Admin, Role } from "./types";

type State = { status: "loading" } | { status: "anon"; error?: string; botUsername?: string | null } | { status: "ready"; admin: Admin; botUsername: string | null };

const AuthCtx = createContext<{ state: State; logout: () => Promise<void>; refresh: () => Promise<void> }>({
  state: { status: "loading" },
  logout: async () => {},
  refresh: async () => {},
});

const RANK: Record<Role, number> = { support: 1, manager: 2, owner: 3 };

declare global {
  interface Window {
    Telegram?: { WebApp?: { initData: string; ready(): void; expand(): void } };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const started = useRef(false);

  const loadMe = useCallback(async () => {
    try {
      const me = await api<{ admin: Admin; csrf_token: string; bot_username: string | null }>("/auth/me");
      setCsrf(me.csrf_token);
      setState({ status: "ready", admin: me.admin, botUsername: me.bot_username });
    } catch (e) {
      setCsrf(null);
      setState({ status: "anon", error: e instanceof ApiError && e.status !== 401 ? e.message : undefined });
    }
  }, []);

  useEffect(() => onUnauthorized(() => setState({ status: "anon", error: "Сессия истекла, войдите снова" })), []);

  useEffect(() => {
    // The login token is single-use: never exchange it twice (StrictMode re-runs effects).
    if (started.current) return;
    started.current = true;
    const boot = async () => {
      const hash = new URLSearchParams(window.location.hash.slice(1));
      const token = hash.get("token");
      try {
        if (token) {
          history.replaceState(null, "", window.location.pathname); // never keep the token in the URL
          const r = await api<{ admin: Admin; csrf_token: string }>("/auth/exchange", { method: "POST", body: { token } });
          setCsrf(r.csrf_token);
        } else if (window.Telegram?.WebApp?.initData) {
          window.Telegram.WebApp.ready();
          window.Telegram.WebApp.expand();
          const r = await api<{ admin: Admin; csrf_token: string }>("/auth/webapp", { method: "POST", body: { init_data: window.Telegram.WebApp.initData } });
          setCsrf(r.csrf_token);
        }
      } catch (e) {
        setState({ status: "anon", error: e instanceof ApiError ? e.message : "Не удалось войти" });
        return;
      }
      await loadMe();
    };
    void boot();
  }, [loadMe]);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      setCsrf(null);
      setState({ status: "anon" });
    }
  }, []);

  return <AuthCtx.Provider value={{ state, logout, refresh: loadMe }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);

export function useAdmin(): Admin {
  const { state } = useAuth();
  if (state.status !== "ready") throw new Error("not authenticated");
  return state.admin;
}

export function can(admin: Admin, role: Role): boolean {
  return RANK[admin.role] >= RANK[role];
}
