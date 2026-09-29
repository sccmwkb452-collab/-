"use client";

import type { ImageKind } from "@prisma/client";
import { ArrowDown, ArrowUp, ImagePlus, Loader2, Star, Trash2 } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { deleteProjectImageAction, updateProjectImageAction } from "@/lib/actions/projects";
import { cn } from "@/lib/utils";

interface ManagedImage {
  id: string;
  url: string;
  alt: string;
  kind: ImageKind;
}

const MAX_SIZE = 10 * 1024 * 1024;
const ACCEPT = ["image/jpeg", "image/png", "image/webp", "image/avif"];

const SECTIONS: { kind: ImageKind; title: string; hint: string; multiple: boolean }[] = [
  { kind: "COVER", title: "Главное изображение", hint: "Показывается в каталоге и первым в галерее. Рекомендуем 1600×1000 и больше.", multiple: false },
  { kind: "GALLERY", title: "Галерея", hint: "Фото и визуализации дома. Можно выбрать несколько файлов.", multiple: true },
  { kind: "PLAN", title: "Планировки", hint: "Поэтажные планы в порядке этажей.", multiple: true },
];

function ImageRow({ image, first, last }: { image: ManagedImage; first: boolean; last: boolean }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [alt, setAlt] = useState(image.alt);
  const run = (fn: () => Promise<{ ok: boolean; error?: string; message?: string }>) =>
    start(async () => {
      const res = await fn();
      if (!res.ok) toast.error(res.error ?? "Ошибка");
      else {
        if (res.message) toast.success(res.message);
        router.refresh();
      }
    });

  return (
    <li className={cn("flex items-center gap-3 rounded-xl border border-border bg-white p-2.5 transition", pending && "opacity-60")}>
      <span className="relative h-16 w-24 shrink-0 overflow-hidden rounded-lg bg-secondary">
        <Image src={image.url} alt={alt || "Изображение проекта"} fill sizes="96px" className="object-cover" />
      </span>
      <Input
        value={alt}
        onChange={(e) => setAlt(e.target.value)}
        onBlur={() => alt !== image.alt && run(() => updateProjectImageAction(image.id, { alt }))}
        placeholder="Alt-текст для SEO и доступности"
        className="h-10 min-w-0 flex-1 text-sm"
        aria-label="Alt-текст"
        maxLength={200}
      />
      <div className="flex shrink-0 items-center">
        {image.kind !== "COVER" && (
          <>
            <Button type="button" variant="ghost" size="icon-sm" disabled={first || pending} onClick={() => run(() => updateProjectImageAction(image.id, { move: -1 }))} aria-label="Выше"><ArrowUp /></Button>
            <Button type="button" variant="ghost" size="icon-sm" disabled={last || pending} onClick={() => run(() => updateProjectImageAction(image.id, { move: 1 }))} aria-label="Ниже"><ArrowDown /></Button>
          </>
        )}
        {image.kind === "GALLERY" && (
          <Button type="button" variant="ghost" size="icon-sm" disabled={pending} onClick={() => run(() => updateProjectImageAction(image.id, { kind: "COVER" }))} aria-label="Сделать главным" title="Сделать главным"><Star /></Button>
        )}
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          disabled={pending}
          className="text-destructive hover:bg-destructive/10"
          onClick={() => window.confirm("Удалить изображение?") && run(() => deleteProjectImageAction(image.id))}
          aria-label="Удалить"
        >
          {pending ? <Loader2 className="animate-spin" /> : <Trash2 />}
        </Button>
      </div>
    </li>
  );
}

function UploadZone({ projectId, kind, multiple }: { projectId: string; kind: ImageKind; multiple: boolean }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [drag, setDrag] = useState(false);

  const upload = async (list: FileList | File[]) => {
    const files = Array.from(list);
    const invalid = files.filter((f) => !ACCEPT.includes(f.type) || f.size > MAX_SIZE);
    if (invalid.length) {
      toast.error("Некоторые файлы пропущены", { description: "Допустимы JPG, PNG, WebP, AVIF до 10 МБ." });
    }
    const valid = files.filter((f) => !invalid.includes(f)).slice(0, multiple ? 12 : 1);
    if (!valid.length) return;
    const body = new FormData();
    body.set("kind", kind);
    valid.forEach((f) => body.append("files", f));
    setUploading(true);
    try {
      const res = await fetch(`/api/admin/projects/${projectId}/images`, { method: "POST", body });
      const data = (await res.json().catch(() => null)) as { ok?: boolean; uploaded?: number; errors?: string[]; error?: string } | null;
      if (!res.ok || !data?.ok) throw new Error(data?.error ?? "Не удалось загрузить");
      toast.success(`Загружено: ${data.uploaded}`);
      data.errors?.forEach((e) => toast.error(e));
      router.refresh();
    } catch (error) {
      toast.error("Ошибка загрузки", { description: error instanceof Error ? error.message : undefined });
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        if (e.dataTransfer.files.length) upload(e.dataTransfer.files);
      }}
      className={cn("rounded-xl border-2 border-dashed p-5 text-center transition", drag ? "border-accent bg-accent/5" : "border-border")}
    >
      <input ref={inputRef} type="file" accept={ACCEPT.join(",")} multiple={multiple} className="sr-only" id={`upload-${kind}`} onChange={(e) => e.target.files && upload(e.target.files)} />
      <label htmlFor={`upload-${kind}`} className="inline-flex cursor-pointer items-center gap-2 rounded-full bg-secondary px-4 py-2 text-sm font-medium transition hover:bg-sand/60">
        {uploading ? <Loader2 className="size-4 animate-spin" /> : <ImagePlus className="size-4" />}
        {uploading ? "Загрузка…" : multiple ? "Выбрать файлы" : "Выбрать файл"}
      </label>
      <p className="mt-2 text-xs text-muted-foreground">или перетащите сюда · JPG, PNG, WebP до 10 МБ</p>
    </div>
  );
}

export function ImageManager({ projectId, images }: { projectId: string; images: ManagedImage[] }) {
  return (
    <div className="space-y-6">
      {SECTIONS.map((s) => {
        const list = images.filter((i) => i.kind === s.kind);
        return (
          <Card key={s.kind}>
            <CardHeader>
              <CardTitle>{s.title}</CardTitle>
              <p className="text-sm text-muted-foreground">{s.hint}</p>
            </CardHeader>
            <CardContent className="space-y-3">
              {list.length > 0 && (
                <ul className="space-y-2">
                  {list.map((img, i) => (
                    <ImageRow key={img.id} image={img} first={i === 0} last={i === list.length - 1} />
                  ))}
                </ul>
              )}
              {s.kind === "COVER" && !list.length && <p className="text-sm text-destructive">Без главного изображения карточка проекта будет выглядеть пустой.</p>}
              <UploadZone projectId={projectId} kind={s.kind} multiple={s.multiple} />
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
