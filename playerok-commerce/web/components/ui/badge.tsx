import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/format";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium [&_svg]:size-3.5 [&_svg]:shrink-0",
  {
    variants: {
      tone: {
        neutral: "border-border-strong bg-surface-2 text-muted-foreground",
        info: "border-primary/30 bg-primary/10 text-blue-300",
        accent: "border-highlight/30 bg-highlight/10 text-sky-300",
        success: "border-success/30 bg-success/10 text-green-300",
        warning: "border-warning/30 bg-warning/10 text-yellow-300",
        danger: "border-danger/35 bg-danger/10 text-red-300",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export type Tone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

export function Badge({ className, tone, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
