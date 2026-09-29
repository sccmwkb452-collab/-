"use client";

import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Check } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/button";

const ADVANTAGES = ["Индивидуальный расчёт", "Фиксированная комплектация", "Контроль строительства", "Гарантия"];

export function Hero({ image }: { image: string }) {
  const reduce = useReducedMotion();
  const fade = (delay: number) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 28 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 1, delay, ease: [0.22, 1, 0.36, 1] as const },
        };

  return (
    <section className="relative isolate flex min-h-[100svh] flex-col justify-end overflow-hidden bg-primary text-white">
      <motion.div
        className="absolute inset-0 -z-10"
        initial={reduce ? false : { scale: 1.08 }}
        animate={{ scale: 1 }}
        transition={{ duration: 2.4, ease: [0.22, 1, 0.36, 1] }}
      >
        <Image src={image} alt="Современный загородный дом вечером" fill priority sizes="100vw" className="object-cover object-[60%_center]" />
      </motion.div>
      <div className="absolute inset-0 -z-10 bg-gradient-to-t from-black/80 via-black/25 to-black/40" />
      <div className="absolute inset-0 -z-10 bg-gradient-to-r from-black/55 via-transparent to-transparent" />
      <div className="absolute inset-0 -z-10 bg-black/35 sm:hidden" />

      <div className="container-page pt-32 pb-10 sm:pb-14 lg:pb-20">
        <motion.p {...fade(0.1)} className="eyebrow text-white/70!">
          Строительство частных домов под ключ
        </motion.p>
        <motion.h1 {...fade(0.2)} className="mt-5 max-w-4xl text-[2.6rem] leading-[1.02] font-semibold tracking-[-0.035em] sm:text-6xl lg:text-7xl xl:text-[5.5rem]">
          Построим дом,
          <br />
          <span className="text-white/65">который подходит</span> именно вам
        </motion.h1>
        <motion.p {...fade(0.35)} className="mt-6 max-w-xl text-base leading-relaxed text-white/75 sm:text-lg">
          Выберите проект, настройте площадь и комплектацию и получите предварительный расчёт стоимости за несколько минут.
        </motion.p>
        <motion.div {...fade(0.5)} className="mt-9 flex flex-col gap-3 sm:flex-row">
          <Button asChild size="xl" variant="accent">
            <Link href="/calculator">
              Рассчитать стоимость
              <ArrowRight />
            </Link>
          </Button>
          <Button asChild size="xl" variant="outline" className="border-white/30 text-white hover:border-white hover:bg-white/10">
            <Link href="/projects">Смотреть проекты</Link>
          </Button>
        </motion.div>
        <motion.ul {...fade(0.7)} className="mt-12 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-white/15 pt-6 text-sm text-white/80 sm:flex sm:flex-wrap sm:gap-x-10">
          {ADVANTAGES.map((a) => (
            <li key={a} className="flex items-center gap-2.5">
              <span className="flex size-5 items-center justify-center rounded-full bg-accent">
                <Check className="size-3 text-white" strokeWidth={3} />
              </span>
              {a}
            </li>
          ))}
        </motion.ul>
      </div>
    </section>
  );
}
