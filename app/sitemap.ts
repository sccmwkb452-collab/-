import type { MetadataRoute } from "next";
import { prisma } from "@/lib/db";
import { siteUrl } from "@/lib/seo";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticPages = ["", "/projects", "/calculator", "/technology", "/build", "/about", "/contacts", "/faq", "/privacy", "/terms"];
  const projects = await prisma.project.findMany({ where: { status: "PUBLISHED" }, select: { slug: true, updatedAt: true } });
  return [
    ...staticPages.map((p) => ({
      url: siteUrl(p || "/"),
      changeFrequency: "weekly" as const,
      priority: p === "" ? 1 : p === "/projects" || p === "/calculator" ? 0.9 : 0.6,
    })),
    ...projects.map((p) => ({ url: siteUrl(`/projects/${p.slug}`), lastModified: p.updatedAt, changeFrequency: "monthly" as const, priority: 0.8 })),
  ];
}
