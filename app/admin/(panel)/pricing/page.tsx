import type { Metadata } from "next";
import { AdminPageHeader } from "@/components/admin/page-header";
import { PricingEditor } from "@/components/admin/pricing/pricing-editor";
import { prisma } from "@/lib/db";

export const metadata: Metadata = { title: "Ценообразование" };

export default async function PricingPage() {
  const [technologies, packages, houseTypes, options, params] = await Promise.all([
    prisma.technology.findMany({ orderBy: { sortOrder: "asc" } }),
    prisma.completionPackage.findMany({ orderBy: { sortOrder: "asc" } }),
    prisma.houseType.findMany({ orderBy: { sortOrder: "asc" } }),
    prisma.option.findMany({ orderBy: { sortOrder: "asc" } }),
    prisma.priceSetting.findMany({ orderBy: { sortOrder: "asc" } }),
  ]);
  return (
    <>
      <AdminPageHeader title="Ценообразование" description="Все цены калькулятора хранятся в базе данных и применяются на сайте сразу после сохранения." />
      <PricingEditor
        technologies={technologies.map((t) => ({ id: t.id, slug: t.slug, name: t.name, pricePerM2: t.pricePerM2, buildTime: t.buildTime, warranty: t.warranty, shortDescription: t.shortDescription, active: t.active }))}
        packages={packages.map((p) => ({ id: p.id, code: p.code, name: p.name, description: p.description, multiplier: p.multiplier, active: p.active }))}
        houseTypes={houseTypes.map((h) => ({ id: h.id, code: h.code, name: h.name, floors: h.floors, multiplier: h.multiplier, active: h.active }))}
        options={options.map((o) => ({ id: o.id, code: o.code, name: o.name, description: o.description, pricingType: o.pricingType, price: o.price, active: o.active, sortOrder: o.sortOrder }))}
        params={params.map((p) => ({ key: p.key, label: p.label, description: p.description, value: p.value, unit: p.unit }))}
      />
    </>
  );
}
