import { ArrowUpRight, Bath, BedDouble, Layers, Ruler } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { formatArea, formatPrice, pluralize } from "@/lib/utils";
import type { ProjectCardData } from "@/types/project";

export function ProjectCard({ project, priority = false }: { project: ProjectCardData; priority?: boolean }) {
  const tags = [
    project.hasSecondLight && "Второй свет",
    project.hasGarage && "Гараж",
    project.hasTerrace && "Терраса",
  ].filter(Boolean) as string[];

  return (
    <article className="group relative flex flex-col">
      <Link href={`/projects/${project.slug}`} className="absolute inset-0 z-10 rounded-2xl" aria-label={`${project.title} — подробнее`} />
      <div className="relative aspect-[4/3] overflow-hidden rounded-2xl bg-sand/40">
        {project.cover ? (
          <Image
            src={project.cover.url}
            alt={project.cover.alt}
            fill
            priority={priority}
            sizes="(min-width: 1280px) 30vw, (min-width: 768px) 45vw, 100vw"
            className="object-cover transition-transform duration-[1.2s] ease-[var(--ease-premium)] group-hover:scale-[1.04]"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Изображение появится позже</div>
        )}
        <div className="absolute top-4 left-4 flex flex-wrap gap-1.5">
          {tags.slice(0, 2).map((t) => (
            <Badge key={t} variant="glass">{t}</Badge>
          ))}
        </div>
        <span className="absolute right-4 bottom-4 flex size-11 translate-y-2 items-center justify-center rounded-full bg-white text-foreground opacity-0 shadow-lg transition-all duration-500 group-hover:translate-y-0 group-hover:opacity-100">
          <ArrowUpRight className="size-5" />
        </span>
      </div>
      <div className="flex flex-1 flex-col pt-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-xl font-semibold tracking-tight">{project.title}</h3>
            {project.subtitle && <p className="mt-1 line-clamp-1 text-sm text-muted-foreground">{project.subtitle}</p>}
          </div>
        </div>
        <dl className="mt-4 grid grid-cols-4 gap-2 border-y border-border/80 py-3.5 text-sm">
          <div className="flex items-center gap-1.5" title="Площадь">
            <Ruler className="size-4 text-accent" aria-hidden />
            <dt className="sr-only">Площадь</dt>
            <dd className="font-medium tabular">{formatArea(project.area)}</dd>
          </div>
          <div className="flex items-center gap-1.5" title="Этажность">
            <Layers className="size-4 text-accent" aria-hidden />
            <dt className="sr-only">Этажность</dt>
            <dd className="font-medium">{project.houseTypeCode === "mansard" ? "Мансарда" : `${project.floors} эт.`}</dd>
          </div>
          <div className="flex items-center gap-1.5" title="Спальни">
            <BedDouble className="size-4 text-accent" aria-hidden />
            <dt className="sr-only">Спальни</dt>
            <dd className="font-medium">{project.bedrooms} {pluralize(project.bedrooms, ["сп.", "сп.", "сп."])}</dd>
          </div>
          <div className="flex items-center gap-1.5" title="Санузлы">
            <Bath className="size-4 text-accent" aria-hidden />
            <dt className="sr-only">Санузлы</dt>
            <dd className="font-medium">{project.bathrooms} с/у</dd>
          </div>
        </dl>
        <div className="mt-4 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Стоимость строительства</p>
            <p className="text-lg font-semibold tabular">от {formatPrice(project.priceFrom)}</p>
          </div>
          <span className="text-sm font-semibold text-foreground underline-offset-4 group-hover:underline">Подробнее</span>
        </div>
      </div>
    </article>
  );
}
