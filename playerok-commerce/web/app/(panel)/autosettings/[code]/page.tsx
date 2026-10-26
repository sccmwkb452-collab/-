"use client";

import { ArrowLeft, Eye, FlaskConical, RotateCcw, Save } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import { Async, CopyButton, Empty, Notice, PageHeader } from "@/components/app/blocks";
import { ConfirmAction } from "@/components/app/confirm";
import { StatusBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { dt } from "@/lib/format";
import { useDraft } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { INTEGRATION_STATE, LOG_RESULT } from "@/lib/status";
import type { AutoDetail, AutoField } from "@/lib/types";

type TestResult = { ok: boolean; problems: string[]; texts: Record<string, string>; integration: { label: string } };

function FieldInput({
  field,
  value,
  onChange,
  disabled,
  variables,
}: {
  field: AutoField;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
  variables: Record<string, string>;
}) {
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  switch (field.type) {
    case "bool":
      return (
        <label className="flex items-start gap-3">
          <Switch checked={Boolean(value)} onCheckedChange={onChange} disabled={disabled} className="mt-0.5" />
          <span>
            <span className="block text-sm font-medium">{field.label}</span>
            {field.help && <span className="text-xs text-muted-foreground">{field.help}</span>}
          </span>
        </label>
      );
    case "int":
      return (
        <Field
          label={field.label}
          hint={[field.help, field.min !== null && field.max !== null ? `от ${field.min} до ${field.max}` : ""].filter(Boolean).join(" · ")}
        >
          <Input inputMode="numeric" value={String(value ?? "")} onChange={(e) => onChange(e.target.value.replace(/[^\d-]/g, ""))} disabled={disabled} />
        </Field>
      );
    case "choice":
      return (
        <Field label={field.label} hint={field.help}>
          <NativeSelect value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
            {field.choices.map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </Field>
      );
    case "multichoice": {
      const selected = Array.isArray(value) ? (value as string[]) : [];
      return (
        <Field label={field.label} hint={field.help || "Ничего не выбрано — для всех"}>
          <div className="flex flex-wrap gap-1.5">
            {field.choices.map(([v, label]) => {
              const on = selected.includes(v);
              return (
                <button
                  key={v}
                  type="button"
                  disabled={disabled}
                  aria-pressed={on}
                  onClick={() => onChange(on ? selected.filter((x) => x !== v) : [...selected, v])}
                  className={`rounded-full border px-2.5 py-1 text-xs disabled:opacity-60 ${on ? "border-primary bg-primary/15 text-foreground" : "border-border text-muted-foreground hover:text-foreground"}`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </Field>
      );
    }
    case "list":
      return (
        <Field label={field.label} hint={field.help || "По одному значению в строке"}>
          <Textarea
            value={Array.isArray(value) ? (value as string[]).join("\n") : String(value ?? "")}
            onChange={(e) => onChange(e.target.value.split("\n"))}
            disabled={disabled}
            className="min-h-24"
          />
        </Field>
      );
    case "template":
      return (
        <Field label={field.label} hint={field.help}>
          <Textarea ref={textareaRef} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} disabled={disabled} className="min-h-28" />
          {!disabled && (
            <div className="mt-1 flex flex-wrap gap-1">
              {Object.entries(variables).map(([name, desc]) => (
                <button
                  key={name}
                  type="button"
                  title={desc}
                  onClick={() => {
                    const el = textareaRef.current;
                    const text = String(value ?? "");
                    const pos = el?.selectionStart ?? text.length;
                    onChange(`${text.slice(0, pos)}{${name}}${text.slice(pos)}`);
                  }}
                  className="rounded border border-border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground hover:border-border-strong hover:text-foreground"
                >
                  {`{${name}}`}
                </button>
              ))}
            </div>
          )}
        </Field>
      );
    default:
      return (
        <Field label={field.label} hint={field.help}>
          <Input value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} disabled={disabled} />
        </Field>
      );
  }
}

export default function AutosettingPage() {
  const { code } = useParams<{ code: string }>();
  const state = useApi<AutoDetail>(`/autosettings/${code}`);
  const { can } = useSession();
  const { busy, run } = useAction();
  const [config, setConfig] = useDraft(state.data, (d) => ({ ...d.config }));
  const [preview, setPreview] = React.useState<Record<string, string>>({});
  const [test, setTest] = React.useState<TestResult>();

  return (
    <Async state={state} rows={10}>
      {(d) => {
        const manage = can("autosettings.manage");
        const unavailable = d.integration.state === "unavailable";
        const dirty = config && JSON.stringify(config) !== JSON.stringify(d.config);
        return (
          <>
            <Link href="/autosettings" className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground">
              <ArrowLeft className="size-4" /> Все автонастройки
            </Link>
            <PageHeader
              title={d.label}
              description={d.description}
              actions={
                <>
                  <Button
                    size="sm"
                    loading={busy === "test"}
                    onClick={async () => {
                      const r = await run("test", () => api.post<TestResult>(`/autosettings/${code}/test`));
                      if (r) {
                        setTest(r);
                        state.reload();
                      }
                    }}
                  >
                    <FlaskConical /> Тест
                  </Button>
                  {manage && (
                    <ConfirmAction
                      label="Сбросить"
                      icon={<RotateCcw />}
                      title="Вернуть значения по умолчанию?"
                      description="Тексты и параметры станут стандартными. Включена функция или нет — не изменится."
                      onConfirm={async () => {
                        const r = await run("reset", () => api.post(`/autosettings/${code}/reset`), "Сброшено к значениям по умолчанию");
                        if (r) state.reload();
                        return r;
                      }}
                    />
                  )}
                  <label className="ml-1 flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-[13px]">
                    <Switch
                      checked={d.enabled}
                      disabled={unavailable || !manage || busy !== null}
                      onCheckedChange={async (v) => {
                        const r = await run("toggle", () => api.post(`/autosettings/${code}/toggle`, { enabled: v }), v ? "Включено" : "Выключено");
                        if (r) state.reload();
                      }}
                    />
                    {d.enabled ? "Включено" : "Выключено"}
                  </label>
                </>
              }
            >
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge map={INTEGRATION_STATE} value={d.integration.state} />
                <span className="text-xs text-muted-foreground">
                  Изменено {dt(d.updated_at)}
                  {d.updated_by ? ` · ${d.updated_by}` : ""}
                  {d.last_run_at ? ` · последний запуск ${dt(d.last_run_at)}` : ""}
                </span>
              </div>
            </PageHeader>

            <div className="mb-6 flex flex-col gap-3">
              {d.stopped && (
                <Notice tone="danger" title="Автоматизация остановлена аварийно">
                  Функция не выполняется, даже если включена. Снимите остановку в разделе «Безопасность».
                </Notice>
              )}
              {d.integration.state !== "available" && (
                <Notice tone={unavailable ? "danger" : "warning"} title={unavailable ? "Интеграция недоступна" : "Режим подсказок оператору"}>
                  <span className="whitespace-pre-line">{d.integration.reason}</span>
                  {d.integration.assist && <span className="mt-1 block">{d.integration.assist}</span>}
                </Notice>
              )}
              {d.safety && <Notice tone="info" title="Ограничения безопасности">{d.safety}</Notice>}
              {d.last_error && (
                <Notice tone="danger" title="Последняя ошибка">
                  {d.last_error}
                </Notice>
              )}
            </div>

            {test && (
              <Card className="mb-6">
                <CardHeader title={test.ok ? "Тест пройден" : "Тест нашёл проблемы"} description={`Ничего не отправлялось. ${test.integration.label}`} />
                <CardBody className="flex flex-col gap-3">
                  {test.problems.length > 0 && (
                    <ul className="list-disc pl-5 text-[13px] text-red-300">
                      {test.problems.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ul>
                  )}
                  {Object.entries(test.texts).map(([label, text]) => (
                    <div key={label} className="rounded-md border border-border bg-surface-2/40 p-3">
                      <p className="mb-1 text-xs text-muted-foreground">{label}</p>
                      <p className="text-sm whitespace-pre-wrap">{text}</p>
                    </div>
                  ))}
                </CardBody>
              </Card>
            )}

            <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
              <Card>
                <CardHeader title="Параметры и тексты" description="Переменные в фигурных скобках заменяются данными заказа" />
                <CardBody>
                  {d.fields.length === 0 ? (
                    <p className="text-sm text-muted-foreground">У этой функции нет настраиваемых параметров.</p>
                  ) : (
                    config && (
                      <div className="flex flex-col gap-5">
                        {d.fields.map((f) => (
                          <div key={f.name}>
                            <FieldInput
                              field={f}
                              value={config[f.name]}
                              onChange={(v) => setConfig({ ...config, [f.name]: v })}
                              disabled={!manage}
                              variables={d.variables}
                            />
                            {f.type === "template" && (
                              <div className="mt-2">
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  loading={busy === `p-${f.name}`}
                                  onClick={async () => {
                                    const r = await run(`p-${f.name}`, () => api.post<{ text: string }>(`/autosettings/${code}/preview`, { field: f.name }));
                                    if (r) setPreview({ ...preview, [f.name]: r.text });
                                  }}
                                >
                                  <Eye /> Предпросмотр сохранённого текста
                                </Button>
                                {preview[f.name] !== undefined && (
                                  <div className="mt-2 rounded-md border border-border bg-surface-2/40 p-3">
                                    <p className="text-sm whitespace-pre-wrap">{preview[f.name] || "— пусто —"}</p>
                                    {preview[f.name] && <CopyButton value={preview[f.name]} className="mt-2" />}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                        {manage && (
                          <div className="flex gap-2">
                            <Button
                              variant="primary"
                              disabled={!dirty}
                              loading={busy === "save"}
                              onClick={async () => {
                                const r = await run("save", () => api.put(`/autosettings/${code}`, { values: config }), "Сохранено");
                                if (r) {
                                  setPreview({});
                                  state.reload();
                                }
                              }}
                            >
                              <Save /> Сохранить
                            </Button>
                            <Button disabled={!dirty} onClick={() => setConfig({ ...d.config })}>
                              Отменить изменения
                            </Button>
                          </div>
                        )}
                      </div>
                    )
                  )}
                </CardBody>
              </Card>

              <Card>
                <CardHeader title="История и ошибки" description="Последние запуски, подсказки и изменения" />
                {d.history.length ? (
                  <ul className="divide-y divide-border">
                    {d.history.map((h, i) => (
                      <li key={i} className="px-5 py-3 text-[13px]">
                        <div className="flex items-center justify-between gap-2">
                          <StatusBadge map={LOG_RESULT} value={h.result} />
                          <span className="text-xs text-muted-foreground">{dt(h.at)}</span>
                        </div>
                        <p className="mt-1">
                          <span className="text-muted-foreground">{h.action}</span>
                          {h.message ? ` — ${h.message}` : ""}
                        </p>
                        {h.order_id && (
                          <Link href={`/orders/${h.order_id}`} className="text-xs text-highlight hover:underline">
                            заказ
                          </Link>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty title="Записей нет" />
                )}
              </Card>
            </div>
          </>
        );
      }}
    </Async>
  );
}
