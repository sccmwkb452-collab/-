import type { Metadata } from "next";
import { FaqList, faqSchema } from "@/components/shared/faq-list";
import { JsonLd } from "@/components/shared/json-ld";
import { FinalCta } from "@/components/shared/final-cta";
import { PageHero } from "@/components/shared/page-hero";
import { getFaqs } from "@/lib/data/projects";
import { pageMetadata } from "@/lib/seo";
import { getSiteSettings } from "@/lib/settings";

export const metadata: Metadata = pageMetadata({
  title: "Вопросы и ответы о строительстве дома",
  description: "Ответы на частые вопросы: точность расчёта, сроки, оплата, ипотека, гарантия и изменения проекта.",
  path: "/faq",
});

const CATEGORIES: Record<string, string> = { general: "Общие вопросы", construction: "Строительство", payment: "Оплата и гарантии" };

export default async function FaqPage() {
  const [faqs, settings] = await Promise.all([getFaqs(), getSiteSettings()]);
  const groups = Object.entries(CATEGORIES)
    .map(([key, title]) => ({ key, title, items: faqs.filter((f) => f.category === key) }))
    .filter((g) => g.items.length);
  const other = faqs.filter((f) => !(f.category in CATEGORIES));
  if (other.length) groups.push({ key: "other", title: "Другое", items: other });

  return (
    <>
      <PageHero eyebrow="FAQ" title="Вопросы и ответы" description="Собрали ответы на вопросы, которые чаще всего задают перед началом строительства." breadcrumbs={[{ name: "FAQ", path: "/faq" }]} />
      <div className="container-page space-y-16 pb-8">
        {groups.length ? (
          groups.map((g) => (
            <section key={g.key} className="grid gap-6 lg:grid-cols-12" aria-labelledby={`faq-${g.key}`}>
              <h2 id={`faq-${g.key}`} className="text-xl font-semibold lg:col-span-4">{g.title}</h2>
              <div className="lg:col-span-8">
                <FaqList items={g.items} withSchema={false} />
              </div>
            </section>
          ))
        ) : (
          <FaqList items={[]} />
        )}
      </div>
      {faqs.length > 0 && <JsonLd data={faqSchema(faqs)} />}
      <FinalCta phone={settings.phone} title="Остались вопросы?" description="Позвоните нам или рассчитайте стоимость — инженер ответит на все вопросы." />
    </>
  );
}
