"use client";

import Image from "next/image";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface Plan {
  id: string;
  url: string;
  alt: string;
}

export function ProjectPlans({ plans }: { plans: Plan[] }) {
  if (!plans.length) return <p className="text-muted-foreground">Планировки предоставим по запросу.</p>;
  const label = (p: Plan, i: number) => (plans.length === 1 ? "План" : i === 0 ? "1 этаж" : `${i + 1} этаж`) + (p.alt.includes("мансард") ? " (мансарда)" : "");
  return (
    <Tabs defaultValue={plans[0].id}>
      {plans.length > 1 && (
        <TabsList>
          {plans.map((p, i) => (
            <TabsTrigger key={p.id} value={p.id}>{label(p, i)}</TabsTrigger>
          ))}
        </TabsList>
      )}
      {plans.map((p) => (
        <TabsContent key={p.id} value={p.id} className="mt-6">
          <a href={p.url} target="_blank" rel="noopener" className="relative block aspect-[16/11] overflow-hidden rounded-2xl border border-border bg-white" aria-label="Открыть планировку в полном размере">
            <Image src={p.url} alt={p.alt} fill sizes="(min-width: 1024px) 60vw, 100vw" className="object-contain" />
          </a>
        </TabsContent>
      ))}
    </Tabs>
  );
}
