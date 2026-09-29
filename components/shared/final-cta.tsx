import { ArrowRight, Phone } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { phoneHref } from "@/lib/utils";

interface FinalCtaProps {
  phone: string;
  title?: string;
  description?: string;
  href?: string;
  cta?: string;
}

export function FinalCta({
  phone,
  title = "Получите расчёт своего дома сегодня",
  description = "Настройте параметры в конструкторе — инженер проверит расчёт и подготовит подробную смету бесплатно.",
  href = "/calculator",
  cta = "Рассчитать стоимость",
}: FinalCtaProps) {
  return (
    <section className="container-page py-16 sm:py-24">
      <div className="relative isolate overflow-hidden rounded-[2rem] bg-primary text-white">
        <Image src="/demo/cta.webp" alt="" fill sizes="100vw" className="-z-10 object-cover opacity-60" />
        <div className="absolute inset-0 -z-10 bg-gradient-to-r from-black/85 via-black/60 to-black/10" />
        <div className="max-w-2xl px-6 py-14 sm:px-12 sm:py-20 lg:px-16 lg:py-24">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-5xl">{title}</h2>
          <p className="mt-5 text-base leading-relaxed text-white/70 sm:text-lg">{description}</p>
          <div className="mt-9 flex flex-col gap-3 sm:flex-row">
            <Button asChild size="xl" variant="accent">
              <Link href={href}>
                {cta}
                <ArrowRight />
              </Link>
            </Button>
            <Button asChild size="xl" variant="outline" className="border-white/30 text-white hover:border-white hover:bg-white/10">
              <a href={phoneHref(phone)}>
                <Phone />
                {phone}
              </a>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
