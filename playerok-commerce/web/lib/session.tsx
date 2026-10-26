"use client";

import * as React from "react";

import { api, useApi } from "./api";

export type Me = {
  id: number;
  email: string;
  display_name: string;
  role: string;
  role_name: string;
  permissions: string[];
  telegram_linked: boolean;
  totp_enabled: boolean;
  last_login_at: string | null;
};

type SessionValue = { me: Me | undefined; botUsername: string | null; can: (permission: string) => boolean; reload: () => void };

const SessionContext = React.createContext<SessionValue>({ me: undefined, botUsername: null, can: () => false, reload: () => {} });

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const state = useApi<{ user: Me; bot_username: string | null }>("/auth/me");
  const me = state.data?.user;
  const value = React.useMemo<SessionValue>(
    () => ({
      me,
      botUsername: state.data?.bot_username ?? null,
      can: (permission: string) => Boolean(me && (me.permissions.includes("*") || me.permissions.includes(permission))),
      reload: state.reload,
    }),
    [me, state.data?.bot_username, state.reload],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  return React.useContext(SessionContext);
}

export async function logout() {
  try {
    await api.post("/auth/logout");
  } finally {
    window.location.replace("/login");
  }
}
