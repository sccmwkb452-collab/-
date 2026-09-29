import "@fontsource-variable/manrope";
import "./globals.css";
import type { Metadata, Viewport } from "next";
import { Toaster } from "@/components/ui/sonner";
import { siteUrl } from "@/lib/seo";
import { brandCss, getSiteSettings } from "@/lib/settings";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const settings = await getSiteSettings();
  return {
    metadataBase: new URL(siteUrl()),
    title: { default: settings.seoTitle, template: `%s — ${settings.companyName}` },
    description: settings.seoDescription,
    applicationName: settings.companyName,
    openGraph: { siteName: settings.companyName, locale: "ru_RU", type: "website" },
  };
}

export const viewport: Viewport = {
  themeColor: "#F7F6F2",
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const settings = await getSiteSettings();
  return (
    <html lang="ru" data-scroll-behavior="smooth">
      <head>
        <style dangerouslySetInnerHTML={{ __html: brandCss(settings) }} />
      </head>
      <body className="min-h-dvh">
        {children}
        <Toaster />
      </body>
    </html>
  );
}
