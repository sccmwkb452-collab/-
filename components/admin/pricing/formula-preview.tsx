import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { EstimateResult } from "@/lib/pricing/types";
import { formatPrice } from "@/lib/utils";

export function FormulaPreview({ preview }: { preview: { label: string; result: EstimateResult } | null }) {
  return (
    <aside className="xl:sticky xl:top-6 xl:self-start">
      <Card className="border-transparent bg-primary text-primary-foreground">
        <CardHeader>
          <CardTitle>Проверка формулы</CardTitle>
          <p className="text-sm text-white/55">Пример расчёта с текущими, в том числе несохранёнными, значениями.</p>
        </CardHeader>
        <CardContent>
          {preview ? (
            <>
              <p className="text-sm text-white/70">{preview.label}</p>
              <p className="mt-4 text-3xl font-semibold tracking-tight tabular">{formatPrice(preview.result.total)}</p>
              <dl className="mt-4 space-y-1.5 border-t border-white/10 pt-4 text-sm">
                {(
                  [
                    ["База (площадь × цена м²)", preview.result.base],
                    ["Этажность", preview.result.houseTypeAdjustment],
                    ["Комплектация", preview.result.packageAdjustment],
                    ["Доп. спальни", preview.result.bedroomsAdjustment],
                    ["Опции", preview.result.optionsTotal],
                  ] as const
                ).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3">
                    <dt className="text-white/55">{k}</dt>
                    <dd className="tabular">{v < 0 ? "−" : ""}{formatPrice(Math.abs(v))}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-4 text-xs text-white/40">
                Итог = база + этажность + комплектация + спальни + опции, с округлением.
              </p>
            </>
          ) : (
            <p className="text-sm text-white/60">Недостаточно данных для примера.</p>
          )}
        </CardContent>
      </Card>
    </aside>
  );
}
