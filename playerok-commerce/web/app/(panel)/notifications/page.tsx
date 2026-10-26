"use client";

import { Bell, Link2, Save } from "lucide-react";
import * as React from "react";

import { Async, CopyButton, Empty, Notice, PageHeader } from "@/components/app/blocks";
import { StatusBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { dt } from "@/lib/format";
import { useDraft } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { NOTIFICATION_STATUS } from "@/lib/status";
import type { Notification } from "@/lib/types";

type NotifySettings = { kinds: Record<string, boolean>; quiet_hours: { enabled: boolean; start: string; end: string } };
type SettingsView = { values: { notifications: NotifySettings }; notification_kinds: Record<string, string>; timezone: string };

const SEVERITY_TONE: Record<string, string> = { info: "", success: "text-green-300", warning: "text-yellow-300", critical: "text-red-300" };

function TelegramLink() {
  const { me, botUsername, reload } = useSession();
  const [link, setLink] = React.useState<{ code: string; link: string | null; command: string; expires_minutes: number }>();
  const { busy, run } = useAction();
  return (
    <Card>
      <CardHeader title="Telegram" description={botUsername ? `Бот @${botUsername}` : "Имя бота не задано (BOT_USERNAME)"} />
      <CardBody className="flex flex-col gap-3 text-sm">
        <p>
          {me?.telegram_linked ? "Ваш аккаунт привязан — уведомления приходят вам в Telegram." : "Аккаунт не привязан к Telegram. Владельцы из OWNER_TELEGRAM_IDS получают уведомления и без привязки."}
        </p>
        <Button
          size="sm"
          className="self-start"
          loading={busy === "link"}
          onClick={async () => {
            const r = await run("link", () => api.post<NonNullable<typeof link>>("/auth/telegram-link"));
            if (r) setLink(r);
          }}
        >
          <Link2 /> {me?.telegram_linked ? "Привязать другой аккаунт" : "Привязать Telegram"}
        </Button>
        {link && (
          <div className="rounded-md border border-border bg-surface-2/40 p-3 text-[13px]">
            <p>Код действует {link.expires_minutes} минут и срабатывает один раз.</p>
            {link.link ? (
              <a href={link.link} target="_blank" rel="noreferrer noopener" className="mt-1 block text-highlight hover:underline" onClick={() => setTimeout(reload, 15_000)}>
                Открыть бота и привязать →
              </a>
            ) : (
              <p className="mt-1">Отправьте боту команду:</p>
            )}
            <div className="mt-2 flex items-center gap-2">
              <code className="rounded bg-surface-3 px-2 py-1 font-mono">{link.command}</code>
              <CopyButton value={link.command} />
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function Preferences() {
  const { can } = useSession();
  const state = useApi<SettingsView>("/settings");
  const [draft, setDraft] = useDraft(state.data, (d) => structuredClone(d.values.notifications));
  const { busy, run } = useAction();
  const manage = can("settings.manage");
  return (
    <Card>
      <CardHeader title="Что присылать" description="Выключенные виды сохраняются в журнале, но не отправляются. Критичные уведомления отправляются всегда." />
      <Async state={state}>
        {(d) =>
          draft && (
            <CardBody className="flex flex-col gap-5">
              <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                {Object.entries(d.notification_kinds).map(([kind, label]) => (
                  <label key={kind} className="flex items-center justify-between gap-3 text-sm">
                    <span>{label.replace(/^\S+\s/, "")}</span>
                    <Switch
                      checked={draft.kinds[kind] ?? true}
                      disabled={!manage}
                      onCheckedChange={(v) => setDraft({ ...draft, kinds: { ...draft.kinds, [kind]: v } })}
                    />
                  </label>
                ))}
              </div>
              <div className="rounded-md border border-border p-4">
                <label className="flex items-center justify-between gap-3 text-sm font-medium">
                  Тихие часы
                  <Switch
                    checked={draft.quiet_hours.enabled}
                    disabled={!manage}
                    onCheckedChange={(v) => setDraft({ ...draft, quiet_hours: { ...draft.quiet_hours, enabled: v } })}
                  />
                </label>
                <p className="mt-1 text-xs text-muted-foreground">
                  В это время ({d.timezone}) обычные уведомления копятся и приходят после окончания тихих часов; критичные приходят сразу.
                </p>
                <div className="mt-3 grid max-w-xs grid-cols-2 gap-3">
                  <Field label="С">
                    <Input type="time" value={draft.quiet_hours.start} disabled={!manage} onChange={(e) => setDraft({ ...draft, quiet_hours: { ...draft.quiet_hours, start: e.target.value } })} />
                  </Field>
                  <Field label="До">
                    <Input type="time" value={draft.quiet_hours.end} disabled={!manage} onChange={(e) => setDraft({ ...draft, quiet_hours: { ...draft.quiet_hours, end: e.target.value } })} />
                  </Field>
                </div>
              </div>
              {manage && (
                <Button
                  variant="primary"
                  className="self-start"
                  loading={busy === "save"}
                  onClick={async () => {
                    const r = await run("save", () => api.put("/settings/notifications", { value: draft }), "Настройки уведомлений сохранены");
                    if (r) state.reload();
                  }}
                >
                  <Save /> Сохранить
                </Button>
              )}
            </CardBody>
          )
        }
      </Async>
    </Card>
  );
}

export default function NotificationsPage() {
  const state = useApi<{ items: Notification[]; kinds: Record<string, string> }>("/notifications");
  return (
    <>
      <PageHeader title="Уведомления" description="Что и когда бот присылает в Telegram. Секреты и полные коды в уведомления не попадают." />
      <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader title="Последние уведомления" />
          <Async state={state} rows={8}>
            {(d) =>
              d.items.length ? (
                <ul className="divide-y divide-border">
                  {d.items.map((n) => (
                    <li key={n.id} className="px-5 py-3.5">
                      <div className="flex flex-wrap items-center gap-2 text-[13px]">
                        <span className={`font-medium ${SEVERITY_TONE[n.severity] ?? ""}`}>{n.title}</span>
                        <StatusBadge map={NOTIFICATION_STATUS} value={n.status} />
                        <span className="ml-auto text-xs text-muted-foreground">{dt(n.created_at)}</span>
                      </div>
                      <p className="mt-1 line-clamp-3 text-[13px] whitespace-pre-line text-muted-foreground">{n.body.replace(/<[^>]+>/g, "")}</p>
                      <p className="mt-1 text-[11px] text-subtle">
                        {(d.kinds[n.kind] ?? n.kind).replace(/^\S+\s/, "")}
                        {n.attempts > 1 ? ` · попыток ${n.attempts}` : ""}
                        {n.last_error ? ` · ${n.last_error}` : ""}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty title="Уведомлений пока не было" icon={Bell} />
              )
            }
          </Async>
        </Card>
        <div className="flex flex-col gap-6">
          <TelegramLink />
          <Preferences />
          <Notice>Отправку выполняет воркер. Если он не запущен, уведомления копятся в очереди со статусом «В очереди».</Notice>
        </div>
      </div>
    </>
  );
}
