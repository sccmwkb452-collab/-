"use client";

import { FlaskConical, KeyRound, LogOut, Monitor, OctagonX, ShieldCheck, Zap } from "lucide-react";
import * as React from "react";

import { Async, CopyButton, Empty, KV, Notice, PageHeader } from "@/components/app/blocks";
import { ConfirmAction } from "@/components/app/confirm";
import { ToneBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { ago, dt } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { AuditEntry, KillSwitch } from "@/lib/types";

type Security = {
  kill_switch: KillSwitch;
  mode: "test" | "live";
  live_allowed: boolean;
  failed_logins: AuditEntry[];
  admin_actions: AuditEntry[];
  session_hours: number;
  session_idle_minutes: number;
};

type WebSession = { id: number; ip: string | null; user_agent: string | null; created_at: string; last_seen_at: string; expires_at: string; current: boolean };

function shortAgent(ua: string | null) {
  if (!ua) return "неизвестное устройство";
  const browser = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "браузер";
  const os = /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Mac OS/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "";
  return `${browser}${os ? `, ${os}` : ""}`;
}

function PasswordCard() {
  const [v, setV] = React.useState({ current: "", next: "", repeat: "" });
  const { busy, run } = useAction();
  const mismatch = v.repeat && v.next !== v.repeat;
  return (
    <Card>
      <CardHeader title="Пароль" description="Не короче 10 символов: строчные, заглавные буквы и цифра" />
      <CardBody className="flex flex-col gap-3">
        <Field label="Текущий пароль">
          <Input type="password" autoComplete="current-password" value={v.current} onChange={(e) => setV({ ...v, current: e.target.value })} />
        </Field>
        <Field label="Новый пароль">
          <Input type="password" autoComplete="new-password" value={v.next} onChange={(e) => setV({ ...v, next: e.target.value })} />
        </Field>
        <Field label="Повторите новый пароль" error={mismatch ? "Пароли не совпадают" : undefined}>
          <Input type="password" autoComplete="new-password" value={v.repeat} onChange={(e) => setV({ ...v, repeat: e.target.value })} aria-invalid={Boolean(mismatch)} />
        </Field>
        <Button
          variant="primary"
          className="self-start"
          disabled={!v.current || v.next.length < 10 || v.next !== v.repeat}
          loading={busy === "pw"}
          onClick={async () => {
            const r = await run(
              "pw",
              () => api.post<{ revoked_sessions: number }>("/auth/password", { current_password: v.current, new_password: v.next }),
              (x) => `Пароль изменён. Завершено других сессий: ${x.revoked_sessions}`,
            );
            if (r) setV({ current: "", next: "", repeat: "" });
          }}
        >
          <KeyRound /> Сменить пароль
        </Button>
      </CardBody>
    </Card>
  );
}

function TotpCard() {
  const { me, reload } = useSession();
  const [uri, setUri] = React.useState<string>();
  const [code, setCode] = React.useState("");
  const { busy, run } = useAction();
  const secret = uri ? new URL(uri).searchParams.get("secret") ?? "" : "";
  return (
    <Card>
      <CardHeader
        title="Двухфакторная аутентификация"
        description="Код из приложения-аутентификатора при каждом входе"
        actions={me?.totp_enabled ? <ToneBadge tone="success">Включена</ToneBadge> : <ToneBadge tone="warning">Выключена</ToneBadge>}
      />
      <CardBody className="flex flex-col gap-3">
        {me?.totp_enabled ? (
          <ConfirmAction
            label="Отключить 2FA"
            variant="danger-soft"
            title="Отключить двухфакторную аутентификацию?"
            description="Вход станет возможен только по паролю."
            input={{ label: "Ваш пароль", type: "password", required: true }}
            confirmVariant="danger"
            confirmLabel="Отключить"
            onConfirm={async (password) => {
              const r = await run("off", () => api.post("/auth/totp/disable", { password }), "2FA отключена");
              if (r) reload();
              return r;
            }}
          />
        ) : uri ? (
          <>
            <ol className="list-decimal pl-5 text-[13px] text-muted-foreground">
              <li>Откройте Google Authenticator, 1Password, Aegis или другое приложение.</li>
              <li>Добавьте аккаунт вручную по секретному ключу ниже (или по ссылке otpauth).</li>
              <li>Введите 6-значный код из приложения.</li>
            </ol>
            <div className="flex flex-wrap items-center gap-2">
              <code className="rounded bg-surface-2 px-2 py-1 font-mono text-[13px] break-all">{secret}</code>
              <CopyButton value={secret} label="Ключ" />
              <CopyButton value={uri} label="Ссылка otpauth" />
            </div>
            <div className="flex items-end gap-2">
              <Field label="Код из приложения">
                <Input inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="w-36" />
              </Field>
              <Button
                variant="primary"
                disabled={code.length < 6}
                loading={busy === "confirm"}
                onClick={async () => {
                  const r = await run("confirm", () => api.post("/auth/totp/confirm", { code }), "2FA включена");
                  if (r) {
                    setUri(undefined);
                    setCode("");
                    reload();
                  }
                }}
              >
                Подтвердить
              </Button>
            </div>
          </>
        ) : (
          <Button
            className="self-start"
            loading={busy === "setup"}
            onClick={async () => {
              const r = await run("setup", () => api.post<{ otpauth_uri: string }>("/auth/totp/setup"));
              if (r) setUri(r.otpauth_uri);
            }}
          >
            <ShieldCheck /> Включить 2FA
          </Button>
        )}
      </CardBody>
    </Card>
  );
}

function SessionsCard() {
  const state = useApi<{ items: WebSession[] }>("/auth/sessions");
  const { busy, run } = useAction();
  return (
    <Card>
      <CardHeader
        title="Активные сессии"
        actions={
          <Button
            size="sm"
            loading={busy === "others"}
            onClick={async () => {
              const r = await run("others", () => api.post<{ revoked: number }>("/auth/sessions/revoke-others"), (x) => `Завершено сессий: ${x.revoked}`);
              if (r) state.reload();
            }}
          >
            <LogOut /> Завершить остальные
          </Button>
        }
      />
      <Async state={state}>
        {(d) => (
          <ul className="divide-y divide-border">
            {d.items.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 px-5 py-3">
                <div className="flex min-w-0 items-center gap-3">
                  <Monitor className="size-4 shrink-0 text-subtle" />
                  <div className="min-w-0 text-[13px]">
                    <p className="truncate">
                      {shortAgent(s.user_agent)} {s.current && <span className="text-green-300">· эта сессия</span>}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {s.ip ?? "IP неизвестен"} · активность {ago(s.last_seen_at)} · до {dt(s.expires_at)}
                    </p>
                  </div>
                </div>
                {!s.current && (
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={busy === `s${s.id}`}
                    onClick={async () => {
                      const r = await run(`s${s.id}`, () => api.del(`/auth/sessions/${s.id}`), "Сессия завершена");
                      if (r) state.reload();
                    }}
                  >
                    Завершить
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Async>
    </Card>
  );
}

export default function SecurityPage() {
  const { can, me } = useSession();
  const state = useApi<Security>("/security");
  const { run } = useAction();
  const owner = me?.permissions.includes("*");

  return (
    <>
      <PageHeader title="Безопасность" description="Режим работы, аварийная остановка, вход в панель и журнал входов." />
      <Async state={state} rows={8}>
        {(d) => (
          <div className="flex flex-col gap-6">
            <div className="grid gap-6 xl:grid-cols-2">
              <Card className={d.kill_switch.active ? "border-danger/40" : undefined}>
                <CardHeader
                  title="Аварийная остановка"
                  description="Мгновенно останавливает все закупки, автовыдачу, автонастройки и публикации"
                  actions={d.kill_switch.active ? <ToneBadge tone="danger">Остановлено</ToneBadge> : <ToneBadge tone="success">Работает</ToneBadge>}
                />
                <CardBody className="flex flex-col gap-3">
                  {d.kill_switch.active && (
                    <KV
                      items={[
                        ["Причина", d.kill_switch.reason || "—"],
                        ["Кто", d.kill_switch.by ?? "—"],
                        ["Когда", dt(d.kill_switch.at)],
                      ]}
                    />
                  )}
                  {can("security.manage") &&
                    (d.kill_switch.active ? (
                      <ConfirmAction
                        label="Снять остановку"
                        variant="success"
                        title="Возобновить автоматизацию?"
                        description="Снова начнут работать включённые автонастройки и закупки в пределах лимитов."
                        confirmLabel="Возобновить"
                        onConfirm={async () => {
                          const r = await run("ks", () => api.post("/security/kill-switch", { active: false }), "Автоматизация возобновлена");
                          if (r) state.reload();
                          return r;
                        }}
                      />
                    ) : (
                      <ConfirmAction
                        label="Остановить всю автоматизацию"
                        icon={<OctagonX />}
                        variant="danger"
                        size="md"
                        title="Аварийно остановить автоматизацию?"
                        description="Ничего не удаляется. Заказы продолжат приниматься, но все автоматические действия будут ждать вас."
                        input={{ label: "Причина", required: true }}
                        confirmVariant="danger"
                        confirmLabel="Остановить"
                        onConfirm={async (reason) => {
                          const r = await run("ks", () => api.post("/security/kill-switch", { active: true, reason }), "Автоматизация остановлена");
                          if (r) state.reload();
                          return r;
                        }}
                      />
                    ))}
                </CardBody>
              </Card>

              <Card>
                <CardHeader
                  title="Режим работы"
                  actions={d.mode === "live" ? <ToneBadge tone="success">Боевой</ToneBadge> : <ToneBadge tone="warning">Тестовый</ToneBadge>}
                />
                <CardBody className="flex flex-col gap-3">
                  <p className="text-[13px] text-muted-foreground">
                    В тестовом режиме закупки у поставщиков имитируются (коды с префиксом TEST-), публикации не выполняются, а деньги не тратятся.
                  </p>
                  {!d.live_allowed && (
                    <Notice tone="warning">
                      Боевой режим запрещён на сервере. Чтобы разрешить его, задайте <b>ALLOW_LIVE_OPERATIONS=true</b> в переменных окружения backend,
                      перезапустите сервисы и включите режим здесь.
                    </Notice>
                  )}
                  {can("settings.manage") &&
                    (d.mode === "live" ? (
                      <ConfirmAction
                        label="Перейти в тестовый режим"
                        icon={<FlaskConical />}
                        title="Включить тестовый режим?"
                        onConfirm={async () => {
                          const r = await run("mode", () => api.post("/security/mode", { mode: "test" }), "Тестовый режим включён");
                          if (r) state.reload();
                          return r;
                        }}
                      />
                    ) : (
                      <ConfirmAction
                        label="Включить боевой режим"
                        icon={<Zap />}
                        variant="primary"
                        disabled={!d.live_allowed || !owner}
                        title="Включить боевой режим?"
                        description="Система начнёт выполнять реальные закупки в пределах лимитов поставщиков. Проверьте лимиты и режимы закупки перед включением."
                        confirmLabel="Включить"
                        confirmVariant="danger"
                        onConfirm={async () => {
                          const r = await run("mode", () => api.post<{ mode: string }>("/security/mode", { mode: "live" }), (x) =>
                            x.mode === "live" ? "Боевой режим включён" : "Сервер не разрешил боевой режим",
                          );
                          if (r) state.reload();
                          return r;
                        }}
                      />
                    ))}
                  {!owner && <p className="text-xs text-muted-foreground">Боевой режим включает только владелец.</p>}
                </CardBody>
              </Card>
            </div>

            <div className="grid gap-6 xl:grid-cols-3">
              <PasswordCard />
              <TotpCard />
              <Card>
                <CardHeader title="Политика входа" />
                <CardBody>
                  <KV
                    items={[
                      ["Срок сессии", `${d.session_hours} ч`],
                      ["Выход при бездействии", `${d.session_idle_minutes} мин`],
                      ["Блокировка", "после 5 неудачных попыток на 15 мин"],
                      ["Защита", "httpOnly-cookie, SameSite=strict, CSRF-токен"],
                    ]}
                  />
                </CardBody>
              </Card>
            </div>

            <SessionsCard />

            <div className="grid gap-6 xl:grid-cols-2">
              <Card>
                <CardHeader title="Неудачные входы" />
                {d.failed_logins.length ? (
                  <Table>
                    <THead>
                      <TR className="hover:bg-transparent">
                        <TH>Когда</TH>
                        <TH>Логин</TH>
                        <TH>IP</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {d.failed_logins.map((a) => (
                        <TR key={a.id}>
                          <TD className="whitespace-nowrap text-muted-foreground">{dt(a.created_at)}</TD>
                          <TD>
                            {a.actor ?? "—"}
                            <span className="block text-xs text-muted-foreground">
                              {a.action === "auth.totp_failed" ? "неверный код 2FA" : a.details?.reason === "unknown_email" ? "нет такого пользователя" : "неверный пароль"}
                            </span>
                          </TD>
                          <TD className="text-muted-foreground">{a.ip ?? "—"}</TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                ) : (
                  <Empty title="Неудачных входов не было" icon={ShieldCheck} />
                )}
              </Card>
              <Card>
                <CardHeader title="Действия администраторов" />
                {d.admin_actions.length ? (
                  <ul className="divide-y divide-border">
                    {d.admin_actions.map((a) => (
                      <li key={a.id} className="flex items-center justify-between gap-3 px-5 py-2.5 text-[13px]">
                        <span className="min-w-0 truncate">
                          {a.actor} · <span className="font-mono text-[12px] text-muted-foreground">{a.action}</span>
                        </span>
                        <span className="shrink-0 text-xs text-muted-foreground">{dt(a.created_at)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty title="Нет записей" />
                )}
              </Card>
            </div>
          </div>
        )}
      </Async>
    </>
  );
}
