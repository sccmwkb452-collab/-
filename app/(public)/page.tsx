import { ArrowRight, ClipboardCheck, Hammer, KeyRound, ShieldCheck, Wallet } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { CalculatorCta } from "@/components/home/calculator-cta";
import { Hero } from "@/components/home/hero";
import { ProjectCard } from "@/components/projects/project-card";
import { FaqList } from "@/components/shared/faq-list";
import { FinalCta } from "@/components/shared/final-cta";
import { Reveal } from "@/components/shared/reveal";
import { SectionHeading } from "@/components/shared/section-heading";
import { Button } from "@/components/ui/button";
import { getFaqs, getFeaturedProjects, getPackages, getTechnologies } from "@/lib/data/projects";
import { pageMetadata } from "@/lib/seo";
import { getSiteSettings } from "@/lib/settings";
import { formatNumber } from "@/lib/utils";

export async function generateMetadata(): Promise<Metadata> {
  const s = await getSiteSettings();
  return { ...pageMetadata({ title: s.seoTitle, description: s.seoDescription, path: "/" }), title: { absolute: s.seoTitle } };
}

const JOURNEY = [
  { title: "Выберите проект", text: "Готовый проект из каталога или собственная идея — начнём с того, что вам ближе." },
  { title: "Настройте параметры", text: "Площадь, этажность, технология, комплектация и опции — в онлайн-конструкторе." },
  { title: "Получите расчёт", text: "Система сразу покажет предварительную стоимость и из чего она складывается." },
  { title: "Встреча с инженером", text: "Уточним детали по участку и подготовим смету с фиксированной ценой." },
];

const WHY = [
  { icon: Wallet, title: "Фиксированная цена", text: "Стоимость закрепляется в договоре и не меняется до конца строительства." },
  { icon: ClipboardCheck, title: "Поэтапная оплата", text: "Платите только за принятый этап. Возможна ипотека и эскроу-счёт." },
  { icon: Hammer, title: "Технический надзор", text: "Инженер контролирует каждый этап, а вы получаете еженедельный фотоотчёт." },
  { icon: ShieldCheck, title: "Гарантия до 15 лет", text: "Гарантия на конструктив, инженерные системы и отделку по договору." },
];

const REVIEWS = [
  { name: "Демо-отзыв", place: "Дом «Нордик», 98 м²", text: "Понравилось, что стоимость в калькуляторе почти совпала с итоговой сметой. Всё строительство вели по графику и присылали отчёты каждую неделю." },
  { name: "Демо-отзыв", place: "Дом «Артем», 156 м²", text: "Внесли изменения в планировку бесплатно: добавили кабинет и увеличили террасу. Дом сдали на две недели раньше срока." },
  { name: "Демо-отзыв", place: "Дом «Горизонт», 148 м²", text: "Главное — прозрачность. В любой момент было понятно, за что мы платим и на каком этапе стройка." },
];

export default async function HomePage() {
  const [settings, projects, technologies, packages, faqs] = await Promise.all([
    getSiteSettings(),
    getFeaturedProjects(6),
    getTechnologies(),
    getPackages(),
    getFaqs(),
  ]);
  const minPrice = technologies.length ? Math.min(...technologies.map((t) => t.pricePerM2)) : 0;

  return (
    <>
      <Hero image="/demo/hero.webp" />

      <section className="container-page py-20 sm:py-28" aria-labelledby="journey-title">
        <div className="grid gap-12 lg:grid-cols-12">
          <Reveal className="lg:col-span-4">
            <SectionHeading
              eyebrow="Как это работает"
              title={<span id="journey-title">От идеи до расчёта — за несколько минут</span>}
              description="Мы превратили первый шаг к своему дому в понятный путь без звонков и ожидания."
            />
          </Reveal>
          <ol className="grid gap-px overflow-hidden rounded-3xl border border-border bg-border sm:grid-cols-2 lg:col-span-8">
            {JOURNEY.map((step, i) => (
              <Reveal key={step.title} delay={i * 0.08} className="h-full">
                <li className="flex h-full flex-col bg-background p-7 sm:p-9">
                  <span className="text-sm font-semibold text-accent tabular">0{i + 1}</span>
                  <h3 className="mt-10 text-xl font-semibold">{step.title}</h3>
                  <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">{step.text}</p>
                </li>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      <CalculatorCta minPricePerM2={minPrice} stepsCount={7} />

      <section className="container-page py-20 sm:py-28" aria-labelledby="projects-title">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <SectionHeading eyebrow="Каталог" title={<span id="projects-title">Проекты домов</span>} description="Каждый проект можно адаптировать под ваш участок и образ жизни." />
          <Button asChild variant="outline" className="self-start sm:self-auto">
            <Link href="/projects">
              Все проекты
              <ArrowRight />
            </Link>
          </Button>
        </div>
        {projects.length ? (
          <div className="mt-12 grid gap-x-6 gap-y-12 md:grid-cols-2 xl:grid-cols-3">
            {projects.map((p, i) => (
              <Reveal key={p.id} delay={(i % 3) * 0.08}>
                <ProjectCard project={p} />
              </Reveal>
            ))}
          </div>
        ) : (
          <p className="mt-12 rounded-2xl border border-dashed p-10 text-center text-muted-foreground">Проекты скоро появятся в каталоге.</p>
        )}
      </section>

      <section className="border-y border-border bg-white py-20 sm:py-28" aria-labelledby="tech-title">
        <div className="container-page">
          <SectionHeading eyebrow="Технологии" title={<span id="tech-title">Строим из того, что подходит именно вам</span>} />
          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {technologies.map((t, i) => (
              <Reveal key={t.id} delay={i * 0.06} className="h-full">
                <Link href={`/technology#${t.slug}`} className="group flex h-full flex-col rounded-2xl border border-border bg-background p-7 transition-all duration-500 hover:-translate-y-1 hover:border-foreground/20">
                  <span className="text-sm text-muted-foreground">{t.buildTime}</span>
                  <h3 className="mt-8 text-2xl font-semibold">{t.name}</h3>
                  <p className="mt-3 flex-1 text-sm leading-relaxed text-muted-foreground">{t.shortDescription}</p>
                  <p className="mt-8 flex items-end justify-between border-t border-border pt-5">
                    <span>
                      <span className="block text-xs text-muted-foreground">под ключ</span>
                      <span className="text-lg font-semibold tabular">от {formatNumber(t.pricePerM2)} ₽/м²</span>
                    </span>
                    <ArrowRight className="size-5 transition-transform group-hover:translate-x-1" />
                  </p>
                </Link>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="container-page py-20 sm:py-28" aria-labelledby="why-title">
        <div className="grid gap-12 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <SectionHeading
              eyebrow="Почему мы"
              title={<span id="why-title">Прозрачное строительство без сюрпризов</span>}
              description="Мы отвечаем за результат от первого эскиза до передачи ключей — и фиксируем это в договоре."
            />
            <Button asChild variant="outline" className="mt-8">
              <Link href="/build">Как проходит строительство</Link>
            </Button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:col-span-7">
            {WHY.map((w, i) => (
              <Reveal key={w.title} delay={i * 0.06}>
                <div className="h-full rounded-2xl bg-white p-7">
                  <w.icon className="size-6 text-accent" aria-hidden />
                  <h3 className="mt-6 text-lg font-semibold">{w.title}</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{w.text}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-secondary/60 py-20 sm:py-28" aria-labelledby="packages-title">
        <div className="container-page">
          <SectionHeading eyebrow="Комплектации" title={<span id="packages-title">Выберите степень готовности дома</span>} description="От надёжной коробки до дома, в который можно заехать с чемоданом." />
          <div className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {packages.map((p, i) => (
              <Reveal key={p.id} delay={i * 0.06} className="h-full">
                <div className={i === packages.length - 1 ? "flex h-full flex-col rounded-2xl bg-primary p-7 text-primary-foreground" : "flex h-full flex-col rounded-2xl bg-white p-7"}>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold tracking-widest uppercase opacity-50">Уровень {i + 1}</span>
                    {i === packages.length - 1 && (
                      <span className="flex items-center gap-1.5 rounded-full bg-accent px-2.5 py-1 text-xs font-semibold text-white">
                        <KeyRound className="size-3.5" aria-hidden />
                        Можно заезжать
                      </span>
                    )}
                  </div>
                  <h3 className="mt-6 text-2xl font-semibold">{p.name}</h3>
                  <p className="mt-2 text-sm opacity-65">{p.description}</p>
                  <ul className="mt-6 space-y-2.5 text-sm">
                    {p.includes.map((inc) => (
                      <li key={inc} className="flex gap-2.5">
                        <span className="mt-2 size-1.5 shrink-0 rounded-full bg-accent" />
                        {inc}
                      </li>
                    ))}
                  </ul>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="container-page py-20 sm:py-28" aria-labelledby="reviews-title">
        <SectionHeading eyebrow="Отзывы" title={<span id="reviews-title">Что говорят владельцы домов</span>} description="Ниже — демонстрационные отзывы для примера оформления раздела." />
        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {REVIEWS.map((r, i) => (
            <Reveal key={r.place} delay={i * 0.08} className="h-full">
              <figure className="flex h-full flex-col rounded-2xl border border-border bg-white p-7">
                <blockquote className="flex-1 text-[15px] leading-relaxed">«{r.text}»</blockquote>
                <figcaption className="mt-6 flex items-center justify-between border-t border-border pt-5 text-sm">
                  <span className="font-semibold">{r.place}</span>
                  <span className="rounded-full bg-secondary px-2.5 py-1 text-xs text-muted-foreground">{r.name}</span>
                </figcaption>
              </figure>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="container-page pb-4" aria-labelledby="faq-title">
        <div className="grid gap-10 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <SectionHeading eyebrow="FAQ" title={<span id="faq-title">Частые вопросы</span>} />
            <Button asChild variant="link" className="mt-6">
              <Link href="/faq">Все вопросы и ответы →</Link>
            </Button>
          </div>
          <div className="lg:col-span-8">
            <FaqList items={faqs.slice(0, 5)} withSchema={false} />
          </div>
        </div>
      </section>

      <FinalCta phone={settings.phone} />
    </>
  );
}
