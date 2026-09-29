"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import type { ActionResult } from "@/lib/actions/result";
import { saveHouseTypesAction, savePackagesAction, savePriceParamsAction, saveTechnologiesAction } from "@/lib/actions/pricing";
import { calculateEstimate } from "@/lib/pricing/engine";
import type { PricingConfig } from "@/lib/pricing/types";
import { OptionsEditor, type OptionRow } from "./options-editor";
import { FormulaPreview } from "./formula-preview";
import { NumberCell, PricingSection, TextCell } from "./section";

export interface TechRow { id: string; slug: string; name: string; pricePerM2: number; buildTime: string; warranty: string; shortDescription: string; active: boolean }
export interface PackageRow { id: string; code: string; name: string; description: string; multiplier: number; active: boolean }
export interface HouseTypeRow { id: string; code: string; name: string; floors: number; multiplier: number; active: boolean }
export interface ParamRow { key: string; label: string; description: string; value: number; unit: string }

interface EditorProps {
  technologies: TechRow[];
  packages: PackageRow[];
  houseTypes: HouseTypeRow[];
  options: OptionRow[];
  params: ParamRow[];
}

export function useSaver() {
  const router = useRouter();
  const [pending, start] = useTransition();
  const save = (fn: () => Promise<ActionResult<unknown>>, after?: () => void) =>
    start(async () => {
      const res = await fn();
      if (res.ok) {
        toast.success(res.message ?? "Сохранено");
        after?.();
        router.refresh();
      } else toast.error(res.error);
    });
  return { pending, save };
}

export const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const patch = <T,>(list: T[], i: number, p: Partial<T>) => list.map((row, idx) => (idx === i ? { ...row, ...p } : row));

export function PricingEditor(props: EditorProps) {
  const [techs, setTechs] = useState(props.technologies);
  const [packs, setPacks] = useState(props.packages);
  const [types, setTypes] = useState(props.houseTypes);
  const [params, setParams] = useState(props.params);
  const [options, setOptions] = useState<OptionRow[]>(props.options);
  const tech = useSaver();
  const pack = useSaver();
  const type = useSaver();
  const param = useSaver();

  const preview = useMemo(() => {
    const p = Object.fromEntries(params.map((x) => [x.key, x.value]));
    const config: PricingConfig = {
      houseTypes: types.map((t) => ({ code: t.code, name: t.name, description: "", floors: t.floors, multiplier: t.multiplier })),
      technologies: techs.map((t) => ({ slug: t.slug, name: t.name, shortDescription: "", pricePerM2: t.pricePerM2 })),
      packages: packs.map((x) => ({ code: x.code, name: x.name, description: "", includes: [], multiplier: x.multiplier })),
      options: options.map((o) => ({ code: o.code, name: o.name, description: "", pricingType: o.pricingType, price: o.price })),
      params: {
        areaMin: p.area_min ?? 50,
        areaMax: p.area_max ?? 400,
        bedroomBaseCount: p.bedroom_base_count ?? 3,
        bedroomSurcharge: p.bedroom_surcharge ?? 0,
        roundingStep: p.rounding_step ?? 1,
        spreadPercent: p.estimate_spread_percent ?? 0,
      },
    };
    const ht = types.find((t) => t.code === "two-story") ?? types[0];
    const tc = techs[0];
    const pk = packs[packs.length - 1];
    if (!ht || !tc || !pk) return null;
    const picked = options.slice(0, 2);
    try {
      return {
        label: `156 м², ${ht.name.toLowerCase()}, ${tc.name.toLowerCase()}, «${pk.name}», 4 спальни${picked.length ? `, ${picked.map((o) => o.name.toLowerCase()).join(" + ")}` : ""}`,
        result: calculateEstimate(config, { houseType: ht.code, area: 156, bedrooms: 4, technology: tc.slug, package: pk.code, options: picked.map((o) => o.code) }),
      };
    } catch {
      return null;
    }
  }, [techs, packs, types, params, options]);

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
      <div className="min-w-0 space-y-6">
        <PricingSection
          title="Технологии · стоимость за м²"
          description="Базовая цена квадратного метра в комплектации «Под ключ»."
          dirty={!same(techs, props.technologies)}
          pending={tech.pending}
          onSave={() => tech.save(() => saveTechnologiesAction(techs.map(({ slug: _slug, ...t }) => t)))}
        >
          <div className="space-y-3">
            {techs.map((t, i) => (
              <div key={t.id} className="grid gap-2 rounded-xl border border-border p-3 sm:grid-cols-[1fr_10rem_8rem_auto] sm:items-center">
                <TextCell label="Название" value={t.name} onChange={(v) => setTechs(patch(techs, i, { name: v }))} />
                <NumberCell label={`Цена за м², ${t.name}`} value={t.pricePerM2} step={500} suffix="₽/м²" onChange={(v) => setTechs(patch(techs, i, { pricePerM2: v }))} />
                <TextCell label="Срок" value={t.buildTime} onChange={(v) => setTechs(patch(techs, i, { buildTime: v }))} />
                <label className="flex items-center gap-2 text-sm">
                  <Switch checked={t.active} onCheckedChange={(v) => setTechs(patch(techs, i, { active: v }))} aria-label={`${t.name} активна`} />
                  <span className="sm:hidden">Активна</span>
                </label>
              </div>
            ))}
          </div>
        </PricingSection>

        <PricingSection
          title="Комплектации · коэффициенты"
          description="Множитель к стоимости «Под ключ». Например, 0,8 — тёплый контур стоит 80% от цены под ключ."
          dirty={!same(packs, props.packages)}
          pending={pack.pending}
          onSave={() => pack.save(() => savePackagesAction(packs.map(({ code: _code, ...p }) => p)))}
        >
          <div className="space-y-3">
            {packs.map((p, i) => (
              <div key={p.id} className="grid gap-2 rounded-xl border border-border p-3 sm:grid-cols-[12rem_8rem_1fr_auto] sm:items-center">
                <TextCell label="Название" value={p.name} onChange={(v) => setPacks(patch(packs, i, { name: v }))} />
                <NumberCell label={`Коэффициент, ${p.name}`} value={p.multiplier} step={0.01} suffix="×" onChange={(v) => setPacks(patch(packs, i, { multiplier: v }))} />
                <TextCell label="Описание" value={p.description} onChange={(v) => setPacks(patch(packs, i, { description: v }))} />
                <Switch checked={p.active} onCheckedChange={(v) => setPacks(patch(packs, i, { active: v }))} aria-label={`${p.name} активна`} />
              </div>
            ))}
          </div>
        </PricingSection>

        <PricingSection
          title="Этажность · коэффициенты"
          description="Одноэтажный дом дороже за м² из-за большего фундамента и кровли."
          dirty={!same(types, props.houseTypes)}
          pending={type.pending}
          onSave={() => type.save(() => saveHouseTypesAction(types.map(({ id, name, multiplier, active }) => ({ id, name, multiplier, active }))))}
        >
          <div className="grid gap-3 sm:grid-cols-3">
            {types.map((t, i) => (
              <div key={t.id} className="space-y-2 rounded-xl border border-border p-3">
                <TextCell label="Название" value={t.name} onChange={(v) => setTypes(patch(types, i, { name: v }))} />
                <NumberCell label={`Коэффициент, ${t.name}`} value={t.multiplier} step={0.01} suffix="×" onChange={(v) => setTypes(patch(types, i, { multiplier: v }))} />
                <label className="flex items-center justify-between text-sm text-muted-foreground">
                  Активен
                  <Switch checked={t.active} onCheckedChange={(v) => setTypes(patch(types, i, { active: v }))} />
                </label>
              </div>
            ))}
          </div>
        </PricingSection>

        <OptionsEditor options={options} original={props.options} onChange={setOptions} />

        <PricingSection
          title="Параметры расчёта"
          description="Границы площади, надбавки и округление итоговой суммы."
          dirty={!same(params, props.params)}
          pending={param.pending}
          onSave={() => param.save(() => savePriceParamsAction(params.map(({ key, value }) => ({ key, value }))))}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            {params.map((p, i) => (
              <div key={p.key}>
                <p className="text-sm font-medium">{p.label}</p>
                <p className="mb-2 text-xs text-muted-foreground">{p.description}</p>
                <NumberCell label={p.label} value={p.value} suffix={p.unit} onChange={(v) => setParams(patch(params, i, { value: v }))} />
              </div>
            ))}
          </div>
        </PricingSection>
      </div>

      <FormulaPreview preview={preview} />
    </div>
  );
}
