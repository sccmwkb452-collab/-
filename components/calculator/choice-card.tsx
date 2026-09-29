"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChoiceCardProps {
  selected: boolean;
  onSelect: () => void;
  title: string;
  description?: string;
  aside?: React.ReactNode;
  visual?: React.ReactNode;
  children?: React.ReactNode;
  role?: "radio" | "checkbox";
  className?: string;
}

/** Большая карточка выбора для конфигуратора. Доступна с клавиатуры как radio/checkbox. */
export function ChoiceCard({ selected, onSelect, title, description, aside, visual, children, role = "radio", className }: ChoiceCardProps) {
  return (
    <button
      type="button"
      role={role}
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        "group relative flex w-full flex-col rounded-2xl border bg-white p-5 text-left transition-all duration-300 ease-[var(--ease-premium)] outline-none focus-visible:ring-3 focus-visible:ring-accent/40 sm:p-6 cursor-pointer",
        selected
          ? "border-primary shadow-[0_0_0_1px_var(--primary),0_12px_32px_-12px_rgba(0,0,0,0.25)]"
          : "border-border hover:-translate-y-0.5 hover:border-foreground/30 hover:shadow-[0_12px_32px_-16px_rgba(0,0,0,0.18)]",
        className,
      )}
    >
      <span
        className={cn(
          "absolute top-4 right-4 flex size-6 items-center justify-center border transition-all duration-300",
          role === "radio" ? "rounded-full" : "rounded-md",
          selected ? "border-primary bg-primary text-primary-foreground" : "border-foreground/20 bg-white",
        )}
        aria-hidden
      >
        <Check className={cn("size-3.5 transition-transform", selected ? "scale-100" : "scale-0")} strokeWidth={3} />
      </span>
      {visual && <span className={cn("mb-5 block transition-colors", selected ? "text-primary" : "text-foreground/45 group-hover:text-foreground/70")}>{visual}</span>}
      <span className="pr-8 text-lg font-semibold tracking-tight">{title}</span>
      {description && <span className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{description}</span>}
      {children}
      {aside && <span className="mt-auto pt-4 text-sm font-semibold tabular">{aside}</span>}
    </button>
  );
}
