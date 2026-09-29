import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { JsonLd } from "./json-ld";
import { breadcrumbJsonLd } from "@/lib/seo";

interface PageHeroProps {
  eyebrow: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  breadcrumbs: { name: string; path: string }[];
  children?: React.ReactNode;
}

export function PageHero({ eyebrow, title, description, breadcrumbs, children }: PageHeroProps) {
  const crumbs = [{ name: "Главная", path: "/" }, ...breadcrumbs];
  return (
    <section className="container-page pt-28 pb-10 sm:pt-36 sm:pb-14">
      <nav aria-label="Хлебные крошки">
        <ol className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
          {crumbs.map((c, i) => (
            <li key={c.path} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="size-3 opacity-50" aria-hidden />}
              {i < crumbs.length - 1 ? (
                <Link href={c.path} className="hover:text-foreground">{c.name}</Link>
              ) : (
                <span aria-current="page" className="text-foreground">{c.name}</span>
              )}
            </li>
          ))}
        </ol>
      </nav>
      <div className="mt-8 flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <p className="eyebrow">{eyebrow}</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl lg:text-6xl">{title}</h1>
          {description && <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted-foreground sm:text-lg">{description}</p>}
        </div>
        {children}
      </div>
      <JsonLd data={breadcrumbJsonLd(crumbs)} />
    </section>
  );
}
