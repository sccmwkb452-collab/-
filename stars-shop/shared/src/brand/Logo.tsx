import { useId } from "react";

/** Pulsar mark: a four-point spark on an orbit with a travelling pulse. */
export function LogoMark({ size = 32, className }: { size?: number; className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" className={className} aria-hidden>
      <defs>
        <linearGradient id={`bg${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--c-accent, #2F6BFF)" />
          <stop offset="1" stopColor="var(--c-accent-2, #1D8CFF)" />
        </linearGradient>
        <radialGradient id={`hl${id}`} cx="0.25" cy="0.15" r="0.8">
          <stop offset="0" stopColor="#fff" stopOpacity="0.45" />
          <stop offset="0.6" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect x="0" y="0" width="40" height="40" rx="12" fill={`url(#bg${id})`} />
      <rect x="0" y="0" width="40" height="40" rx="12" fill={`url(#hl${id})`} />
      <path d="M8.5 25.5a13 13 0 0 1 21.6-12.9" fill="none" stroke="#fff" strokeOpacity="0.38" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M31.5 14.5a13 13 0 0 1-21.6 12.9" fill="none" stroke="#fff" strokeOpacity="0.16" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="30.1" cy="12.6" r="2.2" fill="var(--c-accent-3, #22D3EE)" stroke="#fff" strokeWidth="1" />
      <path d="M20 9.5c.9 6.1 4.4 9.6 10.5 10.5-6.1.9-9.6 4.4-10.5 10.5-.9-6.1-4.4-9.6-10.5-10.5 6.1-.9 9.6-4.4 10.5-10.5Z" fill="#fff" />
    </svg>
  );
}

export function Logo({ name, logoUrl, size = 32, className }: { name: string; logoUrl?: string | null; size?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className ?? ""}`}>
      {logoUrl ? (
        <img src={logoUrl} alt="" width={size} height={size} className="rounded-xl object-cover" style={{ width: size, height: size }} />
      ) : (
        <LogoMark size={size} />
      )}
      <span className="truncate font-display text-[17px] font-semibold tracking-[-0.02em] text-text">{name}</span>
    </span>
  );
}
