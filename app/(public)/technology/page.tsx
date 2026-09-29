import { Check, Clock, ShieldCheck } from "lucide-react";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { FinalCta } from "@/components/shared/final-cta";
import { PageHero } from "@/components/shared/page-hero";
import { Reveal } from "@/components/shared/reveal";
import { Button } from "@/components/ui/button";
import { getTechnologies } from "@/lib/data/projects";
import { pageMetadata } from "@/lib/seo";
import { getSiteSettings } from "@/lib/settings";
import { formatNumber } from "@/lib/utils";

export const metadata: Metadata = pageMetadata({
  title: "Технологии строительства домов",
  description: "Газобетон, кирпич, каркас и клеёный брус: сравнение технологий, сроков строительства, гарантий и стоимости за квадратный метр.",
  path: "/technology",
});

const IMAGES = ["/demo/projects/dom-gorizont/cover.webp", "/demo/projects/dom-grafit/gallery-1.webp", "/demo/projects/dom-skandi/cover.webp", "/demo/projects/dom-lesnoy/gallery-3.webp"];

export default async function TechnologyPage() {
  const [technologies, settings] = await Promise.all([getTechnologies(), getSiteSettings()]);
  return (
    <>
      <PageHero
        eyebrow="Технологии"
        title="Четыре технологии — один стандарт качества"
        description="Мы строим из материалов, которые проверили на сотнях объектов. Поможем выбрать технологию под ваш бюджет, сроки и образ жизни."
        breadcrumbs={[{ name: "Технологии", path: "/technology" }]}
      />

      <section className="container-page pb-8" aria-label="Сравнение технологий">
        <div className="overflow-x-auto rounded-2xl border border-border bg-white">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs tracking-wide text-muted-foreground uppercase">
                <th className="px-5 py-4 font-semibold">Технология</th>
                <th className="px-5 py-4 font-semibold">Срок</th>
                <th className="px-5 py-4 font-semibold">Гарантия</th>
                <th className="px-5 py-4 text-right font-semibold">Под ключ, ₽/м²</th>
              </tr>
            </thead>
            <tbody>
              {technologies.map((t) => (
                <tr key={t.id} className="border-b border-border last:border-0">
                  <td className="px-5 py-4 font-semibold"><a href={`#${t.slug}`} className="hover:text-accent">{t.name}</a></td>
                  <td className="px-5 py-4">{t.buildTime}</td>
                  <td className="px-5 py-4">{t.warranty}</td>
                  <td className="px-5 py-4 text-right font-semibold tabular">от {formatNumber(t.pricePerM2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="container-page">
        {technologies.map((t, i) => (
          <section key={t.id} id={t.slug} className="scroll-mt-24 border-b border-border py-16 last:border-0 sm:py-24" aria-labelledby={`${t.slug}-title`}>
            <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
              <Reveal className={i % 2 ? "lg:order-2" : undefined}>
                <div className="relative aspect-[4/3] overflow-hidden rounded-3xl bg-sand/40">
                  <Image src={IMAGES[i % IMAGES.length]} alt={`Дом по технологии «${t.name}»`} fill sizes="(min-width: 1024px) 50vw, 100vw" className="object-cover" />
                </div>
              </Reveal>
              <Reveal delay={0.1}>
                <p className="eyebrow">Технология {String(i + 1).padStart(2, "0")}</p>
                <h2 id={`${t.slug}-title`} className="mt-4 text-3xl font-semibold tracking-tight sm:text-5xl">{t.name}</h2>
                <p className="mt-6 text-[15px] leading-relaxed text-foreground/80 sm:text-base">{t.description}</p>
                <ul className="mt-8 grid gap-3 sm:grid-cols-2">
                  {t.advantages.map((a) => (
                    <li key={a} className="flex items-start gap-2.5 text-[15px]">
                      <Check className="mt-1 size-4 shrink-0 text-accent" />
                      {a}
                    </li>
                  ))}
                </ul>
                <div className="mt-8 flex flex-wrap gap-6 border-t border-border pt-6 text-sm">
                  <span className="flex items-center gap-2"><Clock className="size-4 text-accent" />{t.buildTime}</span>
                  <span className="flex items-center gap-2"><ShieldCheck className="size-4 text-accent" />{t.warranty}</span>
                  <span className="font-semibold tabular">от {formatNumber(t.pricePerM2)} ₽/м² под ключ</span>
                </div>
                <Button asChild className="mt-8">
                  <Link href="/calculator">Рассчитать дом из материала «{t.name}»</Link>
                </Button>
              </Reveal>
            </div>
          </section>
        ))}
      </div>

      <FinalCta phone={settings.phone} title="Не знаете, что выбрать?" description="Инженер сравнит технологии для вашего участка и бюджета — бесплатно и без обязательств." />
    </>
  );
}
