"use client";

import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { deleteOptionAction, saveOptionAction } from "@/lib/actions/pricing";
import { slugify } from "@/lib/utils";
import { NumberCell, TextCell } from "./section";

export interface OptionRow {
  id?: string;
  code: string;
  name: string;
  description: string;
  pricingType: "FIXED" | "PER_M2";
  price: number;
  active: boolean;
  sortOrder: number;
}

interface Props {
  options: OptionRow[];
  original: OptionRow[];
  onChange: (next: OptionRow[]) => void;
}

export function OptionsEditor({ options, original, onChange }: Props) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const patch = (i: number, p: Partial<OptionRow>) => onChange(options.map((o, idx) => (idx === i ? { ...o, ...p } : o)));

  const save = (i: number) =>
    start(async () => {
      const row = options[i];
      const res = await saveOptionAction({ ...row, code: row.code || slugify(row.name) });
      if (res.ok) {
        toast.success(res.message ?? "Сохранено");
        router.refresh();
      } else toast.error(res.error);
    });

  const remove = (i: number) => {
    const row = options[i];
    if (!row.id) {
      onChange(options.filter((_, idx) => idx !== i));
      return;
    }
    if (!window.confirm(`Удалить опцию «${row.name}»?`)) return;
    const id = row.id;
    start(async () => {
      const res = await deleteOptionAction(id);
      if (res.ok) {
        toast.success(res.message ?? "Удалено");
        onChange(options.filter((_, idx) => idx !== i));
        router.refresh();
      } else toast.error(res.error);
    });
  };

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-4">
        <div>
          <CardTitle>Дополнительные опции</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">Фиксированная цена или цена за м² площади дома. Каждая опция сохраняется отдельно.</p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => onChange([...options, { code: "", name: "", description: "", pricingType: "FIXED", price: 0, active: true, sortOrder: options.length + 1 }])}
        >
          <Plus />
          Добавить опцию
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {options.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">Опций пока нет.</p>}
        {options.map((o, i) => {
          const before = o.id ? original.find((x) => x.id === o.id) : null;
          const dirty = !before || JSON.stringify(before) !== JSON.stringify(o);
          return (
            <div key={o.id ?? `new-${i}`} className="space-y-2 rounded-xl border border-border p-3">
              <div className="grid gap-2 sm:grid-cols-[1fr_12rem]">
                <TextCell label="Название" value={o.name} onChange={(v) => patch(i, { name: v })} />
                <TextCell label="Код (латиница)" value={o.code} onChange={(v) => patch(i, { code: v })} />
              </div>
              <TextCell label="Описание" value={o.description} onChange={(v) => patch(i, { description: v })} />
              <div className="flex flex-wrap items-center gap-2">
                <Select value={o.pricingType} onValueChange={(v) => patch(i, { pricingType: v as OptionRow["pricingType"] })}>
                  <SelectTrigger className="h-10 w-32 text-sm" aria-label="Тип цены"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="FIXED">Фиксированная</SelectItem>
                    <SelectItem value="PER_M2">За м²</SelectItem>
                  </SelectContent>
                </Select>
                <div className="w-40">
                  <NumberCell label={`Цена, ${o.name || "новая опция"}`} value={o.price} step={1000} suffix={o.pricingType === "PER_M2" ? "₽/м²" : "₽"} onChange={(v) => patch(i, { price: v })} />
                </div>
                <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Switch checked={o.active} onCheckedChange={(v) => patch(i, { active: v })} />
                  Активна
                </label>
                <div className="ml-auto flex gap-1">
                  <Button size="sm" disabled={!dirty || pending} onClick={() => save(i)}>Сохранить</Button>
                  <Button size="icon-sm" variant="ghost" className="text-destructive hover:bg-destructive/10" aria-label="Удалить опцию" disabled={pending} onClick={() => remove(i)}>
                    <Trash2 />
                  </Button>
                </div>
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
