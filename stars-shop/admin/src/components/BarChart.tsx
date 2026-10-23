import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "./ui";

export interface BarDatum {
  key: string;
  label: string; // axis label
  tooltip: string; // full label in the tooltip / table
  value: number;
}

function niceMax(max: number): number {
  if (max <= 0) return 1;
  const exp = 10 ** Math.floor(Math.log10(max));
  const f = max / exp;
  const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
  return nice * exp;
}

export function compact(value: number): string {
  return new Intl.NumberFormat("ru-RU", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

/**
 * Single-series column chart (no legend: the card title names the series).
 * Columns <= 24px with a 4px rounded data-end, hairline grid, one tooltip per
 * column (hover and keyboard focus), selective label on the maximum, and a
 * table view so no value depends on hovering.
 */
export function BarChart({ data, format, height = 220, dimmed, title, integer, emptyText = "За выбранный период данных нет" }: { data: BarDatum[]; format: (v: number) => string; height?: number; dimmed?: boolean; title: string; integer?: boolean; emptyText?: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [active, setActive] = useState<number | null>(null);
  const [table, setTable] = useState(false);

  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, e.contentRect.width)));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const pad = { top: 22, right: 8, bottom: 26, left: 44 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const max = useMemo(() => {
    const m = niceMax(Math.max(0, ...data.map((d) => d.value)));
    // Counts get whole-number ticks (max divisible by 4 quarter steps).
    return integer ? Math.max(4, Math.ceil(m / 4) * 4) : m;
  }, [data, integer]);
  const empty = data.every((d) => d.value === 0);
  const ticks = [0, max / 4, max / 2, (max * 3) / 4, max];
  const slot = innerW / Math.max(1, data.length);
  const barW = Math.max(2, Math.min(24, slot - 2));
  const maxIndex = data.reduce((best, d, i) => (d.value > (data[best]?.value ?? -1) ? i : best), 0);
  const labelEvery = Math.ceil(data.length / Math.max(1, Math.floor(innerW / 54)));
  const y = (v: number) => pad.top + innerH - (v / max) * innerH;

  return (
    <div>
      <div className="mb-2 flex justify-end">
        <button onClick={() => setTable((t) => !t)} className="text-[12px] font-semibold text-text-3 hover:text-text" aria-pressed={table}>
          {table ? "График" : "Таблица"}
        </button>
      </div>
      {table ? (
        <div className="max-h-[260px] overflow-y-auto rounded-xl ring-1 ring-line">
          <table className="data w-full">
            <thead>
              <tr>
                <th>Период</th>
                <th className="text-right">{title}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.key}>
                  <td>{d.tooltip}</td>
                  <td className="text-right tabular">{format(d.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={box} className={cn("relative transition-opacity", dimmed && "opacity-50")}>
          {empty && (
            <div className="pointer-events-none absolute inset-x-0 top-[38%] z-10 text-center text-[13px] text-text-3">{emptyText}</div>
          )}
          <svg width={width} height={height} role="img" aria-label={title} className="block">
            {ticks.map((t) => (
              <g key={t}>
                <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke="var(--c-line)" strokeWidth={1} shapeRendering="crispEdges" />
                <text x={pad.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-text-3 text-[11px] tabular">
                  {compact(t)}
                </text>
              </g>
            ))}
            {data.map((d, i) => {
              const x = pad.left + i * slot + (slot - barW) / 2;
              const top = y(d.value);
              const h = pad.top + innerH - top;
              const r = Math.min(4, h, barW / 2);
              const path = h > 0 ? `M${x},${pad.top + innerH} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${pad.top + innerH} Z` : "";
              const isActive = active === i;
              return (
                <g key={d.key}>
                  {path && <path d={path} fill="var(--c-accent)" opacity={active === null || isActive ? 1 : 0.55} />}
                  {i === maxIndex && d.value > 0 && (
                    <text x={x + barW / 2} y={top - 6} textAnchor="middle" className="fill-text-2 text-[11px] font-semibold tabular">
                      {compact(d.value)}
                    </text>
                  )}
                  {i % labelEvery === 0 && (
                    <text x={x + barW / 2} y={height - 8} textAnchor="middle" className="fill-text-3 text-[11px] tabular">
                      {d.label}
                    </text>
                  )}
                  {/* hit target: the whole slot, larger than the mark */}
                  <rect
                    x={pad.left + i * slot}
                    y={pad.top}
                    width={slot}
                    height={innerH}
                    fill="transparent"
                    tabIndex={0}
                    aria-label={`${d.tooltip}: ${format(d.value)}`}
                    onPointerEnter={() => setActive(i)}
                    onPointerLeave={() => setActive(null)}
                    onFocus={() => setActive(i)}
                    onBlur={() => setActive(null)}
                    className="outline-none"
                  />
                </g>
              );
            })}
          </svg>
          {active !== null && data[active] && (
            <div
              className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-xl bg-surface-3 px-3 py-2 shadow-2xl ring-1 ring-line"
              style={{ left: Math.min(width - 70, Math.max(70, pad.left + active * slot + slot / 2)), top: Math.max(30, y(data[active].value) - 8) }}
            >
              <div className="text-[14px] font-bold tabular text-text">{format(data[active].value)}</div>
              <div className="text-[11.5px] text-text-3">{data[active].tooltip}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
