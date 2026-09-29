import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-semibold transition-all duration-300 ease-[var(--ease-premium)] outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 cursor-pointer",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/88 active:scale-[0.98]",
        accent: "bg-accent text-accent-foreground hover:brightness-110 active:scale-[0.98]",
        outline: "border border-foreground/15 bg-transparent hover:border-foreground/40 hover:bg-foreground/[0.03]",
        light: "bg-white/95 text-foreground hover:bg-white backdrop-blur",
        ghost: "hover:bg-foreground/5",
        link: "rounded-none px-0 text-foreground underline-offset-4 hover:underline",
        destructive: "bg-destructive text-white hover:bg-destructive/90",
        secondary: "bg-secondary text-secondary-foreground hover:bg-sand/60",
      },
      size: {
        default: "h-11 px-6",
        sm: "h-9 px-4 text-[13px]",
        lg: "h-13 px-8 text-[15px]",
        xl: "h-14 px-9 text-base",
        icon: "size-10",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "button";
  return <Comp data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}

export { Button, buttonVariants };
