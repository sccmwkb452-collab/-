import { useEffect } from "react";
import { useBoot } from "../components/BootContext";
import { HomeHeader, Page } from "../components/Layout";
import { Catalog } from "../components/home/Catalog";
import { Hero } from "../components/home/Hero";
import { Announcements, Faq, Footer, HowItWorks, PaymentsInfo, PromoBanners, RecentOrders, SupportCard, WhyUs } from "../components/home/Sections";
import { canAuthenticate } from "../lib/api";
import { useOrders } from "../lib/queries";

function scrollToCatalog() {
  document.getElementById("catalog")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function Home({ scrollTo }: { scrollTo?: "catalog" }) {
  const boot = useBoot();
  const recent = useOrders("all", 3, canAuthenticate);

  useEffect(() => {
    if (scrollTo === "catalog") {
      const t = setTimeout(scrollToCatalog, 250);
      return () => clearTimeout(t);
    }
  }, [scrollTo]);

  return (
    <>
      <HomeHeader />
      <Page className="space-y-10">
        <div className="space-y-3">
          <Announcements />
          <Hero onBuy={scrollToCatalog} />
        </div>
        <PromoBanners />
        <Catalog products={boot.catalog} />
        <HowItWorks />
        <WhyUs />
        <PaymentsInfo />
        {recent.data && <RecentOrders orders={recent.data.items} />}
        <Faq />
        <SupportCard />
        <Footer />
      </Page>
    </>
  );
}
