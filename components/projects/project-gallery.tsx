"use client";

import { ChevronLeft, ChevronRight, Expand } from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface GalleryImage {
  id: string;
  url: string;
  alt: string;
}

export function ProjectGallery({ images, title }: { images: GalleryImage[]; title: string }) {
  const [index, setIndex] = useState(0);
  const [open, setOpen] = useState(false);
  const count = images.length;
  const go = useCallback((delta: number) => setIndex((i) => (i + delta + count) % count), [count]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, go]);

  if (!count) {
    return <div className="flex aspect-[16/10] items-center justify-center rounded-3xl bg-sand/40 text-muted-foreground">Изображения скоро появятся</div>;
  }
  const current = images[index];

  return (
    <div>
      <div className="group relative aspect-[16/10] overflow-hidden rounded-3xl bg-sand/40">
        <Image
          key={current.id}
          src={current.url}
          alt={current.alt || title}
          fill
          priority={index === 0}
          sizes="(min-width: 1024px) 66vw, 100vw"
          className="animate-in object-cover duration-500 fade-in-0"
        />
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="absolute right-4 bottom-4 flex items-center gap-2 rounded-full bg-white/90 px-4 py-2 text-sm font-medium backdrop-blur transition hover:bg-white cursor-pointer"
        >
          <Expand className="size-4" />
          Открыть
        </button>
        {count > 1 && (
          <>
            <button type="button" onClick={() => go(-1)} aria-label="Предыдущее фото" className="absolute top-1/2 left-4 flex size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/90 opacity-100 transition hover:bg-white sm:opacity-0 sm:group-hover:opacity-100 focus-visible:opacity-100 cursor-pointer">
              <ChevronLeft className="size-5" />
            </button>
            <button type="button" onClick={() => go(1)} aria-label="Следующее фото" className="absolute top-1/2 right-4 flex size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/90 opacity-100 transition hover:bg-white sm:opacity-0 sm:group-hover:opacity-100 focus-visible:opacity-100 cursor-pointer">
              <ChevronRight className="size-5" />
            </button>
            <span className="absolute bottom-4 left-4 rounded-full bg-black/55 px-3 py-1 text-xs font-medium text-white tabular backdrop-blur">
              {index + 1} / {count}
            </span>
          </>
        )}
      </div>
      {count > 1 && (
        <div className="mt-3 grid grid-cols-4 gap-3 sm:grid-cols-6">
          {images.map((img, i) => (
            <button
              key={img.id}
              type="button"
              onClick={() => setIndex(i)}
              aria-label={`Показать фото ${i + 1}`}
              aria-current={i === index}
              className={cn(
                "relative aspect-[4/3] overflow-hidden rounded-xl transition-all cursor-pointer",
                i === index ? "ring-2 ring-primary ring-offset-2 ring-offset-background" : "opacity-60 hover:opacity-100",
              )}
            >
              <Image src={img.url} alt="" fill sizes="160px" className="object-cover" />
            </button>
          ))}
        </div>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-[min(96vw,1400px)] bg-black p-2 sm:p-3">
          <DialogTitle className="sr-only">{title}</DialogTitle>
          <DialogDescription className="sr-only">Фото {index + 1} из {count}</DialogDescription>
          <div className="relative aspect-[16/10] w-full">
            <Image src={current.url} alt={current.alt || title} fill sizes="96vw" className="rounded-xl object-contain" />
          </div>
          {count > 1 && (
            <div className="flex items-center justify-between px-2 pb-1 text-sm text-white/70">
              <button type="button" onClick={() => go(-1)} className="flex items-center gap-1 rounded-full px-3 py-2 hover:bg-white/10 cursor-pointer"><ChevronLeft className="size-4" /> Назад</button>
              <span className="tabular">{index + 1} / {count}</span>
              <button type="button" onClick={() => go(1)} className="flex items-center gap-1 rounded-full px-3 py-2 hover:bg-white/10 cursor-pointer">Вперёд <ChevronRight className="size-4" /></button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
