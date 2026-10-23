import { LogoMark } from "@starshop/shared";
import { KeyRound, MessageSquare, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, setCsrf } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ErrorBox } from "../components/ui";

declare global {
  interface Window {
    onTelegramAuth?: (user: Record<string, unknown>) => void;
  }
}

/** Passwordless sign-in: a one-time link from the bot (/admin), Telegram
 * Mini App launch data, or the Telegram Login Widget (needs /setdomain in @BotFather). */
export function Login({ error }: { error?: string }) {
  const { refresh } = useAuth();
  const widget = useRef<HTMLDivElement>(null);
  const [bot, setBot] = useState("");
  useEffect(() => {
    fetch("/api/v1/bootstrap")
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { bot_username?: string | null } | null) => setBot(d?.bot_username ?? ""))
      .catch(() => setBot(""));
  }, []);

  useEffect(() => {
    if (!bot || !widget.current) return;
    window.onTelegramAuth = async (user) => {
      try {
        const r = await api<{ csrf_token: string }>("/auth/telegram-widget", { method: "POST", body: user });
        setCsrf(r.csrf_token);
        await refresh();
      } catch {
        /* the error box shows after refresh */
      }
    };
    const s = document.createElement("script");
    s.src = "https://telegram.org/js/telegram-widget.js?22";
    s.async = true;
    s.dataset.telegramLogin = bot;
    s.dataset.size = "large";
    s.dataset.radius = "12";
    s.dataset.onauth = "onTelegramAuth(user)";
    s.dataset.requestAccess = "write";
    widget.current.appendChild(s);
  }, [bot, refresh]);

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden px-4">
      <div className="pointer-events-none absolute -left-32 -top-32 size-[420px] rounded-full bg-accent/20 blur-[120px]" aria-hidden />
      <div className="pointer-events-none absolute -bottom-40 -right-24 size-[420px] rounded-full bg-accent-2/20 blur-[120px]" aria-hidden />
      <div className="relative w-full max-w-[420px] rounded-3xl bg-surface p-7 ring-1 ring-line shadow-card">
        <LogoMark size={48} />
        <h1 className="mt-5 font-display text-[22px] font-semibold tracking-[-0.03em]">Вход в админ-панель</h1>
        <p className="mt-2 text-[14px] leading-relaxed text-text-2">Без паролей: вход подтверждается вашим аккаунтом Telegram.</p>
        {error && (
          <div className="mt-5">
            <ErrorBox text={error} />
          </div>
        )}
        <ol className="mt-6 space-y-4 text-[13.5px]">
          <li className="flex gap-3">
            <MessageSquare className="mt-0.5 size-5 shrink-0 text-accent" />
            <span>
              Отправьте боту {bot ? <b>@{bot}</b> : "магазина"} команду <code className="rounded bg-surface-2 px-1.5 py-0.5 font-semibold">/admin</code>.
            </span>
          </li>
          <li className="flex gap-3">
            <KeyRound className="mt-0.5 size-5 shrink-0 text-accent" />
            <span>Нажмите «Войти в админ-панель». Ссылка одноразовая и действует 5 минут.</span>
          </li>
          <li className="flex gap-3">
            <ShieldCheck className="mt-0.5 size-5 shrink-0 text-accent" />
            <span>Доступ есть только у администраторов из списка в настройках.</span>
          </li>
        </ol>
        {bot && <div ref={widget} className="mt-6 flex justify-center" />}
      </div>
    </div>
  );
}
