import type { LeadStatus } from "@prisma/client";
import { LEAD_STATUS_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";

const STYLES: Record<LeadStatus, string> = {
  NEW: "bg-accent text-white",
  IN_PROGRESS: "bg-[#E8E1D3] text-[#5D4A2E]",
  CONTACTED: "bg-[#DDE6EE] text-[#2E4A5D]",
  CALCULATION: "bg-[#E6E0EE] text-[#4A3A5D]",
  CONTRACT: "bg-[#DCEBDF] text-[#2F5A38]",
  COMPLETED: "bg-primary text-primary-foreground",
  REJECTED: "bg-secondary text-muted-foreground line-through decoration-1",
};

export function LeadStatusBadge({ status, className }: { status: LeadStatus; className?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap", STYLES[status], className)}>
      {LEAD_STATUS_LABELS[status]}
    </span>
  );
}
