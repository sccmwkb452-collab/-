"use client";

import { Archive, ArrowLeft, CheckCircle2, ExternalLink, ImageIcon, Pause, Play, Save, Send, Wand2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import { Async, CopyButton, Empty, KV, Notice, PageHeader } from "@/components/app/blocks";
import { ConfirmAction } from "@/components/app/confirm";
import { StatusBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { dt, money } from "@/lib/format";
import { useDraft } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { LISTING_STATUS } from "@/lib/status";
import type { ExportPayload, ListingDetail } from "@/lib/types";

type PublishResult = { mode: "manual" | "test" | "published"; message: string; data?: ExportPayload; steps?: string[] };

const ACTIONS: Record<string, string> = {
  create: "Создано",
  prepare: "Подготовлено к публикации",
  preview_confirmed: "Предпросмотр подтверждён",
  publish_test: "Тестовая публикация",
  published: "Отмечено опубликованным",
  pause: "Приостановлено",
  resume: "Возобновлено",
  archive: "В архиве",
};

const FIELD_NAMES: Record<string, string> = {
  title: "название",
  description: "описание",
  price: "цена",
  quantity: "количество",
  marketplace_category: "категория",
  relist_on_complete: "повторная публикация",
};

function actionLabel(action: string) {
  if (action.startsWith("update:")) {
    const fields = action.slice(7).split(",").filter(Boolean);
    return `Изменено: ${fields.map((f) => FIELD_NAMES[f] ?? f).join(", ")}`;
  }
  return ACTIONS[action] ?? action;
}

function toDraft(l: ListingDetail) {
  return {
    title: l.title,
    description: l.description,
    price: l.price,
    quantity: String(l.quantity),
    marketplace_category: l.marketplace_category ?? "",
    relist_on_complete: l.relist_on_complete,
  };
}

function MarkPublished({ id, onDone }: { id: number; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [externalId, setExternalId] = React.useState("");
  const [url, setUrl] = React.useState("");
  const { busy, run } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="success" size="sm">
          <CheckCircle2 /> Отметить опубликованным
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Лот опубликован на PlayerOK"
        description="Укажите номер лота — по нему система свяжет объявление с будущими заказами."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              disabled={!externalId.trim()}
              loading={busy === "m"}
              onClick={async () => {
                const r = await run(
                  "m",
                  () => api.post(`/listings/${id}/mark-published`, { external_id: externalId.trim(), url: url.trim() || null }),
                  "Объявление отмечено опубликованным",
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
        <div className="flex flex-col gap-4">
          <Field label="Номер лота">
            <Input value={externalId} onChange={(e) => setExternalId(e.target.value)} autoFocus />
          </Field>
          <Field label="Ссылка на лот" hint="Необязательно">
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://playerok.com/products/…" />
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function ListingPage() {
  const { id } = useParams<{ id: string }>();
  const state = useApi<ListingDetail>(`/listings/${id}`);
  const { can } = useSession();
  const { busy, run } = useAction();
  const [draft, setDraft] = useDraft(state.data, toDraft);
  const [publish, setPublish] = React.useState<PublishResult>();

  async function call(key: string, path: string, success: string, body: unknown = {}) {
    const r = await run(key, () => api.post<ListingDetail>(path, body), success);
    if (r) state.reload();
    return r;
  }

  return (
    <Async state={state} rows={10}>
      {(l) => {
        const manage = can("listings.manage");
        const editable = ["draft", "ready", "paused", "error", "blocked", "published"].includes(l.status);
        const belowMin = Boolean(draft && l.min_price && Number(draft.price.replace(",", ".")) < Number(l.min_price));
        return (
          <>
            <Link href="/listings" className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground">
              <ArrowLeft className="size-4" /> Все объявления
            </Link>
            <PageHeader
              title={l.title}
              description={
                <>
                  Товар:{" "}
                  <Link href={`/products/${l.product_id}`} className="text-highlight hover:underline">
                    {l.product}
                  </Link>{" "}
                  · версия {l.version}
                </>
              }
              actions={
                manage && (
                  <>
                    {l.status === "draft" && (
                      <Button
                        variant="primary"
                        size="sm"
                        loading={busy === "prepare"}
                        onClick={() => call("prepare", `/listings/${id}/prepare`, "Проверки пройдены — объявление готово")}
                      >
                        <Wand2 /> Подготовить к публикации
                      </Button>
                    )}
                    {l.status === "ready" && !l.preview_confirmed_at && can("listings.publish") && (
                      <Button
                        variant="primary"
                        size="sm"
                        loading={busy === "confirm"}
                        onClick={() => call("confirm", `/listings/${id}/confirm-preview`, "Предпросмотр подтверждён")}
                      >
                        <CheckCircle2 /> Подтвердить предпросмотр
                      </Button>
                    )}
                    {l.status === "ready" && l.preview_confirmed_at && can("listings.publish") && (
                      <Button
                        variant="primary"
                        size="sm"
                        loading={busy === "publish"}
                        onClick={async () => {
                          const r = await run("publish", () => api.post<{ result: PublishResult }>(`/listings/${id}/publish`));
                          if (r) {
                            setPublish(r.result);
                            state.reload();
                          }
                        }}
                      >
                        <Send /> Опубликовать
                      </Button>
                    )}
                    {l.status === "ready" && <MarkPublished id={l.id} onDone={state.reload} />}
                    {l.status === "published" && (
                      <Button size="sm" loading={busy === "pause"} onClick={() => call("pause", `/listings/${id}/pause`, "Приостановлено")}>
                        <Pause /> Приостановить
                      </Button>
                    )}
                    {l.status === "paused" && (
                      <Button size="sm" loading={busy === "resume"} onClick={() => call("resume", `/listings/${id}/resume`, "Возобновлено")}>
                        <Play /> Возобновить
                      </Button>
                    )}
                    {l.status !== "archived" && (
                      <ConfirmAction
                        label="В архив"
                        icon={<Archive />}
                        title="Перенести объявление в архив?"
                        description="Если лот опубликован на PlayerOK, снимите его там вручную."
                        input={{ label: "Причина" }}
                        onConfirm={(reason) => call("archive", `/listings/${id}/archive`, "Перенесено в архив", { reason })}
                      />
                    )}
                  </>
                )
              }
            >
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge map={LISTING_STATUS} value={l.status} />
                {l.external_id && (
                  <span className="text-[13px] text-muted-foreground">
                    Лот {l.external_id}
                    {l.external_url && (
                      <a
                        href={l.external_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="ml-1.5 inline-flex items-center gap-1 text-highlight hover:underline"
                      >
                        открыть <ExternalLink className="size-3" />
                      </a>
                    )}
                  </span>
                )}
              </div>
            </PageHeader>

            {l.status_reason && (
              <Notice tone={l.status === "blocked" || l.status === "error" ? "danger" : "info"} className="mb-5">
                {l.status_reason}
              </Notice>
            )}

            {publish && (
              <Card className="mb-6 border-primary/30">
                <CardHeader
                  title={publish.mode === "manual" ? "Публикация вручную" : publish.mode === "test" ? "Тестовая публикация" : "Опубликовано"}
                  description={publish.message}
                />
                {publish.data && (
                  <CardBody className="flex flex-col gap-4">
                    {publish.steps && (
                      <ol className="list-decimal pl-5 text-sm">
                        {publish.steps.map((s) => (
                          <li key={s} className="py-0.5">
                            {s}
                          </li>
                        ))}
                      </ol>
                    )}
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="rounded-md border border-border p-3">
                        <p className="mb-1 text-xs text-muted-foreground">Название</p>
                        <p className="text-sm">{publish.data.title}</p>
                        <CopyButton value={publish.data.title} className="mt-2" />
                      </div>
                      <div className="rounded-md border border-border p-3">
                        <p className="mb-1 text-xs text-muted-foreground">Цена и количество</p>
                        <p className="text-sm">
                          {money(publish.data.price)} · {publish.data.quantity} шт. · {publish.data.category}
                        </p>
                        <CopyButton value={publish.data.price} label="Скопировать цену" className="mt-2" />
                      </div>
                      <div className="rounded-md border border-border p-3 md:col-span-2">
                        <p className="mb-1 text-xs text-muted-foreground">Описание</p>
                        <p className="text-sm whitespace-pre-wrap">{publish.data.description}</p>
                        <CopyButton value={publish.data.description} className="mt-2" />
                      </div>
                    </div>
                  </CardBody>
                )}
              </Card>
            )}

            <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
              <Card>
                <CardHeader title="Содержимое объявления" description="Каждое сохранение создаёт новую версию в истории" />
                <CardBody>
                  {draft && (
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="Название" hint={`${draft.title.length} / 100`} className="sm:col-span-2">
                        <Input
                          value={draft.title}
                          maxLength={100}
                          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                          disabled={!editable || !manage}
                        />
                      </Field>
                      <Field label="Описание" hint={`${draft.description.length} / 2000`} className="sm:col-span-2">
                        <Textarea
                          value={draft.description}
                          maxLength={2000}
                          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                          className="min-h-48"
                          disabled={!editable || !manage}
                        />
                      </Field>
                      <Field
                        label="Цена, ₽"
                        error={belowMin ? `Ниже минимальной цены ${money(l.min_price)} — сохранить не получится` : undefined}
                        hint={`Минимальная ${money(l.min_price)} · рекомендуемая ${money(l.recommended_price)}`}
                      >
                        <Input
                          inputMode="decimal"
                          value={draft.price}
                          onChange={(e) => setDraft({ ...draft, price: e.target.value })}
                          aria-invalid={belowMin}
                          disabled={!editable || !can("pricing.manage")}
                        />
                      </Field>
                      <Field label="Количество">
                        <Input
                          inputMode="numeric"
                          value={draft.quantity}
                          onChange={(e) => setDraft({ ...draft, quantity: e.target.value.replace(/\D/g, "") })}
                          disabled={!editable || !manage}
                        />
                      </Field>
                      <Field label="Категория на PlayerOK" className="sm:col-span-2">
                        <Input
                          value={draft.marketplace_category}
                          onChange={(e) => setDraft({ ...draft, marketplace_category: e.target.value })}
                          disabled={!editable || !manage}
                        />
                      </Field>
                      <label className="flex items-center gap-2.5 text-sm sm:col-span-2">
                        <Switch
                          checked={draft.relist_on_complete}
                          onCheckedChange={(v) => setDraft({ ...draft, relist_on_complete: v })}
                          disabled={!editable || !manage}
                        />
                        Готовить лот заново после продажи (при наличии товара)
                      </label>
                      {manage && editable && (
                        <div className="flex gap-2 sm:col-span-2">
                          <Button
                            variant="primary"
                            loading={busy === "save"}
                            disabled={belowMin}
                            onClick={async () => {
                              const body: Record<string, unknown> = {
                                title: draft.title,
                                description: draft.description,
                                quantity: Number(draft.quantity) || 1,
                                marketplace_category: draft.marketplace_category,
                                relist_on_complete: draft.relist_on_complete,
                              };
                              if (draft.price !== l.price) body.price = draft.price.replace(",", ".");
                              const r = await run("save", () => api.patch(`/listings/${id}`, body), "Сохранено");
                              if (r) state.reload();
                            }}
                          >
                            <Save /> Сохранить
                          </Button>
                          <Button onClick={() => setDraft(toDraft(l))}>Сбросить</Button>
                        </div>
                      )}
                    </div>
                  )}
                </CardBody>
              </Card>

              <div className="flex flex-col gap-6">
                <Card>
                  <CardHeader
                    title="Изображение"
                    actions={
                      manage && (
                        <Button
                          size="sm"
                          loading={busy === "img"}
                          onClick={async () => {
                            const r = await run(
                              "img",
                              () => api.post("/images/generate", { product_id: l.product_id, listing_id: l.id }),
                              "Изображение создано",
                            );
                            if (r) state.reload();
                          }}
                        >
                          <ImageIcon /> Сгенерировать
                        </Button>
                      )
                    }
                  />
                  <CardBody>
                    {l.images.length ? (
                      <div className="flex flex-col gap-3">
                        {/* eslint-disable-next-line @next/next/no-img-element -- authenticated API image, not a static asset */}
                        <img src={l.images[0].url} alt={`Изображение объявления «${l.title}»`} className="w-full rounded-md border border-border" />
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>
                            Шаблон {l.images[0].template} · версия {l.images[0].version}
                          </span>
                          <a href={l.images[0].url} download className="text-highlight hover:underline">
                            Скачать PNG
                          </a>
                        </div>
                      </div>
                    ) : (
                      <Empty title="Изображения нет" icon={ImageIcon}>
                        Сгенерируйте картинку по шаблону категории.
                      </Empty>
                    )}
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="Статус" />
                  <CardBody>
                    <KV
                      items={[
                        ["Предпросмотр", l.preview_confirmed_at ? `подтверждён ${dt(l.preview_confirmed_at)}` : "не подтверждён"],
                        ["Опубликовано", dt(l.published_at)],
                        ["Создано", l.auto_created ? "автоматически" : "вручную"],
                        ["Изменено", dt(l.updated_at)],
                      ]}
                    />
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="История версий" />
                  <CardBody>
                    {l.history.length ? (
                      <ol className="flex flex-col gap-3 text-[13px]">
                        {l.history.map((h, i) => (
                          <li key={i} className="flex items-start justify-between gap-3">
                            <span>
                              <span className="font-medium">v{h.version}</span> · {actionLabel(h.action)}
                              <span className="block text-xs text-muted-foreground">{h.actor ?? "система"}</span>
                            </span>
                            <span className="shrink-0 text-xs text-muted-foreground">{dt(h.at)}</span>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="text-sm text-muted-foreground">Изменений нет.</p>
                    )}
                  </CardBody>
                </Card>
              </div>
            </div>
          </>
        );
      }}
    </Async>
  );
}
