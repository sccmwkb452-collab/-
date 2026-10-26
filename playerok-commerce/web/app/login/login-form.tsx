"use client";

import { KeyRound, LockKeyhole } from "lucide-react";
import { useSearchParams } from "next/navigation";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";

function safeNext(value: string | null) {
  // only same-site relative paths: never redirect to another origin
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/login")) return "/";
  return value;
}

export function LoginForm() {
  const params = useSearchParams();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [totp, setTotp] = React.useState("");
  const [needTotp, setNeedTotp] = React.useState(false);
  const [error, setError] = React.useState<string>();
  const [busy, setBusy] = React.useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await api.post("/auth/login", { email, password, totp: needTotp ? totp : null });
      window.location.replace(safeNext(params.get("next")));
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.code === "totp_required") {
        setNeedTotp(true);
        setError(undefined);
      } else {
        setError(apiError.message);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative w-full max-w-sm">
      <div className="mb-8 flex flex-col items-center text-center">
        <span className="mb-4 grid size-11 place-items-center rounded-xl bg-gradient-to-br from-primary to-highlight text-lg font-bold text-white shadow-lg shadow-primary/25">
          P
        </span>
        <h1 className="text-xl font-semibold tracking-tight">PlayerOK Commerce</h1>
        <p className="mt-1 text-sm text-muted-foreground">Закрытая панель управления магазином</p>
      </div>
      <form onSubmit={submit} className="rounded-xl border border-border bg-surface/90 p-6 shadow-2xl backdrop-blur" noValidate>
        <div className="flex flex-col gap-4">
          <Field label="Электронная почта" htmlFor="email">
            <Input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={needTotp}
              autoFocus
            />
          </Field>
          <Field label="Пароль" htmlFor="password">
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={needTotp}
            />
          </Field>
          {needTotp && (
            <Field label="Код из приложения-аутентификатора" htmlFor="totp" hint="6 цифр из Google Authenticator, 1Password и т. п.">
              <Input
                id="totp"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={8}
                value={totp}
                onChange={(e) => setTotp(e.target.value.replace(/\D/g, ""))}
                autoFocus
              />
            </Field>
          )}
          {error && (
            <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-red-200">
              {error}
            </p>
          )}
          <Button type="submit" variant="primary" size="lg" loading={busy} disabled={!email || !password || (needTotp && totp.length < 6)}>
            {needTotp ? <KeyRound /> : <LockKeyhole />} {needTotp ? "Подтвердить" : "Войти"}
          </Button>
        </div>
      </form>
      <p className="mt-5 text-center text-xs text-subtle">
        Доступ только для владельца и сотрудников. Аккаунт создаётся командой <code className="text-muted-foreground">create-admin</code>.
      </p>
    </div>
  );
}
