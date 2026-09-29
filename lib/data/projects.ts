import "server-only";
import type { Prisma } from "@prisma/client";
import { cache } from "react";
import { prisma } from "@/lib/db";
import type { ProjectCardData } from "@/types/project";

const cardInclude = {
  houseType: true,
  technology: { select: { name: true } },
  images: { where: { kind: "COVER" }, orderBy: { sortOrder: "asc" }, take: 1 },
} satisfies Prisma.ProjectInclude;

type ProjectWithCard = Prisma.ProjectGetPayload<{ include: typeof cardInclude }>;

function toCard(p: ProjectWithCard): ProjectCardData {
  const cover = p.images[0];
  return {
    id: p.id,
    slug: p.slug,
    title: p.title,
    subtitle: p.subtitle,
    area: p.area,
    floors: p.houseType.floors,
    houseTypeCode: p.houseType.code,
    houseTypeName: p.houseType.name,
    bedrooms: p.bedrooms,
    bathrooms: p.bathrooms,
    priceFrom: p.priceFrom,
    technologyName: p.technology?.name ?? null,
    cover: cover ? { url: cover.url, alt: cover.alt || p.title } : null,
    hasGarage: p.hasGarage,
    hasTerrace: p.hasTerrace,
    hasOffice: p.hasOffice,
    hasSecondLight: p.hasSecondLight,
    hasPanoramicWindows: p.hasPanoramicWindows,
    featured: p.featured,
  };
}

export const getPublishedProjects = cache(async () => {
  const rows = await prisma.project.findMany({
    where: { status: "PUBLISHED" },
    include: cardInclude,
    orderBy: [{ sortOrder: "asc" }, { createdAt: "desc" }],
  });
  return rows.map(toCard);
});

export async function getFeaturedProjects(limit = 4) {
  const rows = await prisma.project.findMany({
    where: { status: "PUBLISHED" },
    include: cardInclude,
    orderBy: [{ featured: "desc" }, { sortOrder: "asc" }],
    take: limit,
  });
  return rows.map(toCard);
}

export async function getSimilarProjects(slug: string, area: number, limit = 3) {
  const rows = await prisma.project.findMany({
    where: { status: "PUBLISHED", slug: { not: slug }, area: { gte: area * 0.6, lte: area * 1.5 } },
    include: cardInclude,
    orderBy: { sortOrder: "asc" },
    take: limit,
  });
  return rows.map(toCard);
}

export const getProjectBySlug = cache(async (slug: string) => {
  if (!/^[a-z0-9-]{1,100}$/.test(slug)) return null;
  return prisma.project.findFirst({
    where: { slug, status: "PUBLISHED" },
    include: {
      houseType: true,
      technology: true,
      images: { orderBy: [{ kind: "asc" }, { sortOrder: "asc" }] },
    },
  });
});

export const getFaqs = cache(async (category?: string) =>
  prisma.faq.findMany({
    where: { published: true, ...(category ? { category } : {}) },
    orderBy: { sortOrder: "asc" },
  }),
);

export const getTechnologies = cache(async () =>
  prisma.technology.findMany({ where: { active: true }, orderBy: { sortOrder: "asc" } }),
);

export const getPackages = cache(async () =>
  prisma.completionPackage.findMany({ where: { active: true }, orderBy: { sortOrder: "asc" } }),
);

export const getOptions = cache(async () => prisma.option.findMany({ where: { active: true }, orderBy: { sortOrder: "asc" } }));
