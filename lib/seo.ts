import type { Metadata } from "next";

export function siteUrl(path = "") {
  const base = (process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000").replace(/\/$/, "");
  return `${base}${path}`;
}

interface PageMeta {
  title: string;
  description: string;
  path: string;
  image?: string;
  noIndex?: boolean;
}

export function pageMetadata({ title, description, path, image, noIndex }: PageMeta): Metadata {
  const images = [{ url: image ?? "/demo/hero.webp", width: 1600, height: 1000 }];
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { title, description, url: path, type: "website", locale: "ru_RU", images },
    twitter: { card: "summary_large_image", title, description, images: images.map((i) => i.url) },
    ...(noIndex ? { robots: { index: false, follow: false } } : {}),
  };
}

export function breadcrumbJsonLd(items: { name: string; path: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.name,
      item: siteUrl(item.path),
    })),
  };
}
