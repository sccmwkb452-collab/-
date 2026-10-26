"use client";

import { Download, ImageIcon, Layers, RefreshCw, Wand2 } from "lucide-react";
import * as React from "react";

import { Async, Empty, Notice, PageHeader } from "@/components/app/blocks";
import { ToneBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { dt } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Paged, Product } from "@/lib/types";

type Template = {
  code: string;
  name: string;
  kind: "demo" | "user";
  groups: string[];
  width: number;
  height: number;
  active: boolean;
  fields: string[];
  analysis: { width: number; height: number; format: string | null; palette: string[] } | null;
};

type Image = {
  id: number;
  product_id: number;
  listing_id: number | null;
  version: number | null;
  template: string;
  width: number;
  height: number;
  url: string;
  preview: boolean;
  created_at: string | null;
};

const FIELD_HINT: Record<string, string> = {
  title: "Заголовок",
  amount: "Количество",
  price: "Цена",
  subtitle: "Подзаголовок",
};

function templateState(t: Template) {
  if (t.active) return <ToneBadge tone="success">Готов</ToneBadge>;
  if (!t.width) return <ToneBadge tone="warning">Ждёт файл изображения</ToneBadge>;
  return <ToneBadge tone="warning">Нужна разметка полей</ToneBadge>;
}

export default function ImagesPage() {
  const { can } = useSession();
  const templates = useApi<{ items: Template[]; originals_dir: string }>("/images/templates");
  const products = useApi<Paged<Product>>("/products?per_page=100");
  const [productId, setProductId] = React.useState("");
  const [template, setTemplate] = React.useState("");
  const [showPrice, setShowPrice] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [result, setResult] = React.useState<Image>();
  const gallery = useApi<{ items: Image[] }>(productId ? `/images?product_id=${productId}` : "/images");
  const { busy, run } = useAction();
  const manage = can("listings.manage");
  const productName = (id: number) => products.data?.items.find((p) => p.id === id)?.name ?? `товар #${id}`;

  return (
    <>
      <PageHeader
        title="Генератор изображений"
        description="Картинки для объявлений по вашим шаблонам: система стирает старые надписи и пишет новые значения тем же стилем и шрифтом."
        actions={
          manage && (
            <Button
              loading={busy === "sync"}
              onClick={async () => {
                const r = await run(
                  "sync",
                  () => api.post<{ demo: number; user: number; needs_layout: number; awaiting_file: number }>("/images/templates/sync"),
                  (x) => `Шаблоны обновлены: ваших ${x.user}, ждут файл ${x.awaiting_file}, нужна разметка ${x.needs_layout}`,
                );
                if (r) templates.reload();
              }}
            >
              <RefreshCw /> Обновить шаблоны
            </Button>
          )
        }
      />

      {templates.data && templates.data.items.some((t) => t.kind === "user" && !t.width) && (
        <Notice tone="warning" title="Ваши шаблоны ждут файлы" className="mb-5">
          Разметка ваших 5 шаблонов (Telegram Premium, Stars, подписчики, PUBG UC, Steam) готова, но самих картинок на сервере ещё нет. Положите PNG
          в каталог <b>{templates.data.originals_dir}</b> с именами tg-premium.png, tg-stars.png, tg-subscribers.png, pubg-uc.png, steam-giftcard.png и
          нажмите «Обновить шаблоны».
        </Notice>
      )}

      <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
        <Card>
          <CardHeader title="Создать изображение" description="Предпросмотр — не привязывается к объявлению" />
          <CardBody className="flex flex-col gap-4">
            <Field label="Товар">
              <NativeSelect value={productId} onChange={(e) => setProductId(e.target.value)}>
                <option value="">Выберите…</option>
                {products.data?.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Шаблон" hint="Автоматически — по категории товара">
              <NativeSelect value={template} onChange={(e) => setTemplate(e.target.value)}>
                <option value="">Автоматически</option>
                {templates.data?.items.map((t) => (
                  <option key={t.code} value={t.code} disabled={!t.active}>
                    {t.name}
                    {!t.active ? " (недоступен)" : ""}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Свой заголовок" hint="Необязательно — иначе берётся из товара">
              <Input value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={showPrice} onCheckedChange={setShowPrice} /> Показать цену на картинке (если в шаблоне есть поле цены)
            </label>
            <Button
              variant="primary"
              disabled={!productId || !manage}
              loading={busy === "gen"}
              onClick={async () => {
                const r = await run(
                  "gen",
                  () =>
                    api.post<Image>("/images/generate", {
                      product_id: Number(productId),
                      template_code: template || null,
                      overrides: title.trim() ? { title: title.trim() } : {},
                      show_price: showPrice,
                    }),
                  "Изображение готово",
                );
                if (r) {
                  setResult(r);
                  gallery.reload();
                }
              }}
            >
              <Wand2 /> Сгенерировать
            </Button>
            {result && (
              <div className="flex flex-col gap-2">
                {/* eslint-disable-next-line @next/next/no-img-element -- authenticated API image */}
                <img src={result.url} alt="Сгенерированное изображение" className="w-full rounded-md border border-border" />
                <a href={result.url} download={`image-${result.id}.png`} className="inline-flex items-center gap-1.5 text-[13px] text-highlight hover:underline">
                  <Download className="size-4" /> Скачать PNG {result.width}×{result.height}
                </a>
              </div>
            )}
          </CardBody>
        </Card>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader title="Шаблоны" description="Демо-шаблоны встроены; ваши подключаются из файлов" />
            <Async state={templates}>
              {(d) => (
                <div className="grid gap-4 p-5 sm:grid-cols-2 2xl:grid-cols-3">
                  {d.items.map((t) => (
                    <div key={t.code} className="overflow-hidden rounded-lg border border-border bg-surface-2/40">
                      <div className="grid aspect-[16/10] place-items-center bg-[#0b111d]">
                        {t.width ? (
                          // eslint-disable-next-line @next/next/no-img-element -- authenticated API image
                          <img src={`/api/v1/images/templates/${encodeURIComponent(t.code)}/file`} alt={`Шаблон ${t.name}`} className="h-full w-full object-contain" loading="lazy" />
                        ) : (
                          <ImageIcon className="size-8 text-subtle" aria-hidden />
                        )}
                      </div>
                      <div className="flex flex-col gap-1.5 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium">{t.name}</p>
                          <span className="text-[11px] text-subtle">{t.kind === "demo" ? "демо" : "ваш"}</span>
                        </div>
                        {templateState(t)}
                        <p className="text-xs text-muted-foreground">
                          {t.width ? `${t.width}×${t.height}` : "нет файла"}
                          {t.fields.length ? ` · поля: ${t.fields.map((f) => FIELD_HINT[f] ?? f).join(", ")}` : ""}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Async>
          </Card>

          <Card>
            <CardHeader title={productId ? "Изображения товара" : "Последние изображения"} />
            <Async state={gallery}>
              {(d) =>
                d.items.length ? (
                  <div className="grid grid-cols-2 gap-3 p-5 md:grid-cols-3 2xl:grid-cols-4">
                    {d.items.map((img) => (
                      <a key={img.id} href={img.url} target="_blank" rel="noreferrer" className="group overflow-hidden rounded-md border border-border hover:border-border-strong">
                        {/* eslint-disable-next-line @next/next/no-img-element -- authenticated API image */}
                        <img src={img.url} alt={`Изображение для ${productName(img.product_id)}`} className="aspect-[16/10] w-full object-cover" loading="lazy" />
                        <div className="px-2 py-1.5 text-[11px] text-muted-foreground">
                          <p className="truncate text-foreground">{productName(img.product_id)}</p>
                          {img.preview ? "предпросмотр" : `объявление #${img.listing_id}`} · {dt(img.created_at)}
                        </div>
                      </a>
                    ))}
                  </div>
                ) : (
                  <Empty title="Изображений нет" icon={Layers}>
                    Выберите товар и нажмите «Сгенерировать».
                  </Empty>
                )
              }
            </Async>
          </Card>
        </div>
      </div>
    </>
  );
}
