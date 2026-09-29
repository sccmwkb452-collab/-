"use client";

import { RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
      <p className="eyebrow">Что-то пошло не так</p>
      <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-6xl">Не удалось загрузить страницу</h1>
      <p className="mt-5 max-w-md text-muted-foreground">Мы уже знаем о проблеме. Попробуйте обновить страницу через несколько секунд.</p>
      {error.digest && <p className="mt-2 text-xs text-muted-foreground">Код ошибки: {error.digest}</p>}
      <div className="mt-9 flex flex-col gap-3 sm:flex-row">
        <Button size="lg" onClick={reset}><RotateCcw />Попробовать снова</Button>
        <Button asChild size="lg" variant="outline"><Link href="/">На главную</Link></Button>
      </div>
    </main>
  );
}
