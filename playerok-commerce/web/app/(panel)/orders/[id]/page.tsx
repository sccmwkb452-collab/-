"use client";

import {
  ArrowLeft,
  CheckCircle2,
  Eye,
  EyeOff,
  FlaskConical,
  KeyRound,
  MessageSquare,
  Pause,
  Play,
  RefreshCw,
  ShoppingBag,
  Star,
  StickyNote,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import { Async, CopyButton, Empty, KV, Notice, PageHeader } from "@/components/app/blocks";
import { ConfirmAction } from "@/components/app/confirm";
import { StatusBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, NativeSelect, Textarea } from "@/components/ui/input";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { dt, money } from "@/lib/format";
import { useSession } from "@/lib/session";
import { CODE_STATUS, DELIVERY_TYPE, MESSAGE_STATUS, ORDER_STATUS, SUPPLIER_ORDER_STATUS } from "@/lib/status";
import type { Code, Message, Order, Review, SupplierOrder } from "@/lib/types";

type Detail = {
  order: Order;
  fulfilment: { item_id: number; codes: Code[]; supplier_order: SupplierOrder | null }[];
  events: { at: string; from: string | null; to: string | null; actor: string | null; message: string | null }[];
  messages: Message[];
  reviews: Review[];
  transitions: string[];
};

const FINAL = ["completed", "refund", "cancelled"];

function RevealCode({ code }: { code: Code }) {
  const [plain, setPlain] = React.useState<string>();
  const { busy, run } = useAction();
  React.useEffect(() => {
    if (!plain) return;
    const t = setTimeout(() => setPlain(undefined), 60_000);
    return () => clearTimeout(t);
  }, [plain]);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <code className="rounded bg-surface-2 px-2 py-1 font-mono text-[13px]">{plain ?? code.mask}</code>
      <StatusBadge map={CODE_STATUS} value={code.status} />
      {code.is_test && <span className="text-xs text-yellow-300">тестовый</span>}
      {plain ? (
        <>
          <CopyButton value={plain} />
          <Button size="sm" variant="ghost" onClick={() => setPlain(undefined)}>
            <EyeOff /> Скрыть
          </Button>
        </>
      ) : (
        <Button
          size="sm"
          variant="ghost"
          loading={busy === "reveal"}
          onClick={async () => {
            const r = await run("reveal", () => api.post<{ code: string }>(`/codes/${code.id}/reveal`));
            if (r) setPlain(r.code);
          }}
        >
          <Eye /> Показать
        </Button>
      )}
    </div>
  );
}

function AddCodes({ orderId, itemId, onDone }: { orderId: number; itemId: number; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [codes, setCodes] = React.useState("");
  const [cost, setCost] = React.useState("");
  const { busy, run } = useAction();
  const list = codes.split("\n").map((c) => c.trim()).filter(Boolean);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <KeyRound /> Добавить коды
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Коды для этой позиции"
        description="Коды шифруются сразу при сохранении. Повторяющиеся коды отклоняются."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              disabled={!list.length}
              loading={busy === "codes"}
              onClick={async () => {
                const r = await run(
                  "codes",
                  () => api.post(`/orders/${orderId}/codes`, { item_id: itemId, codes: list, unit_cost: cost.replace(",", ".") || null }),
                  "Коды сохранены",
                );
                if (r) {
                  setOpen(false);
                  setCodes("");
                  onDone();
                }
              }}
            >
              Сохранить {list.length ? `(${list.length})` : ""}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="Коды — по одному в строке">
            <Textarea value={codes} onChange={(e) => setCodes(e.target.value)} className="min-h-32 font-mono" autoComplete="off" spellCheck={false} />
          </Field>
          <Field label="Себестоимость за штуку, ₽" hint="Если не указать, возьмётся из закупки или карточки товара">
            <Input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RecordMessage({ orderNumber, onDone }: { orderNumber: string; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [text, setText] = React.useState("");
  const [result, setResult] = React.useState<Message>();
  const { busy, run } = useAction();
  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setResult(undefined); setText(""); } }}>
      <DialogTrigger asChild>
        <Button size="sm">
          <MessageSquare /> Записать сообщение
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Сообщение покупателя"
        description="Скопируйте текст из чата PlayerOK — автоответчик подберёт ответ, который нужно отправить вручную."
        footer={
          result ? (
            <Button onClick={() => setOpen(false)}>Готово</Button>
          ) : (
            <>
              <Button onClick={() => setOpen(false)}>Отмена</Button>
              <Button
                variant="primary"
                disabled={!text.trim()}
                loading={busy === "msg"}
                onClick={async () => {
                  const r = await run("msg", () => api.post<Message>("/messages", { text, order_ref: orderNumber }));
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
                <p className="text-[13px] text-muted-foreground">Предложенный ответ — отправьте его в чате PlayerOK:</p>
                <p className="rounded-md border border-border bg-surface-2 p-3 text-sm whitespace-pre-wrap">{result.suggested_reply}</p>
                <CopyButton value={result.suggested_reply} className="self-start" />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Ответ не подготовлен: автоответчик выключен или подходящего правила нет. Ответьте покупателю сами.</p>
            )}
          </div>
        ) : (
          <Textarea value={text} onChange={(e) => setText(e.target.value)} autoFocus className="min-h-32" />
        )}
      </DialogContent>
    </Dialog>
  );
}

function RecordReview({ orderNumber, onDone }: { orderNumber: string; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [rating, setRating] = React.useState("5");
  const [text, setText] = React.useState("");
  const { busy, run } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Star /> Записать отзыв
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Отзыв покупателя"
        description="Отзыв с PlayerOK переносится вручную: напоминания об отзыве по этому заказу прекратятся."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              loading={busy === "review"}
              onClick={async () => {
                const r = await run("review", () => api.post("/reviews", { order_ref: orderNumber, rating: Number(rating), text }), "Отзыв записан");
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
        <div className="flex flex-col gap-4">
          <Field label="Оценка">
            <NativeSelect value={rating} onChange={(e) => setRating(e.target.value)}>
              {[5, 4, 3, 2, 1].map((n) => (
                <option key={n} value={n}>
                  {"★".repeat(n)} ({n})
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Текст отзыва">
            <Textarea value={text} onChange={(e) => setText(e.target.value)} />
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function OrderPage() {
  const { id } = useParams<{ id: string }>();
  const state = useApi<Detail>(`/orders/${id}`);
  const { can } = useSession();
  const { busy, run } = useAction();

  async function act(action: string, extra: Record<string, unknown> = {}, success = "Готово") {
    const r = await run(action, () => api.post<{ order: Order }>(`/orders/${id}/action`, { action, ...extra }), success);
    if (r) state.reload();
    return r;
  }

  return (
    <Async state={state} rows={10}>
      {(d) => {
        const o = d.order;
        const manage = can("orders.manage");
        const open = !FINAL.includes(o.status);
        const hasCodeItems = o.items.some((i) => i.delivery_type === "code");
        return (
          <>
            <Link href="/orders" className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground">
              <ArrowLeft className="size-4" /> Все заказы
            </Link>
            <PageHeader
              title={
                <span className="flex flex-wrap items-center gap-3">
                  Заказ {o.number}
                  <StatusBadge map={ORDER_STATUS} value={o.status} />
                  {o.is_test && (
                    <span className="inline-flex items-center gap-1 text-sm font-normal text-yellow-300">
                      <FlaskConical className="size-4" /> тестовый
                    </span>
                  )}
                </span>
              }
              description={o.status_reason ?? undefined}
              actions={
                <Button size="sm" onClick={state.reload}>
                  <RefreshCw /> Обновить
                </Button>
              }
            />

            {o.status === "new" && !o.automation_paused && (
              <Notice className="mb-5" title="Заказ в очереди на обработку">
                Проверку, закупку и выдачу выполняет воркер в фоне. Если статус долго не меняется, проверьте на главной панели, что воркер работает.
              </Notice>
            )}

            {o.needs_attention && (
              <Notice tone="warning" title="Заказ ждёт вашего решения" className="mb-5">
                {o.status_reason ?? "Автоматика остановилась на этом заказе."}
              </Notice>
            )}

            {manage && (
              <Card className="mb-6">
                <CardHeader title="Действия" description="Доступны только допустимые для текущего статуса. Всё записывается в историю." />
                <CardBody className="flex flex-wrap gap-2">
                  {o.status === "pending_review" && (
                    <Button variant="success" size="sm" loading={busy === "continue"} onClick={() => act("continue", {}, "Обработка продолжена")}>
                      <Play /> Продолжить обработку
                    </Button>
                  )}
                  {o.status === "pending_confirmation" && can("suppliers.purchase") && (
                    <ConfirmAction
                      label="Подтвердить закупку"
                      icon={<ShoppingBag />}
                      variant="success"
                      title="Закупить у поставщика?"
                      description="Система выполнит закупку через API поставщика в пределах лимитов. В тестовом режиме покупка только имитируется."
                      confirmLabel="Закупить"
                      onConfirm={() => act("confirm_purchase", {}, "Закупка запущена")}
                    />
                  )}
                  {o.status === "pending_confirmation" && (
                    <Button size="sm" loading={busy === "manual_purchase"} onClick={() => act("manual_purchase", {}, "Переведено в ручную закупку")}>
                      Куплю вручную
                    </Button>
                  )}
                  {o.status === "pending_purchase" && (
                    <ConfirmAction
                      label="Закуплено вручную"
                      icon={<CheckCircle2 />}
                      variant="success"
                      title="Отметить закупку"
                      description="Укажите фактическую стоимость закупки — она пойдёт в расчёт прибыли."
                      input={{ label: "Стоимость закупки, ₽", type: "text", placeholder: "например, 812.50" }}
                      onConfirm={(v) => act("mark_purchased", { cost_rub: v ? v.replace(",", ".") : null }, "Закупка отмечена")}
                    />
                  )}
                  {o.status === "processing" && (
                    <Button size="sm" loading={busy === "poll"} onClick={() => act("poll", {}, "Статус у поставщика проверен")}>
                      <RefreshCw /> Проверить у поставщика
                    </Button>
                  )}
                  {o.status === "error" && (
                    <>
                      <Button variant="primary" size="sm" loading={busy === "retry"} onClick={() => act("retry", {}, "Повторная обработка запущена")}>
                        <RefreshCw /> Повторить
                      </Button>
                      <Button size="sm" loading={busy === "continue"} onClick={() => act("continue", {}, "Продолжено вручную")}>
                        Продолжить вручную
                      </Button>
                    </>
                  )}
                  {(o.status === "ready_for_delivery" || o.status === "dispute") && (
                    <ConfirmAction
                      label="Выдано покупателю"
                      variant="success"
                      title="Товар передан покупателю?"
                      description="Отметьте после того, как отправили код или выполнили услугу в чате PlayerOK."
                      onConfirm={() => act("delivered", {}, "Отмечено как выданное")}
                    />
                  )}
                  {(o.status === "delivered" || o.status === "dispute") && (
                    <ConfirmAction
                      label="Покупатель подтвердил"
                      variant="success"
                      title="Покупатель подтвердил получение на PlayerOK?"
                      description="Заказ будет завершён и учтён в выручке и прибыли."
                      onConfirm={() => act("buyer_confirmed", {}, "Заказ завершён")}
                    />
                  )}
                  {(open || o.status === "completed") && (
                    <>
                      <ConfirmAction
                        label="Спор"
                        title="Открыть спор"
                        input={{ label: "Причина", multiline: true, required: true }}
                        confirmVariant="danger"
                        onConfirm={(v) => act("dispute", { reason: v }, "Спор открыт")}
                      />
                      <ConfirmAction
                        label="Возврат"
                        variant="danger-soft"
                        title="Оформить возврат"
                        description="Выданные коды будут помечены, сумма учтена как возврат."
                        input={{ label: "Причина", multiline: true, required: true }}
                        confirmVariant="danger"
                        onConfirm={(v) => act("refund", { reason: v }, "Возврат оформлен")}
                      />
                    </>
                  )}
                  {open && (
                    <>
                      <ConfirmAction
                        label="Отменить"
                        variant="danger-soft"
                        title="Отменить заказ"
                        input={{ label: "Причина", multiline: true, required: true }}
                        confirmVariant="danger"
                        onConfirm={(v) => act("cancel", { reason: v }, "Заказ отменён")}
                      />
                      <Button
                        size="sm"
                        loading={busy === "pause" || busy === "resume"}
                        onClick={() => act(o.automation_paused ? "resume" : "pause", {}, o.automation_paused ? "Автоматизация возобновлена" : "Автоматизация на паузе")}
                      >
                        {o.automation_paused ? <Play /> : <Pause />} {o.automation_paused ? "Возобновить автоматизацию" : "Пауза автоматизации"}
                      </Button>
                    </>
                  )}
                  {d.transitions.length > 0 && (
                    <SetStatus transitions={d.transitions} onSet={(status, reason) => act("status", { status, reason }, "Статус изменён")} />
                  )}
                  <ConfirmAction
                    label="Заметка"
                    icon={<StickyNote />}
                    title="Заметка к заказу"
                    input={{ label: "Текст", multiline: true, required: true }}
                    onConfirm={(v) => act("note", { reason: v }, "Заметка добавлена")}
                  />
                  {can("messages.manage") && <RecordMessage orderNumber={o.number} onDone={state.reload} />}
                  {can("messages.manage") && <RecordReview orderNumber={o.number} onDone={state.reload} />}
                </CardBody>
              </Card>
            )}

            <div className="grid gap-6 xl:grid-cols-3">
              <div className="flex flex-col gap-6 xl:col-span-2">
                <Card>
                  <CardHeader title="Состав и выдача" />
                  <div className="divide-y divide-border">
                    {o.items.map((item) => {
                      const f = d.fulfilment.find((x) => x.item_id === item.id);
                      return (
                        <div key={item.id} className="px-5 py-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <Link href={`/products/${item.product_id}`} className="font-medium hover:text-highlight">
                                {item.product}
                              </Link>
                              <p className="text-xs text-muted-foreground">
                                {item.sku} · {DELIVERY_TYPE[item.delivery_type]} · выдано {item.fulfilled_quantity} из {item.quantity}
                              </p>
                            </div>
                            <div className="text-right text-sm tabular-nums">
                              <p>
                                {item.quantity} × {money(item.unit_price)}
                              </p>
                              <p className="text-xs text-muted-foreground">себестоимость {money(item.unit_cost)}</p>
                            </div>
                          </div>
                          {f?.supplier_order && (
                            <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-border bg-surface-2/50 px-3 py-2 text-[13px]">
                              <span className="text-muted-foreground">Закупка #{f.supplier_order.id}</span>
                              <StatusBadge map={SUPPLIER_ORDER_STATUS} value={f.supplier_order.status} />
                              {f.supplier_order.is_test && <span className="text-xs text-yellow-300">имитация</span>}
                              {f.supplier_order.cost_rub && <span>{money(f.supplier_order.cost_rub)}</span>}
                              {f.supplier_order.external_id && <span className="text-muted-foreground">ID {f.supplier_order.external_id}</span>}
                              {(f.supplier_order.last_error || f.supplier_order.message) && (
                                <span className="w-full text-xs text-muted-foreground">{f.supplier_order.last_error || f.supplier_order.message}</span>
                              )}
                            </div>
                          )}
                          {f && f.codes.length > 0 && (
                            <div className="mt-3 flex flex-col gap-2">
                              {f.codes.map((c) => (
                                <RevealCode key={c.id} code={c} />
                              ))}
                            </div>
                          )}
                          {manage && o.status === "pending_purchase" && item.delivery_type === "code" && hasCodeItems && (
                            <div className="mt-3">
                              <AddCodes orderId={o.id} itemId={item.id} onDone={state.reload} />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </Card>

                <Card>
                  <CardHeader title="История заказа" />
                  <CardBody>
                    {d.events.length ? (
                      <ol className="relative flex flex-col gap-4 border-l border-border pl-5">
                        {d.events.map((e, i) => (
                          <li key={i} className="relative">
                            <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-surface bg-primary" />
                            <div className="flex flex-wrap items-center gap-2 text-[13px]">
                              {e.to && <StatusBadge map={ORDER_STATUS} value={e.to} />}
                              <span className="text-muted-foreground">
                                {dt(e.at)} · {e.actor ?? "система"}
                              </span>
                            </div>
                            {e.message && <p className="mt-1 text-sm">{e.message}</p>}
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="text-sm text-muted-foreground">Событий пока нет.</p>
                    )}
                  </CardBody>
                </Card>
              </div>

              <div className="flex flex-col gap-6">
                <Card>
                  <CardHeader title="Деньги" />
                  <CardBody>
                    <KV
                      items={[
                        ["Сумма заказа", money(o.total_amount)],
                        ["Комиссия PlayerOK", money(o.marketplace_fee)],
                        ["Закупка", money(o.cost_total)],
                        [
                          "Чистая прибыль",
                          o.net_profit === null ? (
                            "считается после завершения"
                          ) : (
                            <span className={Number(o.net_profit) < 0 ? "text-red-300" : "text-green-300"}>{money(o.net_profit)}</span>
                          ),
                        ],
                      ]}
                    />
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="Сделка" />
                  <CardBody>
                    <KV
                      items={[
                        ["Сделка PlayerOK", o.external_id],
                        ["Покупатель", o.buyer_name],
                        ...Object.entries(o.buyer_data ?? {})
                          .filter(([, v]) => v)
                          .map(([k, v]) => [k === "link" ? "Данные для выдачи" : k, String(v)] as [string, string]),
                        ["Источник", o.source === "import" ? "импорт CSV" : o.source === "manual" ? "вручную" : o.source],
                        ["Создан", dt(o.placed_at)],
                        ["Выдан", dt(o.delivered_at)],
                        ["Подтверждён покупателем", dt(o.buyer_confirmed_at)],
                        ["Завершён", dt(o.completed_at)],
                      ]}
                    />
                    {o.notes && <p className="mt-4 rounded-md bg-surface-2 p-3 text-[13px] whitespace-pre-wrap">{o.notes}</p>}
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="Сообщения и отзывы" />
                  {d.messages.length || d.reviews.length ? (
                    <CardBody className="flex flex-col gap-3">
                      {d.reviews.map((r) => (
                        <div key={r.id} className="rounded-md border border-border p-3 text-sm">
                          <p className="text-yellow-300">{r.rating ? "★".repeat(r.rating) : "без оценки"}</p>
                          {r.text && <p className="mt-1">{r.text}</p>}
                        </div>
                      ))}
                      {d.messages.map((m) => (
                        <div key={m.id} className="rounded-md border border-border p-3 text-sm">
                          <div className="mb-1 flex items-center justify-between gap-2">
                            <StatusBadge map={MESSAGE_STATUS} value={m.status} />
                            <span className="text-xs text-muted-foreground">{dt(m.received_at)}</span>
                          </div>
                          <p className="whitespace-pre-wrap">{m.text}</p>
                          {m.suggested_reply && (
                            <div className="mt-2 rounded bg-surface-2 p-2 text-[13px] text-muted-foreground">
                              <p className="whitespace-pre-wrap">{m.suggested_reply}</p>
                              <CopyButton value={m.suggested_reply} className="mt-2" />
                            </div>
                          )}
                        </div>
                      ))}
                    </CardBody>
                  ) : (
                    <Empty title="Сообщений нет" icon={MessageSquare} />
                  )}
                </Card>
              </div>
            </div>
          </>
        );
      }}
    </Async>
  );
}

function SetStatus({ transitions, onSet }: { transitions: string[]; onSet: (status: string, reason: string) => Promise<unknown> }) {
  const [open, setOpen] = React.useState(false);
  const [status, setStatus] = React.useState(transitions[0]);
  const [reason, setReason] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">Сменить статус</Button>
      </DialogTrigger>
      <DialogContent
        title="Ручная смена статуса"
        description="Только допустимые переходы. Используйте, если на PlayerOK состояние сделки изменилось без системы."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={!reason.trim()}
              onClick={async () => {
                setBusy(true);
                const r = await onSet(status, reason.trim());
                setBusy(false);
                if (r) setOpen(false);
              }}
            >
              Сменить
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="Новый статус">
            <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)}>
              {transitions.map((t) => (
                <option key={t} value={t}>
                  {ORDER_STATUS[t]?.label ?? t}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Причина">
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} className="min-h-16" />
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}
