import type { Metadata } from "next";
import Image from "next/image";
import { FinalCta } from "@/components/shared/final-cta";
import { PageHero } from "@/components/shared/page-hero";
import { Reveal } from "@/components/shared/reveal";
import { pageMetadata } from "@/lib/seo";
import { getSiteSettings } from "@/lib/settings";

export async function generateMetadata(): Promise<Metadata> {
  const s = await getSiteSettings();
  return pageMetadata({ title: `О компании ${s.companyName}`, description: s.description, path: "/about" });
}

const VALUES = [
  { title: "Архитектура", text: "Проектируем дома, в которых удобно жить: продуманные сценарии, свет, пропорции и связь с участком." },
  { title: "Инженерия", text: "Собственный конструкторский отдел рассчитывает каждый узел, а технадзор проверяет исполнение на площадке." },
  { title: "Честность", text: "Фиксированная цена, прозрачная смета и поэтапная оплата. Никаких «непредвиденных» доплат." },
  { title: "Сервис", text: "Один менеджер на весь проект, еженедельные отчёты и гарантийное обслуживание после заселения." },
];

export default async function AboutPage() {
  const settings = await getSiteSettings();
  return (
    <>
      <PageHero
        eyebrow="О компании"
        title={settings.slogan}
        description={settings.description}
        breadcrumbs={[{ name: "О компании", path: "/about" }]}
      />
      <section className="container-page">
        <Reveal>
          <div className="relative aspect-[16/9] overflow-hidden rounded-[2rem] bg-sand/40 sm:aspect-[21/9]">
            <Image src="/demo/about.webp" alt="Загородный дом, построенный компанией" fill sizes="100vw" className="object-cover" />
          </div>
        </Reveal>
      </section>

      <section className="container-page grid gap-12 py-20 sm:py-28 lg:grid-cols-12" aria-labelledby="mission-title">
        <div className="lg:col-span-5">
          <p className="eyebrow">Наш подход</p>
          <h2 id="mission-title" className="mt-4 text-3xl font-semibold tracking-tight sm:text-5xl">Дом — это не квадратные метры, а сценарий жизни</h2>
        </div>
        <div className="space-y-5 text-[15px] leading-relaxed text-foreground/80 sm:text-base lg:col-span-6 lg:col-start-7">
          <p>
            {settings.companyName} объединяет архитекторов, инженеров и строителей в одну команду. Мы берём на себя весь путь: подбор проекта, адаптацию под участок, получение разрешений, строительство и подключение коммуникаций.
          </p>
          <p>
            Мы убеждены, что клиент должен понимать стоимость дома с первого дня. Поэтому сделали открытый калькулятор: вы сами настраиваете параметры и видите, из чего складывается цена, ещё до встречи с менеджером.
          </p>
          <p className="rounded-2xl bg-secondary p-5 text-sm text-muted-foreground">
            Это демонстрационный сайт. Названия, контакты и цифры можно заменить в разделе «Настройки» админ-панели.
          </p>
        </div>
      </section>

      <section className="border-t border-border bg-white py-20 sm:py-28" aria-labelledby="values-title">
        <div className="container-page">
          <h2 id="values-title" className="text-3xl font-semibold tracking-tight sm:text-4xl">Во что мы верим</h2>
          <div className="mt-12 grid gap-px overflow-hidden rounded-3xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
            {VALUES.map((v, i) => (
              <div key={v.title} className="bg-white p-7 sm:p-9">
                <span className="text-sm font-semibold text-accent tabular">0{i + 1}</span>
                <h3 className="mt-10 text-xl font-semibold">{v.title}</h3>
                <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">{v.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <FinalCta phone={settings.phone} />
    </>
  );
}
