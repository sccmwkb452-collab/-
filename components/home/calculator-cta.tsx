import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { Reveal } from "@/components/shared/reveal";
import { Button } from "@/components/ui/button";
import { formatNumber } from "@/lib/utils";

interface CalculatorCtaProps {
  minPricePerM2: number;
  stepsCount: number;
}

const PREVIEW_STEPS = ["Тип дома", "Площадь", "Спальни", "Технология", "Комплектация", "Опции", "Сроки"];

export function CalculatorCta({ minPricePerM2, stepsCount }: CalculatorCtaProps) {
  return (
    <section className="container-page py-6 sm:py-10" aria-labelledby="calc-cta-title">
      <Reveal>
        <div className="relative overflow-hidden rounded-[2rem] bg-primary px-6 py-12 text-primary-foreground sm:px-12 sm:py-16 lg:px-16 lg:py-20">
          <div className="pointer-events-none absolute -top-40 -right-40 size-[32rem] rounded-full bg-accent/25 blur-3xl" aria-hidden />
          <div className="relative grid gap-12 lg:grid-cols-2 lg:items-center">
            <div>
              <p className="eyebrow">Онлайн-конструктор</p>
              <h2 id="calc-cta-title" className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
                Сколько будет стоить ваш дом?
              </h2>
              <p className="mt-5 max-w-md text-base leading-relaxed text-white/65 sm:text-lg">
                Ответьте на несколько вопросов — система рассчитает предварительную стоимость.
              </p>
              <Button asChild size="xl" variant="accent" className="mt-9">
                <Link href="/calculator">
                  Начать расчёт
                  <ArrowRight />
                </Link>
              </Button>
              <p className="mt-5 text-sm text-white/45">
                {stepsCount} шагов · около 2 минут · от {formatNumber(minPricePerM2)} ₽ за м²
              </p>
            </div>
            <ol className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {PREVIEW_STEPS.map((step, i) => (
                <li
                  key={step}
                  className="flex items-center gap-4 rounded-2xl border border-white/10 bg-white/[0.04] px-5 py-4 transition hover:border-white/25 hover:bg-white/[0.07]"
                >
                  <span className="text-sm font-semibold text-accent tabular">{String(i + 1).padStart(2, "0")}</span>
                  <span className="font-medium">{step}</span>
                </li>
              ))}
              <li className="flex items-center gap-4 rounded-2xl bg-accent px-5 py-4 font-semibold text-white">
                <span className="text-sm tabular">→</span>
                Ваш расчёт
              </li>
            </ol>
          </div>
        </div>
      </Reveal>
    </section>
  );
}
