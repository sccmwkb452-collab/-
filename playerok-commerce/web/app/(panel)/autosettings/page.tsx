"use client";

import { ChevronRight, OctagonX, ShieldAlert } from "lucide-react";
import Link from "next/link";

import { Async, Notice, PageHeader } from "@/components/app/blocks";
import { ConfirmAction } from "@/components/app/confirm";
import { StatusBadge, ToneBadge } from "@/components/app/status";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { ago } from "@/lib/format";
import { useSession } from "@/lib/session";
import { INTEGRATION_STATE } from "@/lib/status";
import type { AutoItem, KillSwitch } from "@/lib/types";

export default function AutosettingsPage() {
  const { can } = useSession();
  const state = useApi<{ items: AutoItem[]; kill_switch: KillSwitch }>("/autosettings");
  const { busy, run } = useAction();

  async function toggle(code: string, enabled: boolean) {
    const r = await run(code, () => api.post(`/autosettings/${code}/toggle`, { enabled }), enabled ? "Включено" : "Выключено");
    if (r) state.reload();
  }

  return (
    <>
      <PageHeader
        title="Автонастройки"
        description="14 функций автоматизации. У каждой — описание, статус, тексты, предпросмотр, тест, история и сброс."
        actions={
          can("security.manage") && (
            <ConfirmAction
              label="Отключить всё"
              icon={<OctagonX />}
              variant="danger-soft"
              size="md"
              title="Аварийно отключить все автонастройки?"
              description="Все функции будут выключены. Включать обратно придётся по одной. Глобальная остановка всей автоматизации — в разделе «Безопасность»."
              input={{ label: "Причина", initial: "Аварийное отключение из панели" }}
              confirmVariant="danger"
              confirmLabel="Отключить всё"
              onConfirm={async (reason) => {
                const r = await run("all", () => api.post<{ disabled: number }>("/autosettings-emergency-off", { reason }), (x) => `Отключено функций: ${x.disabled}`);
                if (r) state.reload();
                return r;
              }}
            />
          )
        }
      />
      <Async state={state} rows={10}>
        {(d) => (
          <>
            {d.kill_switch.active && (
              <Notice tone="danger" title="Вся автоматизация остановлена" className="mb-5">
                {d.kill_switch.reason || "Аварийная остановка"} · {ago(d.kill_switch.at)}. Включённые функции не выполняются, пока остановка не снята в разделе
                «Безопасность».
              </Notice>
            )}
            <Notice className="mb-5">
              PlayerOK не даёт API для чатов, подтверждения сделок и поднятия лотов. Такие функции работают в <b>режиме подсказок</b>: бот присылает готовый
              текст или напоминание, а действие на площадке выполняете вы. Функции, которые без API невозможны, честно помечены «Интеграция недоступна».
            </Notice>
            <Card>
              <ul className="divide-y divide-border">
                {d.items.map((a) => {
                  const unavailable = a.integration.state === "unavailable";
                  return (
                    <li key={a.code} className="flex items-center gap-4 px-5 py-3.5">
                      <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-border bg-surface-2 text-lg" aria-hidden>
                        {a.emoji}
                      </span>
                      <Link href={`/autosettings/${a.code}`} className="group min-w-0 flex-1">
                        <span className="flex items-center gap-1 font-medium group-hover:text-highlight">
                          {a.title} <ChevronRight className="size-4 text-subtle" />
                        </span>
                        <span className="mt-1 flex flex-wrap items-center gap-2">
                          <StatusBadge map={INTEGRATION_STATE} value={a.integration.state} />
                          {a.enabled && !a.stopped && !unavailable && <ToneBadge tone="success">Работает</ToneBadge>}
                          {a.enabled && a.stopped && (
                            <ToneBadge tone="danger">
                              <ShieldAlert /> Остановлено аварийно
                            </ToneBadge>
                          )}
                        </span>
                      </Link>
                      <Switch
                        checked={a.enabled}
                        disabled={unavailable || !can("autosettings.manage") || busy !== null}
                        onCheckedChange={(v) => toggle(a.code, v)}
                        aria-label={`${a.title}: ${a.enabled ? "выключить" : "включить"}`}
                        title={unavailable ? a.integration.reason : undefined}
                      />
                    </li>
                  );
                })}
              </ul>
            </Card>
          </>
        )}
      </Async>
    </>
  );
}
