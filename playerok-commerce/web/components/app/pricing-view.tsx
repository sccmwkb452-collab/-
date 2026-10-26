import { KV } from "@/components/app/blocks";
import { StatusBadge } from "@/components/app/status";
import { dt, money, pct } from "@/lib/format";
import { PRICING_STATUS } from "@/lib/status";
import type { Calculation } from "@/lib/types";

const COST_SOURCE: Record<string, string> = {
  supplier: "цена поставщика",
  manual: "себестоимость, введённая вручную",
  inventory: "средняя себестоимость кодов на складе",
  none: "нет данных о себестоимости",
};

export function CalculationView({ calc, currency, fxRate, costSource }: { calc: Calculation; currency?: string | null; fxRate?: string | null; costSource?: string }) {
  const b = calc.breakdown;
  const ev = calc.current ?? calc.recommended;
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge map={PRICING_STATUS} value={calc.status} />
        {costSource && <span className="text-xs text-muted-foreground">Себестоимость: {COST_SOURCE[costSource] ?? costSource}</span>}
        {fxRate && currency && currency !== "RUB" && (
          <span className="text-xs text-muted-foreground">
            · курс {currency} = {fxRate} ₽ (ЦБ РФ)
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["Минимальная", calc.min_price, "ниже — продажа в убыток или ниже порогов"],
          ["Целевая", calc.target_price, "даёт целевую маржу"],
          ["Рекомендуемая", calc.recommended_price, "с учётом рынка"],
          ["Конкурентная", calc.competitive_price, "ниже конкурента, но не ниже минимума"],
        ].map(([label, value, hint]) => (
          <div key={label} className="rounded-md border border-border bg-surface-2/40 px-3 py-2.5">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="mt-0.5 text-lg font-semibold tabular-nums">{money(value)}</p>
            <p className="text-[11px] text-subtle">{hint}</p>
          </div>
        ))}
      </div>
      {b && (
        <div className="grid gap-5 md:grid-cols-2">
          <div>
            <p className="mb-2 text-[13px] font-medium">Полная себестоимость</p>
            <KV
              items={[
                ["Закупка", money(b.purchase_rub)],
                ["Комиссия поставщика", money(b.supplier_fee_rub)],
                ["Конвертация валюты", money(b.conversion_rub)],
                ["Прочие расходы", money(b.other_costs_rub)],
                [<b key="t">Итого</b>, <b key="v">{money(b.full_cost)}</b>],
                ["Доля расходов от цены продажи", pct(b.sale_rate_pct)],
              ]}
            />
          </div>
          {ev && (
            <div>
              <p className="mb-2 text-[13px] font-medium">При цене {money(ev.price)}</p>
              <KV
                items={[
                  ["Комиссия PlayerOK", money(ev.marketplace_fee)],
                  ["Платёжная комиссия", money(ev.payment_fee)],
                  ["Резерв на возвраты", money(ev.refund_reserve)],
                  ["Комиссия вывода", money(ev.withdrawal_fee)],
                  [
                    <b key="p">Чистая прибыль</b>,
                    <b key="v" className={Number(ev.net_profit) < 0 ? "text-red-300" : "text-green-300"}>
                      {money(ev.net_profit)}
                    </b>,
                  ],
                  ["Маржа / ROI", `${pct(ev.margin_pct)} / ${pct(ev.roi_pct)}`],
                ]}
              />
              {ev.violations.length > 0 && (
                <ul className="mt-3 list-disc pl-5 text-[13px] text-red-300">
                  {ev.violations.map((v) => (
                    <li key={v}>{v}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
      {calc.notes.length > 0 && (
        <ul className="list-disc pl-5 text-[13px] text-muted-foreground">
          {calc.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

const FACTOR_LABELS: Record<string, string> = {
  demand: "Спрос",
  margin: "Маржинальность",
  turnover: "Оборачиваемость",
  competition: "Конкуренция",
  supplier_stability: "Стабильность цены поставщика",
  dispute_risk: "Риск споров и возвратов",
  supplier_reliability: "Надёжность поставщика",
  freshness: "Свежесть данных",
  auto_delivery: "Автовыдача",
};

type Factor = { score: number | null; value: unknown; basis: string; confidence: string; confidence_label?: string; at: string | null };

export function FactorList({ factors }: { factors: Record<string, unknown> }) {
  const entries = Object.entries(factors ?? {}).filter(([, v]) => v && typeof v === "object") as [string, Factor][];
  if (!entries.length) return null;
  return (
    <div className="flex flex-col gap-3">
      {entries.map(([key, f]) => (
        <div key={key}>
          <div className="flex items-center justify-between gap-3 text-[13px]">
            <span>{FACTOR_LABELS[key] ?? key}</span>
            <span className="tabular-nums text-muted-foreground">{f.score === null ? "нет данных" : `${Number(f.score).toFixed(0)} / 100`}</span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-3">
            {f.score !== null && <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(0, Math.min(100, Number(f.score)))}%` }} />}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {f.value !== null && f.value !== undefined ? `${String(f.value)} · ` : ""}
            {f.basis}
            {f.confidence_label ? ` · ${f.confidence_label}` : ""}
            {f.at ? ` · ${dt(f.at, false)}` : ""}
          </p>
        </div>
      ))}
    </div>
  );
}
