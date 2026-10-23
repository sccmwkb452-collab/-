import type { HTMLAttributes } from "react";
import { cn } from "./cn";

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl3 bg-surface ring-1 ring-inset ring-line shadow-card", className)} {...rest} />;
}

export function SectionHeader({ title, subtitle, action, id }: { title: string; subtitle?: string; action?: React.ReactNode; id?: string }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-3 px-1" id={id}>
      <div>
        <h2 className="font-display text-[21px] font-semibold leading-tight tracking-[-0.025em] text-text">{title}</h2>
        {subtitle && <p className="mt-1 text-[13.5px] text-text-2">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
