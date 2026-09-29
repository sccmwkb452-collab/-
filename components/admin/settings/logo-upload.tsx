"use client";

import { ImagePlus, Loader2, Trash2 } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { removeLogoAction } from "@/lib/actions/settings";

export function LogoUpload({ logoUrl }: { logoUrl: string | null }) {
  const router = useRouter();
  const [uploading, setUploading] = useState(false);
  const [pending, start] = useTransition();

  const upload = async (file: File) => {
    if (file.size > 10 * 1024 * 1024) {
      toast.error("Файл больше 10 МБ");
      return;
    }
    const body = new FormData();
    body.set("file", file);
    setUploading(true);
    try {
      const res = await fetch("/api/admin/logo", { method: "POST", body });
      const data = (await res.json().catch(() => null)) as { ok?: boolean; error?: string } | null;
      if (!res.ok || !data?.ok) throw new Error(data?.error ?? "Ошибка загрузки");
      toast.success("Логотип обновлён");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Ошибка загрузки");
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Логотип</CardTitle>
        <p className="text-sm text-muted-foreground">PNG или WebP с прозрачным фоном, высота от 72 px. Без логотипа выводится фирменный знак и название.</p>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-4">
        <div className="flex h-20 w-44 items-center justify-center rounded-xl border border-dashed border-border bg-secondary/50 p-3">
          {logoUrl ? <Image src={logoUrl} alt="Текущий логотип" width={160} height={60} className="max-h-14 w-auto object-contain" /> : <span className="text-xs text-muted-foreground">Не загружен</span>}
        </div>
        <div className="flex gap-2">
          <input id="logo" type="file" accept="image/png,image/webp,image/jpeg,image/avif" className="sr-only" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <label htmlFor="logo" className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-full bg-primary px-4 text-[13px] font-semibold text-primary-foreground transition hover:bg-primary/90">
            {uploading ? <Loader2 className="size-4 animate-spin" /> : <ImagePlus className="size-4" />}
            Загрузить
          </label>
          {logoUrl && (
            <Button
              variant="ghost"
              size="sm"
              disabled={pending}
              className="text-destructive hover:bg-destructive/10"
              onClick={() =>
                start(async () => {
                  const res = await removeLogoAction();
                  if (res.ok) {
                    toast.success(res.message ?? "Удалено");
                    router.refresh();
                  } else toast.error(res.error);
                })
              }
            >
              <Trash2 />
              Удалить
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
