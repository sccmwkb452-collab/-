export function HouseIcon({ type, className }: { type: string; className?: string }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 120 80" className={className} aria-hidden>
      <line x1="4" y1="74" x2="116" y2="74" stroke="currentColor" strokeWidth="2" opacity="0.35" />
      {type === "one-story" && (
        <>
          <rect x="18" y="40" width="84" height="34" {...common} />
          <path d="M14 40h92" {...common} strokeWidth={4} />
          <rect x="28" y="50" width="30" height="24" {...common} opacity="0.6" />
          <rect x="70" y="50" width="20" height="14" {...common} opacity="0.6" />
        </>
      )}
      {type === "two-story" && (
        <>
          <rect x="30" y="14" width="60" height="60" {...common} />
          <path d="M26 14h68" {...common} strokeWidth={4} />
          <line x1="30" y1="44" x2="90" y2="44" {...common} opacity="0.35" />
          <rect x="40" y="22" width="18" height="14" {...common} opacity="0.6" />
          <rect x="64" y="22" width="18" height="14" {...common} opacity="0.6" />
          <rect x="40" y="52" width="24" height="22" {...common} opacity="0.6" />
        </>
      )}
      {type === "mansard" && (
        <>
          <path d="M26 74V42L60 10l34 32v32z" {...common} />
          <path d="M20 46L60 8l40 38" {...common} strokeWidth={4} />
          <rect x="50" y="28" width="20" height="14" {...common} opacity="0.6" />
          <rect x="36" y="52" width="26" height="22" {...common} opacity="0.6" />
          <rect x="70" y="54" width="14" height="12" {...common} opacity="0.6" />
        </>
      )}
    </svg>
  );
}
