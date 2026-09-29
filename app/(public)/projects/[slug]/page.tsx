import { ArrowRight, Bath, BedDouble, Check, Layers, MessageSquare, Ruler } from "lucide-react";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { LeadDialog } from "@/components/forms/lead-dialog";
import { ProjectCard } from "@/components/projects/project-card";
import { ProjectGallery } from "@/components/projects/project-gallery";
import { ProjectPlans } from "@/components/projects/project-plans";
import { ProjectViewTracker } from "@/components/projects/project-view-tracker";
import { FaqList } from "@/components/shared/faq-list";
import { FinalCta } from "@/components/shared/final-cta";
import { JsonLd } from "@/components/shared/json-ld";
import { Button } from "@/components/ui/button";
import { getFaqs, getOptions, getProjectBySlug, getSimilarProjects } from "@/lib/data/projects";
import { getPricingConfig } from "@/lib/pricing/config";
import { calculateEstimate } from "@/lib/pricing/engine";
import { breadcrumbJsonLd, pageMetadata, siteUrl } from "@/lib/seo";
import { getSiteSettings } from "@/lib/settings";
import { formatArea, formatNumber, formatPrice } from "@/lib/utils";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const project = await getProjectBySlug(slug);
  if (!project) return { title: "Проект не найден", robots: { index: false } };
  const cover = project.images.find((i) => i.kind === "COVER");
  return pageMetadata({
    title: project.seoTitle || `${project.title} — ${project.area} м²`,
    description: project.seoDescription || project.subtitle || project.description.slice(0, 160),
    path: `/projects/${project.slug}`,
    image: cover?.url,
  });
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-28 border-t border-border py-12 sm:py-16">
      <h2 id={`${id}-title`} className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h2>
      <div className="mt-8">{children}</div>
    </section>
  );
}

export default async function ProjectPage({ params }: Props) {
  const { slug } = await params;
  const project = await getProjectBySlug(slug);
  if (!project) notFound();

  const [settings, config, options, faqs, similar] = await Promise.all([
    getSiteSettings(),
    getPricingConfig(),
    getOptions(),
    getFaqs("general"),
    getSimilarProjects(project.slug, project.area),
  ]);

  const visuals = project.images.filter((i) => i.kind !== "PLAN");
  const gallery = project.images.filter((i) => i.kind === "GALLERY");
  const plans = project.images.filter((i) => i.kind === "PLAN");
  const techSlug = project.technology?.slug ?? config.technologies[0]?.slug;
  const floorsLabel = project.houseType.code === "mansard" ? "С мансардой" : `${project.houseType.floors} ${project.houseType.floors === 1 ? "этаж" : "этажа"}`;

  const packagePrices = techSlug
    ? config.packages.map((p) => ({
        ...p,
        total: calculateEstimate(config, {
          houseType: project.houseType.code,
          area: project.area,
          bedrooms: project.bedrooms,
          technology: techSlug,
          package: p.code,
          options: [],
        }).total,
      }))
    : [];

  const specs: [string, string][] = [
    ["Общая площадь", formatArea(project.area)],
    ...(project.dimensions ? [["Габариты", project.dimensions] as [string, string]] : []),
    ["Этажность", floorsLabel],
    ["Спальни", String(project.bedrooms)],
    ["Санузлы", String(project.bathrooms)],
    ...(project.ceilingHeight ? [["Высота потолков", `${String(project.ceilingHeight).replace(".", ",")} м`] as [string, string]] : []),
    ["Технология", project.technology?.name ?? "На выбор"],
    ["Гараж", project.hasGarage ? "Есть" : "Нет"],
    ["Терраса", project.hasTerrace ? "Есть" : "Нет"],
    ["Кабинет", project.hasOffice ? "Есть" : "Нет"],
    ["Второй свет", project.hasSecondLight ? "Есть" : "Нет"],
    ["Панорамные окна", project.hasPanoramicWindows ? "Есть" : "Нет"],
  ];

  const calcHref = `/calculator?project=${project.slug}`;
  const crumbs = [
    { name: "Главная", path: "/" },
    { name: "Проекты", path: "/projects" },
    { name: project.title, path: `/projects/${project.slug}` },
  ];

  return (
    <>
      <ProjectViewTracker slug={project.slug} />
      <div className="container-page pt-24 sm:pt-28">
        <nav aria-label="Хлебные крошки" className="text-xs text-muted-foreground">
          <Link href="/projects" className="hover:text-foreground">← Все проекты</Link>
        </nav>

        <div className="mt-6 grid gap-x-10 gap-y-10 lg:grid-cols-[1fr_24rem] xl:gap-x-14">
          <div className="min-w-0 lg:col-start-1 lg:row-start-1">
            <ProjectGallery images={visuals.map((i) => ({ id: i.id, url: i.url, alt: i.alt }))} title={project.title} />
          </div>

          <aside className="lg:col-start-2 lg:row-span-2 lg:row-start-1" aria-label="Параметры и стоимость">
            <div className="lg:sticky lg:top-24">
              <p className="eyebrow">{project.houseType.name} дом</p>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">{project.title}</h1>
              {project.subtitle && <p className="mt-3 text-muted-foreground">{project.subtitle}</p>}
              <dl className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border">
                {[
                  { icon: Ruler, label: "Площадь", value: formatArea(project.area) },
                  { icon: Layers, label: "Этажность", value: floorsLabel },
                  { icon: BedDouble, label: "Спальни", value: String(project.bedrooms) },
                  { icon: Bath, label: "Санузлы", value: String(project.bathrooms) },
                ].map((s) => (
                  <div key={s.label} className="bg-white p-4">
                    <dt className="flex items-center gap-2 text-xs text-muted-foreground">
                      <s.icon className="size-3.5 text-accent" />
                      {s.label}
                    </dt>
                    <dd className="mt-1.5 text-lg font-semibold">{s.value}</dd>
                  </div>
                ))}
              </dl>
              <div className="mt-6 rounded-2xl bg-primary p-6 text-primary-foreground">
                <p className="text-sm text-white/55">Стоимость строительства</p>
                <p className="mt-1 text-3xl font-semibold tracking-tight tabular">от {formatPrice(project.priceFrom)}</p>
                <p className="mt-2 text-xs text-white/45">Предварительно, в комплектации «Тёплый контур»</p>
                <Button asChild variant="accent" size="lg" className="mt-6 w-full whitespace-normal">
                  <Link href={calcHref}>
                    Рассчитать стоимость этого проекта
                    <ArrowRight />
                  </Link>
                </Button>
                <LeadDialog
                  projectSlug={project.slug}
                  title="Консультация по проекту"
                  description={`Расскажем подробнее о проекте ${project.title} и ответим на вопросы.`}
                  trigger={
                    <Button variant="outline" size="lg" className="mt-2 w-full border-white/20 text-white hover:border-white/50 hover:bg-white/5">
                      <MessageSquare />
                      Получить консультацию
                    </Button>
                  }
                />
              </div>
            </div>
          </aside>

          <div className="min-w-0 lg:col-start-1 lg:row-start-2">
            <nav aria-label="Разделы проекта" className="sticky top-16 z-20 -mx-4 overflow-x-auto border-b border-border bg-background/90 px-4 backdrop-blur sm:top-16">
              <ul className="flex gap-6 text-sm font-medium whitespace-nowrap">
                {[
                  ["description", "Описание"],
                  ["plans", "Планировки"],
                  ["specs", "Характеристики"],
                  ["packages", "Комплектация"],
                  ["technology", "Технология"],
                  ["gallery", "Галерея"],
                  ["options", "Опции"],
                  ["faq", "FAQ"],
                ].map(([id, label]) => (
                  <li key={id}>
                    <a href={`#${id}`} className="block py-4 text-muted-foreground transition hover:text-foreground">{label}</a>
                  </li>
                ))}
              </ul>
            </nav>

            <Section id="description" title="Описание">
              <p className="max-w-3xl text-lg leading-relaxed text-foreground/85">{project.description}</p>
              {project.features.length > 0 && (
                <ul className="mt-8 grid gap-3 sm:grid-cols-2">
                  {project.features.map((f) => (
                    <li key={f} className="flex items-start gap-3 rounded-xl bg-white p-4 text-[15px]">
                      <Check className="mt-0.5 size-4 shrink-0 text-accent" />
                      {f}
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section id="plans" title="Планировки">
              <ProjectPlans plans={plans.map((p) => ({ id: p.id, url: p.url, alt: p.alt }))} />
            </Section>

            <Section id="specs" title="Характеристики">
              <dl className="grid overflow-hidden rounded-2xl border border-border bg-white sm:grid-cols-2">
                {specs.map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4 border-b border-border px-5 py-4 text-[15px] sm:odd:border-r">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd className="text-right font-medium">{v}</dd>
                  </div>
                ))}
              </dl>
            </Section>

            <Section id="packages" title="Комплектация и стоимость">
              <p className="-mt-4 mb-8 max-w-2xl text-muted-foreground">
                Предварительная стоимость проекта в разных комплектациях{project.technology ? ` (технология: ${project.technology.name.toLowerCase()})` : ""}.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                {packagePrices.map((p) => (
                  <div key={p.code} className="flex flex-col rounded-2xl border border-border bg-white p-6">
                    <div className="flex items-baseline justify-between gap-4">
                      <h3 className="text-lg font-semibold">{p.name}</h3>
                      <p className="font-semibold tabular">от {formatPrice(p.total)}</p>
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">{p.description}</p>
                    <ul className="mt-4 space-y-1.5 text-sm">
                      {p.includes.map((inc) => (
                        <li key={inc} className="flex gap-2">
                          <span className="mt-2 size-1 shrink-0 rounded-full bg-accent" />
                          {inc}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </Section>

            {project.technology && (
              <Section id="technology" title={`Технология: ${project.technology.name}`}>
                <div className="grid gap-8 md:grid-cols-2">
                  <p className="text-[15px] leading-relaxed text-foreground/85">{project.technology.description}</p>
                  <ul className="space-y-3">
                    {project.technology.advantages.map((a) => (
                      <li key={a} className="flex items-center gap-3 border-b border-border pb-3 text-[15px]">
                        <Check className="size-4 text-accent" />
                        {a}
                      </li>
                    ))}
                    <li className="flex justify-between pt-1 text-sm text-muted-foreground">
                      <span>Срок строительства: {project.technology.buildTime}</span>
                      <span>{project.technology.warranty}</span>
                    </li>
                  </ul>
                </div>
                <Button asChild variant="link" className="mt-6">
                  <Link href={`/technology#${project.technology.slug}`}>Подробнее о технологиях →</Link>
                </Button>
              </Section>
            )}

            {gallery.length > 0 && (
              <Section id="gallery" title="Галерея">
                <div className="grid gap-3 sm:grid-cols-2">
                  {gallery.map((g, i) => (
                    <div key={g.id} className={i === 0 ? "relative aspect-[16/10] overflow-hidden rounded-2xl sm:col-span-2" : "relative aspect-[16/10] overflow-hidden rounded-2xl"}>
                      <Image src={g.url} alt={g.alt || project.title} fill sizes="(min-width: 1024px) 50vw, 100vw" className="object-cover transition-transform duration-700 hover:scale-[1.03]" />
                    </div>
                  ))}
                </div>
              </Section>
            )}

            <Section id="options" title="Дополнительные опции">
              <div className="grid gap-3 sm:grid-cols-2">
                {options.map((o) => (
                  <div key={o.id} className="flex items-start justify-between gap-4 rounded-2xl bg-white p-5">
                    <div>
                      <p className="font-semibold">{o.name}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{o.description}</p>
                    </div>
                    <p className="shrink-0 text-sm font-semibold whitespace-nowrap tabular">
                      {o.pricingType === "PER_M2" ? `${formatNumber(o.price)} ₽/м²` : `+${formatPrice(o.price)}`}
                    </p>
                  </div>
                ))}
              </div>
            </Section>

            <Section id="faq" title="Вопросы о проекте">
              <FaqList items={faqs} withSchema={false} />
            </Section>
          </div>

        </div>
      </div>

      {similar.length > 0 && (
        <section className="container-page border-t border-border pt-16 sm:pt-20" aria-labelledby="similar-title">
          <h2 id="similar-title" className="text-3xl font-semibold tracking-tight">Похожие проекты</h2>
          <div className="mt-10 grid gap-x-6 gap-y-12 md:grid-cols-2 xl:grid-cols-3">
            {similar.map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        </section>
      )}

      <FinalCta phone={settings.phone} title={`Рассчитайте ${project.title} со своими параметрами`} href={calcHref} cta="Рассчитать этот проект" />

      <JsonLd data={breadcrumbJsonLd(crumbs)} />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "Product",
          name: project.title,
          description: project.description,
          image: visuals.map((v) => siteUrl(v.url)),
          url: siteUrl(`/projects/${project.slug}`),
          brand: { "@type": "Brand", name: settings.companyName },
          category: "Строительство частного дома",
          additionalProperty: [
            { "@type": "PropertyValue", name: "Площадь", value: project.area, unitCode: "MTK" },
            { "@type": "PropertyValue", name: "Спальни", value: project.bedrooms },
            { "@type": "PropertyValue", name: "Санузлы", value: project.bathrooms },
          ],
          offers: {
            "@type": "Offer",
            priceCurrency: "RUB",
            price: project.priceFrom,
            availability: "https://schema.org/InStock",
            url: siteUrl(`/projects/${project.slug}`),
          },
        }}
      />
    </>
  );
}
