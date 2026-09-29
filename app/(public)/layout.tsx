import { Footer } from "@/components/layout/footer";
import { Header } from "@/components/layout/header";
import { AnalyticsScripts } from "@/components/shared/analytics-scripts";
import { JsonLd } from "@/components/shared/json-ld";
import { siteUrl } from "@/lib/seo";
import { getSiteSettings } from "@/lib/settings";

export default async function PublicLayout({ children }: { children: React.ReactNode }) {
  const settings = await getSiteSettings();
  const sameAs = [settings.telegram, settings.whatsapp, settings.vk].filter(Boolean);
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-full focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground">
        Перейти к содержимому
      </a>
      <Header companyName={settings.companyName} logoUrl={settings.logoUrl} phone={settings.phone} workingHours={settings.workingHours} />
      <main id="main">{children}</main>
      <Footer settings={settings} />
      <AnalyticsScripts />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "HomeAndConstructionBusiness",
          name: settings.companyName,
          slogan: settings.slogan,
          description: settings.description,
          url: siteUrl(),
          telephone: settings.phone,
          email: settings.email,
          address: { "@type": "PostalAddress", streetAddress: settings.address, addressCountry: "RU" },
          logo: settings.logoUrl ? siteUrl(settings.logoUrl) : siteUrl("/icon.svg"),
          ...(sameAs.length ? { sameAs } : {}),
        }}
      />
    </>
  );
}
