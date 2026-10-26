"use client";

import { RotateCcw, Save } from "lucide-react";
import * as React from "react";

import { Async, Notice, PageHeader } from "@/components/app/blocks";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { useDraft } from "@/lib/hooks";
import { useSession } from "@/lib/session";

type Values = {
  "shop.profile": { name: string; playerok_profile_url: string; operator_contact: string };
  "reports.daily": { enabled: boolean; hour: number };
  "reports.weekly": { enabled: boolean; weekday: number; hour: number };
  "orders.auto_pipeline": boolean;
  "research.weights": Record<string, number>;
};

const WEIGHTS: Record<string, string> = {
  demand: "Спрос",
  margin: "Маржинальность",
  turnover: "Оборачиваемость",
  competition: "Конкуренция",
  supplier_stability: "Стабильность цены поставщика",
  dispute_risk: "Риск споров",
  supplier_reliability: "Надёжность поставщика",
  freshness: "Свежесть данных",
  auto_delivery: "Автовыдача",
};

const WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];

function SettingCard<K extends keyof Values>({
  k,
  title,
  description,
  value,
  children,
  onReload,
}: {
  k: K;
  title: string;
  description?: string;
  value: Values[K];
  children: (draft: Values[K], set: (v: Values[K]) => void, disabled: boolean) => React.ReactNode;
  onReload: () => void;
}) {
  const { can } = useSession();
  const [draft, setDraft] = useDraft(value, (v) => structuredClone(v));
  const { busy, run } = useAction();
  const manage = can("settings.manage");
  const dirty = JSON.stringify(draft) !== JSON.stringify(value);
  return (
    <Card>
      <CardHeader
        title={title}
        description={description}
        actions={
          manage && (
            <Button
              size="sm"
              variant="ghost"
              loading={busy === "reset"}
              onClick={async () => {
                const r = await run("reset", () => api.post(`/settings/${k}/reset`), "Сброшено к значениям по умолчанию");
                if (r) onReload();
              }}
            >
              <RotateCcw /> По умолчанию
            </Button>
          )
        }
      />
      <CardBody className="flex flex-col gap-4">
        {draft !== undefined && children(draft, setDraft, !manage)}
        {manage && (
          <Button
            variant="primary"
            className="self-start"
            disabled={!dirty}
            loading={busy === "save"}
            onClick={async () => {
              const r = await run("save", () => api.put(`/settings/${k}`, { value: draft }), "Сохранено");
              if (r) onReload();
            }}
          >
            <Save /> Сохранить
          </Button>
        )}
      </CardBody>
    </Card>
  );
}

export default function SettingsPage() {
  const state = useApi<{ values: Values; timezone: string }>("/settings");
  return (
    <>
      <PageHeader title="Настройки" description="Профиль магазина, отчёты, обработка заказов и веса исследования." />
      <Async state={state} rows={8}>
        {(d) => (
          <div className="grid gap-6 xl:grid-cols-2">
            <SettingCard k="shop.profile" title="Магазин" description="Название подставляется в тексты для покупателей ({shop})" value={d.values["shop.profile"]} onReload={state.reload}>
              {(v, set, disabled) => (
                <>
                  <Field label="Название магазина">
                    <Input value={v.name} onChange={(e) => set({ ...v, name: e.target.value })} disabled={disabled} />
                  </Field>
                  <Field label="Профиль на PlayerOK">
                    <Input value={v.playerok_profile_url} onChange={(e) => set({ ...v, playerok_profile_url: e.target.value })} disabled={disabled} placeholder="https://playerok.com/profile/…" />
                  </Field>
                  <Field label="Контакт оператора" hint="Для текстов о проблеме с заказом">
                    <Input value={v.operator_contact} onChange={(e) => set({ ...v, operator_contact: e.target.value })} disabled={disabled} />
                  </Field>
                </>
              )}
            </SettingCard>

            <SettingCard
              k="orders.auto_pipeline"
              title="Обработка заказов"
              description="Автоматически проверять, закупать (в рамках режима поставщика) и выдавать новые заказы"
              value={d.values["orders.auto_pipeline"]}
              onReload={state.reload}
            >
              {(v, set, disabled) => (
                <>
                  <label className="flex items-center justify-between gap-3 text-sm">
                    Автоматическая обработка новых заказов
                    <Switch checked={v} onCheckedChange={set} disabled={disabled} />
                  </label>
                  <Notice>
                    Даже при включённой обработке закупка идёт только в режиме поставщика «После подтверждения» или «Автоматически в лимитах», а в тестовом режиме
                    имитируется. Выключите — и каждый заказ будет ждать вашего решения.
                  </Notice>
                </>
              )}
            </SettingCard>

            <SettingCard k="reports.daily" title="Ежедневный отчёт" description={`Приходит в Telegram, время — ${d.timezone}`} value={d.values["reports.daily"]} onReload={state.reload}>
              {(v, set, disabled) => (
                <>
                  <label className="flex items-center justify-between gap-3 text-sm">
                    Присылать отчёт за вчера
                    <Switch checked={v.enabled} onCheckedChange={(x) => set({ ...v, enabled: x })} disabled={disabled} />
                  </label>
                  <Field label="Час отправки">
                    <NativeSelect value={v.hour} onChange={(e) => set({ ...v, hour: Number(e.target.value) })} disabled={disabled} className="w-32">
                      {Array.from({ length: 24 }, (_, h) => (
                        <option key={h} value={h}>
                          {String(h).padStart(2, "0")}:00
                        </option>
                      ))}
                    </NativeSelect>
                  </Field>
                </>
              )}
            </SettingCard>

            <SettingCard k="reports.weekly" title="Еженедельный отчёт" value={d.values["reports.weekly"]} onReload={state.reload}>
              {(v, set, disabled) => (
                <>
                  <label className="flex items-center justify-between gap-3 text-sm">
                    Присылать отчёт за прошлую неделю
                    <Switch checked={v.enabled} onCheckedChange={(x) => set({ ...v, enabled: x })} disabled={disabled} />
                  </label>
                  <div className="grid max-w-md grid-cols-2 gap-3">
                    <Field label="День">
                      <NativeSelect value={v.weekday} onChange={(e) => set({ ...v, weekday: Number(e.target.value) })} disabled={disabled}>
                        {WEEKDAYS.map((w, i) => (
                          <option key={w} value={i + 1}>
                            {w}
                          </option>
                        ))}
                      </NativeSelect>
                    </Field>
                    <Field label="Час">
                      <NativeSelect value={v.hour} onChange={(e) => set({ ...v, hour: Number(e.target.value) })} disabled={disabled}>
                        {Array.from({ length: 24 }, (_, h) => (
                          <option key={h} value={h}>
                            {String(h).padStart(2, "0")}:00
                          </option>
                        ))}
                      </NativeSelect>
                    </Field>
                  </div>
                </>
              )}
            </SettingCard>

            <SettingCard
              k="research.weights"
              title="Веса исследования товаров"
              description="Сколько каждый фактор весит в итоговой оценке. Сумма не обязана быть 100 — веса нормируются."
              value={d.values["research.weights"]}
              onReload={state.reload}
            >
              {(v, set, disabled) => (
                <div className="grid gap-3 sm:grid-cols-2">
                  {Object.entries(v).map(([k, w]) => (
                    <Field key={k} label={WEIGHTS[k] ?? k}>
                      <Input inputMode="numeric" value={String(w)} onChange={(e) => set({ ...v, [k]: Number(e.target.value.replace(/\D/g, "")) || 0 })} disabled={disabled} />
                    </Field>
                  ))}
                </div>
              )}
            </SettingCard>
          </div>
        )}
      </Async>
    </>
  );
}
