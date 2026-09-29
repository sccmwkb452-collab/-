"use client";

import { Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface SectionProps {
  title: string;
  description: string;
  dirty: boolean;
  pending: boolean;
  onSave: () => void;
  children: React.ReactNode;
}

export function PricingSection({ title, description, dirty, pending, onSave, children }: SectionProps) {
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-4">
        <div>
          <CardTitle>{title}</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        </div>
        <Button onClick={onSave} disabled={!dirty || pending} size="sm">
          {pending ? <Loader2 className="animate-spin" /> : <Save />}
          Сохранить
        </Button>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

interface NumberCellProps {
  value: number;
  onChange: (v: number) => void;
  step?: number;
  suffix?: string;
  label: string;
  min?: number;
}

export function NumberCell({ value, onChange, step = 1, suffix, label, min = 0 }: NumberCellProps) {
  return (
    <span className="relative block">
      <input
        type="number"
        inputMode="decimal"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        step={step}
        aria-label={label}
        onChange={(e) => onChange(e.target.value === "" ? Number.NaN : Number(e.target.value))}
        className="h-10 w-full rounded-lg border border-input bg-white px-3 pr-12 text-sm font-medium tabular outline-none focus-visible:border-accent focus-visible:ring-3 focus-visible:ring-accent/15"
      />
      {suffix && <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs text-muted-foreground">{suffix}</span>}
    </span>
  );
}

export function TextCell({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <input
      value={value}
      aria-label={label}
      placeholder={label}
      onChange={(e) => onChange(e.target.value)}
      className="h-10 w-full rounded-lg border border-input bg-white px-3 text-sm outline-none focus-visible:border-accent focus-visible:ring-3 focus-visible:ring-accent/15"
    />
  );
}
