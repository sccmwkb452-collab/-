import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap", {
  variants: {
    variant: {
      default: "bg-primary text-primary-foreground",
      outline: "border border-foreground/15 text-foreground",
      muted: "bg-secondary text-muted-foreground",
      accent: "bg-accent/12 text-accent",
      success: "bg-success/12 text-success",
      danger: "bg-destructive/10 text-destructive",
      glass: "bg-white/85 text-foreground backdrop-blur",
    },
  },
  defaultVariants: { variant: "default" },
});

function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
