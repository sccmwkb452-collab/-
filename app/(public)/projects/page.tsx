import type { Metadata } from "next";
import { Suspense } from "react";
import { ProjectCatalog } from "@/components/projects/project-catalog";
import { FinalCta } from "@/components/shared/final-cta";
import { PageHero } from "@/components/shared/page-hero";
import { Skeleton } from "@/components/ui/skeleton";
import { getPublishedProjects } from "@/lib/data/projects";
import { pageMetadata } from "@/lib/seo";
import { getSiteSettings } from "@/lib/settings";

export const metadata: Metadata = pageMetadata({
  title: "Каталог проектов домов",
  description: "Проекты одноэтажных, двухэтажных домов и домов с мансардой. Фильтры по площади, этажности, спальням и цене. Стоимость строительства под ключ.",
  path: "/projects",
});

function CatalogSkeleton() {
  return (
    <div className="container-page grid gap-6 pb-24 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i}>
          <Skeleton className="aspect-[4/3] w-full rounded-2xl" />
          <Skeleton className="mt-5 h-6 w-2/3" />
          <Skeleton className="mt-3 h-4 w-full" />
        </div>
      ))}
    </div>
  );
}

export default async function ProjectsPage() {
  const [projects, settings] = await Promise.all([getPublishedProjects(), getSiteSettings()]);
  return (
    <>
      <PageHero
        eyebrow="Каталог"
        title="Проекты домов"
        description="Выберите проект, который нравится, — его можно адаптировать под участок и рассчитать стоимость с вашими параметрами."
        breadcrumbs={[{ name: "Проекты", path: "/projects" }]}
      />
      <Suspense fallback={<CatalogSkeleton />}>
        <ProjectCatalog projects={projects} />
      </Suspense>
      <FinalCta phone={settings.phone} title="Не нашли подходящий проект?" description="Рассчитайте стоимость дома с вашими параметрами — мы спроектируем его индивидуально." />
    </>
  );
}
