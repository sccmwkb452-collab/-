import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
      <p className="eyebrow">Ошибка 404</p>
      <h1 className="mt-4 text-5xl font-semibold tracking-tight sm:text-7xl">Страница не найдена</h1>
      <p className="mt-5 max-w-md text-muted-foreground">
        Возможно, проект сняли с публикации или ссылка устарела. Посмотрите каталог или рассчитайте стоимость своего дома.
      </p>
      <div className="mt-9 flex flex-col gap-3 sm:flex-row">
        <Button asChild size="lg"><Link href="/projects">Каталог проектов</Link></Button>
        <Button asChild size="lg" variant="outline"><Link href="/">На главную</Link></Button>
      </div>
    </main>
  );
}
