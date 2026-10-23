import { TelegramStar } from "@starshop/shared";

// Deterministic "random" particles so the composition is stable.
const PARTICLES = Array.from({ length: 22 }, (_, i) => {
  const r = (n: number) => ((Math.sin(i * 12.9898 + n * 78.233) * 43758.5453) % 1 + 1) % 1;
  return { x: r(1) * 100, y: r(2) * 100, size: 1.5 + r(3) * 2.5, delay: r(4) * 4, dur: 2.5 + r(5) * 3 };
});

export function HeroVisual() {
  return (
    <div className="relative mx-auto h-[210px] w-full max-w-[360px]" aria-hidden>
      {/* glows */}
      <div className="absolute left-1/2 top-1/2 size-[220px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(255,185,40,0.35)_0%,transparent_62%)] blur-md" />
      <div className="absolute left-[18%] top-[30%] size-[140px] rounded-full bg-accent/30 blur-3xl" />
      <div className="absolute right-[12%] top-[18%] size-[120px] rounded-full bg-accent-2/30 blur-3xl" />

      {/* orbits */}
      <svg viewBox="0 0 360 210" className="absolute inset-0 h-full w-full">
        <defs>
          <linearGradient id="orbit" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="var(--c-accent)" stopOpacity="0" />
            <stop offset="0.5" stopColor="var(--c-accent-3)" stopOpacity="0.7" />
            <stop offset="1" stopColor="var(--c-accent-2)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <ellipse cx="180" cy="108" rx="150" ry="44" fill="none" stroke="url(#orbit)" strokeWidth="1.2" transform="rotate(-12 180 108)" />
        <ellipse cx="180" cy="108" rx="118" ry="70" fill="none" stroke="url(#orbit)" strokeWidth="1" opacity="0.6" transform="rotate(18 180 108)" />
      </svg>
      <div className="absolute inset-0 animate-[spin_26s_linear_infinite]">
        <span className="absolute left-[8%] top-1/2 size-2 rounded-full bg-accent-3 shadow-[0_0_12px_4px_var(--c-accent-3)]" />
      </div>
      <div className="absolute inset-[12%] animate-[spin_18s_linear_infinite_reverse]">
        <span className="absolute right-[6%] top-[30%] size-1.5 rounded-full bg-white shadow-[0_0_10px_3px_rgba(255,255,255,0.8)]" />
      </div>

      {/* particles */}
      {PARTICLES.map((p, i) => (
        <span
          key={i}
          className="absolute rounded-full bg-white animate-[twinkle_3s_ease-in-out_infinite]"
          style={{ left: `${p.x}%`, top: `${p.y}%`, width: p.size, height: p.size, animationDelay: `${p.delay}s`, animationDuration: `${p.dur}s` }}
        />
      ))}

      {/* stars */}
      <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        <span className="block animate-[float_6s_ease-in-out_infinite]">
          <TelegramStar size={118} className="drop-shadow-[0_18px_40px_rgba(255,160,0,0.55)]" />
        </span>
      </span>
      <span className="absolute left-[16%] top-[18%] animate-[float_5s_ease-in-out_infinite] [animation-delay:0.8s]">
        <TelegramStar size={34} className="opacity-90" />
      </span>
      <span className="absolute right-[14%] top-[58%] animate-[float_5.5s_ease-in-out_infinite] [animation-delay:1.4s]">
        <TelegramStar size={42} />
      </span>
      <span className="absolute right-[26%] top-[8%] animate-[float_4.5s_ease-in-out_infinite] [animation-delay:2s]">
        <TelegramStar size={20} className="opacity-80" />
      </span>
      <span className="absolute left-[26%] bottom-[6%] animate-[float_5s_ease-in-out_infinite] [animation-delay:2.6s]">
        <TelegramStar size={16} className="opacity-70" />
      </span>
    </div>
  );
}
