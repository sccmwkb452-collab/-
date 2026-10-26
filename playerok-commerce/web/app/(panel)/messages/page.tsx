"use client";

import { Bot, Check, FlaskConical, MessageSquare, Pencil, Plus, Search, Star, Trash2, UserRound } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Async, CopyButton, Empty, Notice, PageHeader, Pager } from "@/components/app/blocks";
import { ConfirmAction } from "@/components/app/confirm";
import { StatusBadge, ToneBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { dt } from "@/lib/format";
import { useDebounced, usePage } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { MESSAGE_STATUS, ORDER_STATUS } from "@/lib/status";
import type { Integration, Message, Paged, Review } from "@/lib/types";

type Rule = {
  id: number;
  name: string;
  priority: number;
  enabled: boolean;
  match_type: "keywords" | "regex";
  patterns: string[];
  order_statuses: string[];
  action: "reply" | "escalate" | "status";
  reply_template: string;
  hits: number;
  last_hit_at: string | null;
};

const RULE_ACTION: Record<string, string> = {
  reply: "Подготовить ответ",
  escalate: "Передать оператору",
  status: "Ответить статусом заказа",
};

function RecordDialog({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [text, setText] = React.useState("");
  const [buyer, setBuyer] = React.useState("");
  const [orderRef, setOrderRef] = React.useState("");
  const [result, setResult] = React.useState<Message>();
  const { busy, run } = useAction();
  function close(v: boolean) {
    setOpen(v);
    if (!v) {
      setResult(undefined);
      setText("");
      setBuyer("");
      setOrderRef("");
    }
  }
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogTrigger asChild>
        <Button variant="primary">
          <Plus /> Записать сообщение
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Сообщение покупателя"
        description="Перенесите текст из чата PlayerOK. Автоответчик подберёт ответ — отправьте его вручную кнопкой «Скопировать»."
        footer={
          result ? (
            <Button onClick={() => close(false)}>Готово</Button>
          ) : (
            <>
              <Button onClick={() => close(false)}>Отмена</Button>
              <Button
                variant="primary"
                disabled={!text.trim()}
                loading={busy === "rec"}
                onClick={async () => {
                  const r = await run("rec", () =>
                    api.post<Message>("/messages", { text, buyer_name: buyer.trim() || null, order_ref: orderRef.trim() || null }),
                  );
                  if (r) {
                    setResult(r);
                    onDone();
                  }
                }}
              >
                Записать
              </Button>
            </>
          )
        }
      >
        {result ? (
          <div className="flex flex-col gap-3">
            <StatusBadge map={MESSAGE_STATUS} value={result.status} />
            {result.problem_hint && <Notice tone="warning">{result.problem_hint}</Notice>}
            {result.suggested_reply ? (
              <>
                <p className="rounded-md border border-border bg-surface-2 p-3 text-sm whitespace-pre-wrap">{result.suggested_reply}</p>
                <CopyButton value={result.suggested_reply} className="self-start" />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Ответ не подготовлен: автоответчик выключен или подходящего правила нет. Ответьте покупателю сами.</p>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <Field label="Текст сообщения">
              <Textarea value={text} onChange={(e) => setText(e.target.value)} autoFocus className="min-h-28" />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Покупатель (ник)">
                <Input value={buyer} onChange={(e) => setBuyer(e.target.value)} />
              </Field>
              <Field label="Заказ" hint="Номер PO-000123 или номер сделки PlayerOK">
                <Input value={orderRef} onChange={(e) => setOrderRef(e.target.value)} />
              </Field>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function MessagesTab() {
  const { can } = useSession();
  const [status, setStatus] = React.useState("");
  const [q, setQ] = React.useState("");
  const query = useDebounced(q);
  const [page, setPage] = usePage(JSON.stringify([status, query]));
  const qs = new URLSearchParams({ page: String(page), per_page: "20" });
  if (status) qs.set("status", status);
  if (query) qs.set("q", query);
  const state = useApi<Paged<Message> & { integration: Integration }>(`/messages?${qs}`);
  const { busy, run } = useAction();

  async function setMsgStatus(id: number, value: string) {
    const r = await run(`${id}`, () => api.post(`/messages/${id}/status`, { status: value }), "Статус обновлён");
    if (r) state.reload();
  }

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Текст или покупатель" className="pl-9" />
        </div>
        <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} className="w-60" aria-label="Статус">
          <option value="">Все сообщения</option>
          {Object.entries(MESSAGE_STATUS).map(([k, s]) => (
            <option key={k} value={k}>
              {s.label}
            </option>
          ))}
        </NativeSelect>
        {can("messages.manage") && <RecordDialog onDone={state.reload} />}
      </div>
      <Async state={state} rows={6}>
        {(d) =>
          d.items.length ? (
            <>
              <ul className="divide-y divide-border">
                {d.items.map((m) => (
                  <li key={m.id} className="px-5 py-4">
                    <div className="flex flex-wrap items-center gap-2 text-[13px]">
                      <span className="flex items-center gap-1.5 font-medium">
                        {m.direction === "out" ? <Bot className="size-4 text-subtle" /> : <UserRound className="size-4 text-subtle" />}
                        {m.direction === "out" ? "Ответ магазина" : m.buyer_name || "Покупатель"}
                      </span>
                      <StatusBadge map={MESSAGE_STATUS} value={m.status} />
                      {m.order_id && (
                        <Link href={`/orders/${m.order_id}`} className="text-highlight hover:underline">
                          заказ
                        </Link>
                      )}
                      <span className="ml-auto text-xs text-muted-foreground">{dt(m.received_at)}</span>
                    </div>
                    <p className="mt-2 text-sm whitespace-pre-wrap">{m.text}</p>
                    {m.problem_hint && (
                      <Notice tone="warning" className="mt-2">
                        {m.problem_hint}
                      </Notice>
                    )}
                    {m.suggested_reply && (
                      <div className="mt-3 rounded-md border border-border bg-surface-2/50 p-3">
                        <p className="mb-1 text-xs text-muted-foreground">Подготовленный ответ — отправьте в чате PlayerOK:</p>
                        <p className="text-sm whitespace-pre-wrap">{m.suggested_reply}</p>
                        <CopyButton value={m.suggested_reply} className="mt-2" />
                      </div>
                    )}
                    {can("messages.manage") && m.direction === "in" && m.status !== "handled" && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button size="sm" loading={busy === `${m.id}`} onClick={() => setMsgStatus(m.id, "handled")}>
                          <Check /> Обработано
                        </Button>
                        {m.status !== "escalated" && (
                          <Button size="sm" variant="ghost" onClick={() => setMsgStatus(m.id, "escalated")}>
                            Нужен оператор
                          </Button>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
              <Pager page={d.page} total={d.total} perPage={d.per_page} onPage={setPage} />
            </>
          ) : (
            <Empty title="Сообщений нет" icon={MessageSquare}>
              {status || query ? "Измените фильтр." : "Сообщения покупателей появятся здесь после того, как вы запишете их в боте или в панели."}
            </Empty>
          )
        }
      </Async>
    </Card>
  );
}

function RuleDialog({ rule, onDone, trigger }: { rule?: Rule; onDone: () => void; trigger: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [v, setV] = React.useState({
    name: rule?.name ?? "",
    priority: String(rule?.priority ?? 100),
    enabled: rule?.enabled ?? true,
    match_type: rule?.match_type ?? "keywords",
    patterns: (rule?.patterns ?? []).join("\n"),
    order_statuses: rule?.order_statuses ?? [],
    action: rule?.action ?? "reply",
    reply_template: rule?.reply_template ?? "",
  });
  const { busy, run } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent
        title={rule ? "Правило автоответчика" : "Новое правило"}
        description="Правила проверяются по приоритету (меньше — раньше). Ответ не может обещать завершение заказа, если он не завершён."
        className="max-w-2xl"
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              loading={busy === "save"}
              disabled={!v.name.trim() || !v.patterns.trim()}
              onClick={async () => {
                const body = {
                  ...v,
                  priority: Number(v.priority) || 100,
                  patterns: v.patterns.split("\n").map((x) => x.trim()).filter(Boolean),
                };
                const r = await run(
                  "save",
                  () => (rule ? api.put(`/autoresponder/rules/${rule.id}`, body) : api.post("/autoresponder/rules", body)),
                  "Правило сохранено",
                );
                if (r) {
                  setOpen(false);
                  onDone();
                }
              }}
            >
              Сохранить
            </Button>
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Название" className="sm:col-span-2">
            <Input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} />
          </Field>
          <Field label="Тип совпадения">
            <NativeSelect value={v.match_type} onChange={(e) => setV({ ...v, match_type: e.target.value as Rule["match_type"] })}>
              <option value="keywords">Ключевые слова</option>
              <option value="regex">Регулярное выражение</option>
            </NativeSelect>
          </Field>
          <Field label="Приоритет">
            <Input inputMode="numeric" value={v.priority} onChange={(e) => setV({ ...v, priority: e.target.value.replace(/\D/g, "") })} />
          </Field>
          <Field label={v.match_type === "regex" ? "Выражения — по одному в строке" : "Слова и фразы — по одной в строке"} className="sm:col-span-2">
            <Textarea value={v.patterns} onChange={(e) => setV({ ...v, patterns: e.target.value })} className="min-h-24 font-mono text-[13px]" />
          </Field>
          <Field label="Действие">
            <NativeSelect value={v.action} onChange={(e) => setV({ ...v, action: e.target.value as Rule["action"] })}>
              {Object.entries(RULE_ACTION).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <label className="flex items-center gap-2 self-end pb-2 text-sm">
            <Switch checked={v.enabled} onCheckedChange={(x) => setV({ ...v, enabled: x })} /> Включено
          </label>
          <Field label="Только для заказов в статусах" hint="Пусто — для любых сообщений" className="sm:col-span-2">
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(ORDER_STATUS).map(([k, s]) => {
                const on = v.order_statuses.includes(k);
                return (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setV({ ...v, order_statuses: on ? v.order_statuses.filter((x) => x !== k) : [...v.order_statuses, k] })}
                    className={`rounded-full border px-2.5 py-1 text-xs ${on ? "border-primary bg-primary/15 text-foreground" : "border-border text-muted-foreground hover:text-foreground"}`}
                    aria-pressed={on}
                  >
                    {s.label}
                  </button>
                );
              })}
            </div>
          </Field>
          {v.action !== "escalate" && (
            <Field label="Текст ответа" hint="Переменные: {buyer}, {order_number}, {product}, {status}, {delivery_time}, {instructions}" className="sm:col-span-2">
              <Textarea value={v.reply_template} onChange={(e) => setV({ ...v, reply_template: e.target.value })} />
            </Field>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RulesTab() {
  const { can } = useSession();
  const state = useApi<{ items: Rule[] }>("/autoresponder/rules");
  const [text, setText] = React.useState("");
  const [orderRef, setOrderRef] = React.useState("");
  const [test, setTest] = React.useState<{ rule: string | null; action: string; reply: string | null; reason: string }>();
  const { busy, run } = useAction();
  const manage = can("autosettings.manage");
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
      <Card>
        <CardHeader
          title="Правила автоответчика"
          description="Работают в режиме подсказок: ответ готовится, но отправляете его вы"
          actions={manage && <RuleDialog onDone={state.reload} trigger={<Button size="sm" variant="primary"><Plus /> Правило</Button>} />}
        />
        <Async state={state}>
          {(d) =>
            d.items.length ? (
              <ul className="divide-y divide-border">
                {d.items.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-start justify-between gap-3 px-5 py-3.5">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{r.name}</span>
                        {r.enabled ? <ToneBadge tone="success">Включено</ToneBadge> : <ToneBadge tone="neutral">Выключено</ToneBadge>}
                        <span className="text-xs text-muted-foreground">
                          приоритет {r.priority} · {RULE_ACTION[r.action]} · срабатываний {r.hits}
                        </span>
                      </div>
                      <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{r.patterns.join(" · ")}</p>
                    </div>
                    {manage && (
                      <div className="flex gap-1">
                        <RuleDialog rule={r} onDone={state.reload} trigger={<Button size="icon-sm" variant="ghost" aria-label="Изменить"><Pencil /></Button>} />
                        <ConfirmAction
                          label=""
                          icon={<Trash2 />}
                          variant="ghost"
                          size="icon-sm"
                          title={`Удалить правило «${r.name}»?`}
                          confirmVariant="danger"
                          confirmLabel="Удалить"
                          onConfirm={async () => {
                            const x = await run("del", () => api.del(`/autoresponder/rules/${r.id}`), "Правило удалено");
                            if (x) state.reload();
                            return x;
                          }}
                        />
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title="Правил нет" />
            )
          }
        </Async>
      </Card>
      <Card>
        <CardHeader title="Проверить на тексте" description="Ничего не отправляется и не сохраняется" />
        <CardBody className="flex flex-col gap-3">
          <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Например: когда придёт код?" />
          <Input value={orderRef} onChange={(e) => setOrderRef(e.target.value)} placeholder="Заказ (необязательно)" />
          <Button
            disabled={!text.trim()}
            loading={busy === "test"}
            onClick={async () => {
              const r = await run("test", () => api.post<typeof test>("/autoresponder/test", { text, order_ref: orderRef.trim() || null }));
              if (r) setTest(r);
            }}
          >
            <FlaskConical /> Проверить
          </Button>
          {test && (
            <div className="rounded-md border border-border bg-surface-2/50 p-3 text-sm">
              <p className="text-xs text-muted-foreground">
                Правило: {test.rule ?? "не найдено"} · {RULE_ACTION[test.action] ?? test.action}
              </p>
              {test.reply && <p className="mt-2 whitespace-pre-wrap">{test.reply}</p>}
              {test.reason && <p className="mt-2 text-xs text-muted-foreground">{test.reason}</p>}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function ReviewsTab() {
  const state = useApi<{ items: Review[] }>("/reviews");
  return (
    <Card>
      <CardHeader title="Отзывы" description="Вносятся вручную со страницы заказа: PlayerOK не отдаёт отзывы без API" />
      <Async state={state}>
        {(d) =>
          d.items.length ? (
            <ul className="divide-y divide-border">
              {d.items.map((r) => (
                <li key={r.id} className="px-5 py-3.5">
                  <div className="flex flex-wrap items-center gap-2 text-[13px]">
                    <span className="text-yellow-300">{r.rating ? "★".repeat(r.rating) + "☆".repeat(5 - r.rating) : "без оценки"}</span>
                    <ToneBadge tone={r.sentiment === "positive" ? "success" : r.sentiment === "negative" ? "danger" : "neutral"}>
                      {r.sentiment === "positive" ? "Положительный" : r.sentiment === "negative" ? "Отрицательный" : "Нейтральный"}
                    </ToneBadge>
                    {r.order_id && (
                      <Link href={`/orders/${r.order_id}`} className="text-highlight hover:underline">
                        заказ
                      </Link>
                    )}
                    <span className="ml-auto text-xs text-muted-foreground">{dt(r.created_at)}</span>
                  </div>
                  {r.text && <p className="mt-1.5 text-sm">{r.text}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="Отзывов нет" icon={Star} />
          )
        }
      </Async>
    </Card>
  );
}

export default function MessagesPage() {
  const integration = useApi<Integration>("/marketplace");
  const caps = integration.data?.capabilities;
  return (
    <>
      <PageHeader title="Сообщения покупателей" description="Входящие сообщения, подготовленные ответы, отзывы и правила автоответчика." />
      {caps && !caps.fetch_messages?.available && (
        <Notice tone="warning" title="Чаты PlayerOK не подключены" className="mb-5">
          {caps.fetch_messages?.reason} {caps.send_messages?.reason}
        </Notice>
      )}
      <Tabs defaultValue="inbox">
        <TabsList>
          <TabsTrigger value="inbox">
            <MessageSquare /> Сообщения
          </TabsTrigger>
          <TabsTrigger value="rules">
            <Bot /> Автоответчик
          </TabsTrigger>
          <TabsTrigger value="reviews">
            <Star /> Отзывы
          </TabsTrigger>
        </TabsList>
        <TabsContent value="inbox">
          <MessagesTab />
        </TabsContent>
        <TabsContent value="rules">
          <RulesTab />
        </TabsContent>
        <TabsContent value="reviews">
          <ReviewsTab />
        </TabsContent>
      </Tabs>
    </>
  );
}
