import type { Metadata } from "next";
import { FinalCta } from "@/components/shared/final-cta";
import { PageHero } from "@/components/shared/page-hero";
import { Reveal } from "@/components/shared/reveal";
import { pageMetadata } from "@/lib/seo";
import { getSiteSettings } from "@/lib/settings";

export const metadata: Metadata = pageMetadata({
  title: "Как проходит строительство дома",
  description: "Этапы строительства дома: от расчёта и договора до передачи ключей. Фиксированная цена, поэтапная оплата и технический надзор.",
  path: "/build",
});

const STAGES = [
  { title: "Расчёт и консультация", time: "1–3 дня", text: "Вы получаете предварительный расчёт в конструкторе, инженер уточняет детали и отвечает на вопросы." },
  { title: "Выезд на участок", time: "1 день", text: "Бесплатно оцениваем рельеф, подъезды, коммуникации. При необходимости заказываем геологию." },
  { title: "Проект и смета", time: "2–4 недели", text: "Адаптируем проект под участок, готовим архитектурный и конструктивный разделы, подробную смету." },
  { title: "Договор с фиксированной ценой", time: "1 день", text: "Фиксируем стоимость, сроки и график платежей. Возможна ипотека и оплата через эскроу." },
  { title: "Фундамент и коробка", time: "1–3 месяца", text: "Возводим фундамент, стены, перекрытия и кровлю. Каждый этап принимает технический надзор." },
  { title: "Инженерия и отделка", time: "1–4 месяца", text: "Монтируем окна, инженерные системы и выполняем отделку в выбранной комплектации." },
  { title: "Сдача дома", time: "1 неделя", text: "Проводим приёмку вместе с вами, передаём исполнительную документацию и ключи." },
];

const PRINCIPLES = [
  { value: "0 ₽", label: "Доплат сверх договора" },
  { value: "7", label: "Этапов приёмки качества" },
  { value: "1×", label: "в неделю фото- и видеоотчёт" },
  { value: "15 лет", label: "Максимальная гарантия" },
];

export default async function BuildPage() {
  const settings = await getSiteSettings();
  return (
    <>
      <PageHero
        eyebrow="Как строим"
        title="Строительство, в котором всё понятно заранее"
        description="Каждый этап — с понятным результатом, сроком и стоимостью. Вы платите только за принятую работу."
        breadcrumbs={[{ name: "Как строим", path: "/build" }]}
      />

      <section className="container-page pb-16" aria-label="Принципы работы">
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-3xl border border-border bg-border lg:grid-cols-4">
          {PRINCIPLES.map((p) => (
            <div key={p.label} className="flex flex-col bg-white p-6 sm:p-8">
              <dt className="order-2 mt-2 text-sm text-muted-foreground">{p.label}</dt>
              <dd className="text-3xl font-semibold tracking-tight sm:text-4xl">{p.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="container-page pb-8" aria-labelledby="stages-title">
        <h2 id="stages-title" className="sr-only">Этапы строительства</h2>
        <ol className="relative border-l border-border pl-8 sm:pl-12">
          {STAGES.map((s, i) => (
            <li key={s.title} className="relative pb-14 last:pb-0">
              <span className="absolute top-0 -left-[2.55rem] flex size-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground tabular sm:-left-[3.55rem]">
                {i + 1}
              </span>
              <Reveal>
                <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:gap-10">
                  <div>
                    <h3 className="text-2xl font-semibold tracking-tight">{s.title}</h3>
                    <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">{s.text}</p>
                  </div>
                  <span className="self-start rounded-full bg-secondary px-3 py-1 text-sm font-medium">{s.time}</span>
                </div>
              </Reveal>
            </li>
          ))}
        </ol>
      </section>

      <FinalCta phone={settings.phone} />
    </>
  );
}
