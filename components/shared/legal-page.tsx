import { PageHero } from "./page-hero";

interface LegalSection {
  title: string;
  paragraphs: string[];
}

export function LegalPage({ title, path, updated, sections }: { title: string; path: string; updated: string; sections: LegalSection[] }) {
  return (
    <>
      <PageHero eyebrow="Документы" title={title} description={`Редакция от ${updated}`} breadcrumbs={[{ name: title, path }]} />
      <article className="container-page max-w-4xl pb-24">
        {sections.map((s, i) => (
          <section key={s.title} className="border-t border-border py-8">
            <h2 className="text-xl font-semibold">{i + 1}. {s.title}</h2>
            <div className="mt-4 space-y-3 text-[15px] leading-relaxed text-foreground/80">
              {s.paragraphs.map((p) => (
                <p key={p}>{p}</p>
              ))}
            </div>
          </section>
        ))}
      </article>
    </>
  );
}
