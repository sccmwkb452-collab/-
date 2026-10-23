import { TelegramStar } from "@starshop/shared";
import { cn } from "../ui/cn";

type Spot = { x: number; y: number; s: number; d: number };

// Hand-placed compositions (percent of the box), main star first.
const LAYOUTS: Spot[][] = [
  [{ x: 50, y: 52, s: 54, d: 0 }],
  [{ x: 44, y: 54, s: 50, d: 0 }, { x: 70, y: 34, s: 28, d: 0.6 }],
  [{ x: 48, y: 56, s: 50, d: 0 }, { x: 74, y: 36, s: 28, d: 0.5 }, { x: 24, y: 32, s: 22, d: 1.1 }],
  [{ x: 50, y: 56, s: 54, d: 0 }, { x: 78, y: 40, s: 26, d: 0.4 }, { x: 22, y: 38, s: 26, d: 0.9 }, { x: 62, y: 18, s: 16, d: 1.4 }],
  [{ x: 50, y: 58, s: 54, d: 0 }, { x: 80, y: 44, s: 28, d: 0.3 }, { x: 20, y: 44, s: 28, d: 0.8 }, { x: 34, y: 18, s: 18, d: 1.2 }, { x: 68, y: 16, s: 18, d: 1.6 }],
  [{ x: 50, y: 58, s: 58, d: 0 }, { x: 82, y: 48, s: 30, d: 0.3 }, { x: 18, y: 48, s: 30, d: 0.7 }, { x: 30, y: 18, s: 20, d: 1.1 }, { x: 70, y: 16, s: 22, d: 1.5 }, { x: 50, y: 12, s: 14, d: 1.9 }],
  [{ x: 50, y: 58, s: 62, d: 0 }, { x: 84, y: 50, s: 30, d: 0.2 }, { x: 16, y: 50, s: 30, d: 0.6 }, { x: 28, y: 18, s: 22, d: 1 }, { x: 72, y: 16, s: 24, d: 1.4 }, { x: 50, y: 10, s: 16, d: 1.8 }, { x: 88, y: 20, s: 12, d: 2.2 }],
];

const GLOWS = [
  "var(--c-accent)",
  "var(--c-accent)",
  "var(--c-accent-2)",
  "var(--c-accent-2)",
  "var(--c-accent-3)",
  "#ffb928",
  "#ffb928",
];

export function tierFor(stars: number): number {
  if (stars < 100) return 0;
  if (stars < 250) return 1;
  if (stars < 500) return 2;
  if (stars < 1000) return 3;
  if (stars < 2500) return 4;
  if (stars < 5000) return 5;
  return 6;
}

export function StarArt({ stars, className }: { stars: number; className?: string }) {
  const tier = tierFor(stars);
  const glow = GLOWS[tier];
  return (
    <div className={cn("relative h-[104px] w-full overflow-hidden rounded-[20px]", className)} aria-hidden>
      <div
        className="absolute inset-0 transition-opacity duration-500 group-hover:opacity-100"
        style={{
          background: `radial-gradient(60% 70% at 50% 62%, color-mix(in oklab, ${glow} 38%, transparent) 0%, transparent 70%), linear-gradient(180deg, color-mix(in oklab, ${glow} 10%, var(--c-surface-2)) 0%, var(--c-surface-2) 100%)`,
          opacity: 0.85,
        }}
      />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,rgba(255,255,255,0.08)_1px,transparent_0)] [background-size:14px_14px] opacity-40" />
      {LAYOUTS[tier].map((spot, i) => (
        <span
          key={i}
          className="absolute animate-[float_5s_ease-in-out_infinite]"
          style={{ left: `${spot.x}%`, top: `${spot.y}%`, animationDelay: `${spot.d}s`, translate: "-50% -50%" }}
        >
          <TelegramStar size={spot.s} className={cn(i === 0 && "drop-shadow-[0_6px_18px_rgba(255,170,0,0.45)]")} />
        </span>
      ))}
    </div>
  );
}
