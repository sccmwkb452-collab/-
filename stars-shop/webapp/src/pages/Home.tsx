import { useEffect } from "react";
import { useBoot } from "../components/BootContext";
import { HomeHeader, Page } from "../components/Layout";
import { Catalog } from "../components/home/Catalog";
import { Greeting, LuckyCard, ReferralCard } from "../components/home/HomeCards";
import { PremiumCard } from "../components/premium/PremiumParts";
import { Announcements, Footer, PromoBanners, RecentOrders } from "../components/home/Sections";

function scrollToCatalog() {
  document.getElementById("catalog")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

/** Header → greeting → Lucky Buy → «Купить Telegram Stars» (own amount and
 * packages) → referrals → recent orders; the bottom navigation is in App. */
export function Home({ scrollTo }: { scrollTo?: "catalog" }) {
  const boot = useBoot();

  useEffect(() => {
    if (scrollTo === "catalog") {
      const t = setTimeout(scrollToCatalog, 250);
      return () => clearTimeout(t);
    }
  }, [scrollTo]);

  return (
    <>
      <HomeHeader />
      <Page className="space-y-6">
        <Greeting />
        <Announcements />
        <LuckyCard />
        <Catalog products={boot.catalog} />
        <PremiumCard />
        <PromoBanners />
        <ReferralCard />
        <RecentOrders />
        <Footer />
      </Page>
    </>
  );
}
