"use client";

import * as React from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { money, num } from "@/lib/format";

/* Palette validated (dataviz validator, dark mode) on the panel surface #0f1626:
   slot 1 revenue, slot 3 net profit; orders go on their own chart — never a dual axis. */
export const SERIES = { revenue: "#3987e5", profit: "#199e70", orders: "#3987e5" } as const;

const AXIS = { stroke: "transparent", tick: { fill: "#8b97ad", fontSize: 12 }, tickLine: false, axisLine: false } as const;
const GRID = "rgb(148 163 194 / 0.10)";

function shortDay(value: string) {
  const [, m, d] = value.split("-");
  return `${d}.${m}`;
}

function compactRub(value: number) {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} млн`;
  if (Math.abs(value) >= 1000) return `${(value / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} тыс`;
  return value.toLocaleString("ru-RU");
}

type TooltipRow = { name: string; color: string; value: string };

function ChartTooltip({ title, rows }: { title: string; rows: TooltipRow[] }) {
  return (
    <div className="min-w-44 rounded-lg border border-border-strong bg-[#131c30]/95 px-3 py-2 text-xs shadow-xl backdrop-blur">
      <p className="mb-1.5 font-medium text-foreground">{title}</p>
      {rows.map((r) => (
        <div key={r.name} className="flex items-center justify-between gap-4 py-0.5">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className="size-2 rounded-sm" style={{ background: r.color }} />
            {r.name}
          </span>
          <span className="font-medium text-foreground tabular-nums">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded-full" style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

export type MoneyPoint = { day: string; revenue: string; net_profit: string; orders: number };

export function MoneyChart({ data, height = 260 }: { data: MoneyPoint[]; height?: number }) {
  const rows = data.map((d) => ({ day: d.day, revenue: Number(d.revenue), profit: Number(d.net_profit) }));
  return (
    <div>
      <Legend
        items={[
          { label: "Выручка", color: SERIES.revenue },
          { label: "Чистая прибыль", color: SERIES.profit },
        ]}
      />
      <div style={{ height }} className="mt-3">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="fill-revenue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={SERIES.revenue} stopOpacity={0.22} />
                <stop offset="100%" stopColor={SERIES.revenue} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="day" tickFormatter={shortDay} {...AXIS} minTickGap={24} />
            <YAxis tickFormatter={compactRub} width={64} {...AXIS} />
            <Tooltip
              cursor={{ stroke: "rgb(148 163 194 / 0.35)", strokeWidth: 1 }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <ChartTooltip
                    title={shortDay(String(label))}
                    rows={[
                      { name: "Выручка", color: SERIES.revenue, value: money(payload.find((p) => p.dataKey === "revenue")?.value as number) },
                      { name: "Чистая прибыль", color: SERIES.profit, value: money(payload.find((p) => p.dataKey === "profit")?.value as number) },
                    ]}
                  />
                ) : null
              }
            />
            <Area
              type="monotone"
              dataKey="revenue"
              name="Выручка"
              stroke={SERIES.revenue}
              strokeWidth={2}
              fill="url(#fill-revenue)"
              dot={false}
              activeDot={{ r: 4, stroke: "#0f1626", strokeWidth: 2 }}
            />
            <Area
              type="monotone"
              dataKey="profit"
              name="Чистая прибыль"
              stroke={SERIES.profit}
              strokeWidth={2}
              fill="transparent"
              dot={false}
              activeDot={{ r: 4, stroke: "#0f1626", strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function OrdersChart({ data, height = 180 }: { data: MoneyPoint[]; height?: number }) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }} barCategoryGap="28%">
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="day" tickFormatter={shortDay} {...AXIS} minTickGap={24} />
          <YAxis allowDecimals={false} width={40} {...AXIS} />
          <Tooltip
            cursor={{ fill: "rgb(148 163 194 / 0.06)" }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <ChartTooltip title={shortDay(String(label))} rows={[{ name: "Заказы", color: SERIES.orders, value: num(payload[0].value as number) }]} />
              ) : null
            }
          />
          <Bar dataKey="orders" name="Заказы" fill={SERIES.orders} radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PriceChart({
  points,
  height = 200,
}: {
  points: { at: string; purchase?: number | null; sale?: number | null }[];
  height?: number;
}) {
  const rows = points.map((p) => ({ ...p, label: new Date(p.at).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" }) }));
  return (
    <div>
      <Legend
        items={[
          { label: "Закупка, ₽", color: "#d95926" },
          { label: "Цена продажи, ₽", color: SERIES.revenue },
        ]}
      />
      <div style={{ height }} className="mt-3">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="label" {...AXIS} minTickGap={24} />
            <YAxis tickFormatter={compactRub} width={56} {...AXIS} />
            <Tooltip
              cursor={{ stroke: "rgb(148 163 194 / 0.35)", strokeWidth: 1 }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <ChartTooltip
                    title={String(label)}
                    rows={payload
                      .filter((p) => p.value !== null && p.value !== undefined)
                      .map((p) => ({
                        name: p.dataKey === "purchase" ? "Закупка" : "Продажа",
                        color: p.dataKey === "purchase" ? "#d95926" : SERIES.revenue,
                        value: money(p.value as number),
                      }))}
                  />
                ) : null
              }
            />
            <Area type="stepAfter" dataKey="purchase" stroke="#d95926" strokeWidth={2} fill="transparent" connectNulls dot={false} />
            <Area type="stepAfter" dataKey="sale" stroke={SERIES.revenue} strokeWidth={2} fill="transparent" connectNulls dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
