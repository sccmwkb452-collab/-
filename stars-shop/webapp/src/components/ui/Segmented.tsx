import { motion } from "motion/react";
import { useId } from "react";
import { haptic } from "../../lib/telegram";
import { cn } from "./cn";

export function Segmented<T extends string>({ value, options, onChange, scrollable, label }: { value: T; options: readonly { id: T; label: string }[]; onChange: (v: T) => void; scrollable?: boolean; label: string }) {
  const layoutId = useId();
  return (
    <div role="tablist" aria-label={label} className={cn("flex gap-1 rounded-2xl bg-surface-2 p-1 ring-1 ring-inset ring-line", scrollable && "no-scrollbar overflow-x-auto")}>
      {options.map((o) => {
        const active = o.id === value;
        return (
          <button
            key={o.id}
            role="tab"
            aria-selected={active}
            onClick={() => {
              haptic.select();
              onChange(o.id);
            }}
            className={cn(
              "relative flex-1 whitespace-nowrap rounded-xl px-3.5 py-2 text-[13.5px] font-semibold transition-colors",
              active ? "text-text" : "text-text-3 hover:text-text-2",
            )}
          >
            {active && <motion.span layoutId={layoutId} className="absolute inset-0 rounded-xl bg-surface shadow-card ring-1 ring-line" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
            <span className="relative">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}
