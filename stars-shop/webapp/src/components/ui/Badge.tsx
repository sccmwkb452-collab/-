import type { OrderStatus, StatusTone } from "@starshop/shared";
import { STATUS_META } from "@starshop/shared";
import { Check, CircleDashed, Clock3, Loader, RotateCcw, TriangleAlert, X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "./cn";

const tones: Record<StatusTone, string> = {
  neutral: "bg-text-3/12 text-text-2 ring-text-3/20",
  warning: "bg-warning/12 text-warning ring-warning/25",
  info: "bg-accent/14 text-[color-mix(in_oklab,var(--c-accent)_70%,var(--c-text))] ring-accent/30",
  success: "bg-success/12 text-success ring-success/25",
  danger: "bg-danger/12 text-danger ring-danger/25",
  violet: "bg-accent-2/14 text-[color-mix(in_oklab,var(--c-accent-2)_70%,var(--c-text))] ring-accent-2/30",
};

export function Badge({ tone = "neutral", children, className, icon }: { tone?: StatusTone; children: ReactNode; className?: string; icon?: ReactNode }) {
  return (
    <span className={cn("inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full px-2.5 text-[12px] font-semibold ring-1 ring-inset", tones[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

const statusIcons: Record<OrderStatus, ReactNode> = {
  created: <CircleDashed className="size-3.5" />,
  pending_payment: <Clock3 className="size-3.5" />,
  paid: <Check className="size-3.5" />,
  processing: <Loader className="size-3.5 animate-[spin_2.4s_linear_infinite]" />,
  completed: <Check className="size-3.5" />,
  failed: <TriangleAlert className="size-3.5" />,
  refund_pending: <RotateCcw className="size-3.5" />,
  refunded: <RotateCcw className="size-3.5" />,
  cancelled: <X className="size-3.5" />,
};

export function StatusBadge({ status, className }: { status: OrderStatus; className?: string }) {
  const meta = STATUS_META[status];
  return (
    <Badge tone={meta.tone} icon={statusIcons[status]} className={className}>
      {meta.label}
    </Badge>
  );
}

export function DemoBadge({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex h-5 items-center rounded-md bg-warning/15 px-1.5 font-display text-[10px] font-bold uppercase tracking-[0.08em] text-warning ring-1 ring-inset ring-warning/30", className)}>
      Demo
    </span>
  );
}
