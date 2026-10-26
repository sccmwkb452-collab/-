import { AlertTriangle, Ban, CheckCircle2, Circle, CircleDot, Info, Loader, XCircle } from "lucide-react";

import { Badge, type Tone } from "@/components/ui/badge";
import { info } from "@/lib/status";

const ICONS: Record<Tone, typeof Circle> = {
  neutral: Circle,
  info: Info,
  accent: Loader,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
};

/** Status always shows icon + text, never color alone. */
export function StatusBadge({
  map,
  value,
  label,
  className,
}: {
  map: Parameters<typeof info>[0];
  value: string | null | undefined;
  label?: string;
  className?: string;
}) {
  const s = info(map, value);
  const Icon = s.tone === "danger" && (value === "blocked" || value === "blocked_by_policy") ? Ban : ICONS[s.tone] ?? CircleDot;
  return (
    <Badge tone={s.tone} className={className}>
      <Icon aria-hidden />
      {label ?? s.label}
    </Badge>
  );
}

export function ToneBadge({ tone, children, className }: { tone: Tone; children: React.ReactNode; className?: string }) {
  const Icon = ICONS[tone];
  return (
    <Badge tone={tone} className={className}>
      <Icon aria-hidden />
      {children}
    </Badge>
  );
}
