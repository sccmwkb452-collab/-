import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { haptic } from "../../lib/telegram";
import { cn } from "./cn";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "gold" | "lucky";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary:
    "bg-accent-gradient text-on-accent shadow-glow hover:brightness-110 active:brightness-95 disabled:shadow-none",
  secondary: "bg-surface-2 text-text ring-1 ring-inset ring-line hover:bg-surface-3",
  ghost: "bg-transparent text-text-2 hover:text-text hover:bg-surface-2",
  danger: "bg-danger/12 text-danger ring-1 ring-inset ring-danger/25 hover:bg-danger/18",
  gold: "bg-gradient-to-br from-[#FFE07A] via-[#FFB928] to-[#F28C00] text-[#2b1600] shadow-[0_10px_30px_-12px_rgba(255,170,0,0.7)] hover:brightness-105",
  // Lucky Buy: the blue/cyan of its promo banner.
  lucky:
    "bg-[linear-gradient(180deg,#2D8DFF_0%,#0866FF_60%,#0657DE_100%)] text-white ring-1 ring-inset ring-[#9FD8FF]/45 shadow-[0_10px_30px_-10px_rgba(8,102,255,0.9),0_0_18px_-6px_rgba(0,207,255,0.6)] hover:brightness-110 disabled:shadow-none",
};

const sizes: Record<Size, string> = {
  sm: "h-9 px-3.5 text-[13px] rounded-xl gap-1.5",
  md: "h-11 px-4.5 text-[15px] rounded-2xl gap-2",
  lg: "h-14 px-6 text-[16px] rounded-[18px] gap-2.5",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
  iconRight?: ReactNode;
  block?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, iconRight, block, className, children, disabled, onClick, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      onClick={(e) => {
        haptic.tap(variant === "primary" || variant === "gold" || variant === "lucky" ? "medium" : "light");
        onClick?.(e);
      }}
      className={cn(
        "relative inline-flex select-none items-center justify-center font-semibold tracking-[-0.01em] transition-[transform,filter,background-color,box-shadow,opacity] duration-200 ease-out-soft",
        "active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100",
        variants[variant],
        sizes[size],
        block && "w-full",
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner className="size-4.5" /> : icon}
      <span className={cn(loading && "opacity-90")}>{children}</span>
      {!loading && iconRight}
    </button>
  );
});

export function IconButton({ label, className, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      aria-label={label}
      title={label}
      onClick={(e) => {
        haptic.tap();
        rest.onClick?.(e);
      }}
      className={cn(
        "inline-flex size-10 items-center justify-center rounded-2xl bg-surface-2 text-text-2 ring-1 ring-inset ring-line transition hover:text-text active:scale-95",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
