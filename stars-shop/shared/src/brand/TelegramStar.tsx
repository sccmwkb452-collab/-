import { useId } from "react";

function starPoints(cx: number, cy: number, outer: number, inner: number): string {
  const pts: string[] = [];
  for (let i = 0; i < 10; i++) {
    const r = i % 2 === 0 ? outer : inner;
    const a = (-90 + i * 36) * (Math.PI / 180);
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return pts.join(" ");
}

const OUTER = starPoints(12, 12.6, 9.6, 4.7);
const INNER = starPoints(12, 11.4, 4.6, 2.3);

/**
 * Telegram Stars currency glyph: a rounded golden five-point star.
 * To use the official asset instead, render <img src="/brand/telegram-star.svg">
 * here — every place in the UI goes through this component.
 */
export function TelegramStar({ size = 20, className, title }: { size?: number; className?: string; title?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className={className}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <defs>
        <linearGradient id={`g${id}`} x1="0.2" y1="0" x2="0.8" y2="1">
          <stop offset="0" stopColor="#FFE07A" />
          <stop offset="0.55" stopColor="#FFB928" />
          <stop offset="1" stopColor="#F28C00" />
        </linearGradient>
      </defs>
      <polygon points={OUTER} fill={`url(#g${id})`} stroke={`url(#g${id})`} strokeWidth={2.4} strokeLinejoin="round" />
      <polygon points={INNER} fill="#FFF6CF" opacity={0.55} stroke="#FFF6CF" strokeOpacity={0.55} strokeWidth={1.2} strokeLinejoin="round" />
    </svg>
  );
}
