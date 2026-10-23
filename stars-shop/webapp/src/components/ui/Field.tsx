import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";
import { cn } from "./cn";

export const Field = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: ReactNode; error?: string | null; leading?: ReactNode; suffix?: ReactNode }>(
  function Field({ label, hint, error, leading, suffix, className, id, ...rest }, ref) {
    const inputId = id ?? rest.name;
    return (
      <label className="block" htmlFor={inputId}>
        {label && <span className="mb-2 block px-1 text-[13px] font-semibold text-text-2">{label}</span>}
        <span
          className={cn(
            "flex h-14 items-center gap-2 rounded-[18px] bg-surface-2 px-4 ring-1 ring-inset transition focus-within:ring-2",
            error ? "ring-danger/60 focus-within:ring-danger" : "ring-line focus-within:ring-accent",
          )}
        >
          {leading && <span className="text-[16px] font-semibold text-text-3">{leading}</span>}
          <input
            ref={ref}
            id={inputId}
            aria-invalid={error ? true : undefined}
            className={cn("h-full min-w-0 flex-1 bg-transparent text-[16px] font-medium text-text outline-none placeholder:text-text-3", className)}
            {...rest}
          />
          {suffix}
        </span>
        {(error || hint) && <span className={cn("mt-2 block px-1 text-[12.5px] leading-snug", error ? "text-danger" : "text-text-3")}>{error || hint}</span>}
      </label>
    );
  },
);
