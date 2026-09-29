import type { Metadata } from "next";
import { CalculatorWizard } from "@/components/calculator/calculator-wizard";
import type { CalculatorState, ProjectContext } from "@/components/calculator/types";
import { PageHero } from "@/components/shared/page-hero";
import { getProjectBySlug } from "@/lib/data/projects";
import { getPricingConfig } from "@/lib/pricing/config";
import { projectPreset } from "@/lib/pricing/project-preset";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Калькулятор стоимости строительства дома",
  description: "Рассчитайте стоимость строительства дома онлайн: тип дома, площадь, технология, комплектация и опции. Предварительный расчёт за 2 минуты.",
  path: "/calculator",
});

type Props = { searchParams: Promise<{ project?: string | string[] }> };

export default async function CalculatorPage({ searchParams }: Props) {
  const { project: projectParam } = await searchParams;
  const slug = typeof projectParam === "string" ? projectParam : undefined;
  const [config, project] = await Promise.all([getPricingConfig(), slug ? getProjectBySlug(slug) : null]);

  let initial: Partial<CalculatorState> = {};
  let context: ProjectContext | null = null;
  if (project) {
    const preset = projectPreset(project);
    const validOptions = new Set(config.options.map((o) => o.code));
    initial = {
      houseType: config.houseTypes.some((h) => h.code === preset.houseType) ? preset.houseType : null,
      area: Math.min(Math.max(preset.area, config.params.areaMin), config.params.areaMax),
      bedrooms: preset.bedrooms,
      technology: config.technologies.some((t) => t.slug === preset.technology) ? preset.technology : null,
      options: preset.options.filter((o) => validOptions.has(o)),
    };
    context = { slug: project.slug, title: project.title, cover: project.images.find((i) => i.kind === "COVER")?.url ?? null };
  }

  const ready = config.houseTypes.length > 0 && config.technologies.length > 0 && config.packages.length > 0;

  return (
    <>
      <PageHero
        eyebrow="Конструктор дома"
        title={context ? `Расчёт: ${context.title}` : "Сколько будет стоить ваш дом?"}
        description={
          context
            ? "Параметры проекта уже подставлены — измените площадь, технологию, комплектацию и опции под себя."
            : "Ответьте на 7 вопросов — система рассчитает предварительную стоимость строительства."
        }
        breadcrumbs={[{ name: "Калькулятор", path: "/calculator" }]}
      />
      {ready ? (
        <CalculatorWizard config={config} initial={initial} project={context} />
      ) : (
        <div className="container-page pb-24">
          <div className="rounded-3xl border border-dashed p-12 text-center text-muted-foreground">
            Калькулятор временно недоступен: не настроены цены. Позвоните нам — рассчитаем стоимость по телефону.
          </div>
        </div>
      )}
    </>
  );
}
