import "server-only";
import type { Project } from "@prisma/client";
import { prisma } from "@/lib/db";
import type { ProjectFormInput } from "@/lib/validation/admin";

export async function getProjectFormOptions() {
  const [houseTypes, technologies] = await Promise.all([
    prisma.houseType.findMany({ orderBy: { sortOrder: "asc" }, select: { id: true, name: true } }),
    prisma.technology.findMany({ orderBy: { sortOrder: "asc" }, select: { id: true, name: true } }),
  ]);
  return { houseTypes, technologies };
}

export function projectToForm(p: Project | null, fallbackHouseTypeId = ""): ProjectFormInput {
  return {
    title: p?.title ?? "",
    slug: p?.slug ?? "",
    subtitle: p?.subtitle ?? "",
    description: p?.description ?? "",
    area: p?.area ?? 120,
    bedrooms: p?.bedrooms ?? 3,
    bathrooms: p?.bathrooms ?? 2,
    houseTypeId: p?.houseTypeId ?? fallbackHouseTypeId,
    technologyId: p?.technologyId ?? "none",
    priceFrom: p?.priceFrom ?? 0,
    dimensions: p?.dimensions ?? "",
    ceilingHeight: p?.ceilingHeight ?? "",
    hasGarage: p?.hasGarage ?? false,
    hasTerrace: p?.hasTerrace ?? false,
    hasOffice: p?.hasOffice ?? false,
    hasSecondLight: p?.hasSecondLight ?? false,
    hasPanoramicWindows: p?.hasPanoramicWindows ?? false,
    featuresText: p?.features.join("\n") ?? "",
    status: p?.status ?? "DRAFT",
    featured: p?.featured ?? false,
    sortOrder: p?.sortOrder ?? 100,
    seoTitle: p?.seoTitle ?? "",
    seoDescription: p?.seoDescription ?? "",
  };
}
