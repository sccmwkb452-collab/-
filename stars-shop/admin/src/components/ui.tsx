import type { OrderStatus, StatusTone } from "@starshop/shared";
import { STATUS_META } from "@starshop/shared";
import { clsx } from "clsx";
import { AnimatePresence, motion } from "motion/react";
import { CircleAlert, CircleCheck, Inbox, X } from "lucide-react";
import {
  createContext,
  forwardRef,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";

export const cn = clsx;

// --- buttons ---------------------------------------------------------------------

type Variant = "primary" | "secondary" | "ghost" | "danger";
const variants: Record<Variant, string> = {
  primary: "bg-accent-gradient text-white shadow-glow hover:brightness-110",
  secondary: "bg-surface-2 text-text ring-1 ring-inset ring-line hover:bg-surface-3",
  ghost: "text-text-2 hover:bg-surface-2 hover:text-text",
  danger: "bg-danger/12 text-danger ring-1 ring-inset ring-danger/30 hover:bg-danger/20",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; loading?: boolean; icon?: ReactNode }>(
  function Button({ variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest }, ref) {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap font-semibold transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50",
          size === "sm" ? "h-8 rounded-lg px-3 text-[12.5px]" : "h-10 rounded-xl px-4 text-[13.5px]",
          variants[variant],
          className,
        )}
        {...rest}
      >
        {loading ? <Spinner /> : icon}
        {children}
      </button>
    );
  },
);

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cn("size-4 animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

// --- surfaces ----------------------------------------------------------------------

export function Card({ className, children, title, action }: { className?: string; children: ReactNode; title?: ReactNode; action?: ReactNode }) {
  return (
    <section className={cn("rounded-2xl bg-surface ring-1 ring-inset ring-line shadow-card", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <h2 className="text-[14px] font-semibold">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageTitle({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-[24px] font-semibold tracking-[-0.03em]">{title}</h1>
        {subtitle && <p className="mt-1 text-[13.5px] text-text-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const tones: Record<StatusTone, string> = {
  neutral: "bg-text-3/12 text-text-2 ring-text-3/20",
  warning: "bg-warning/12 text-warning ring-warning/25",
  info: "bg-accent/14 text-[color-mix(in_oklab,var(--c-accent)_70%,var(--c-text))] ring-accent/30",
  success: "bg-success/12 text-success ring-success/25",
  danger: "bg-danger/12 text-danger ring-danger/25",
  violet: "bg-accent-2/14 text-[color-mix(in_oklab,var(--c-accent-2)_70%,var(--c-text))] ring-accent-2/30",
};

export function Badge({ tone = "neutral", children, className }: { tone?: StatusTone; children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full px-2.5 text-[11.5px] font-semibold ring-1 ring-inset", tones[tone], className)}>{children}</span>;
}

export function StatusBadge({ status }: { status: OrderStatus }) {
  const meta = STATUS_META[status];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export function ModeBadge({ mode }: { mode: string }) {
  return mode === "demo" ? <Badge tone="warning">DEMO</Badge> : null;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-xl bg-surface-2", className)} aria-hidden />;
}

export function Empty({ title, text, icon }: { title: string; text?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <div className="mb-3 flex size-12 items-center justify-center rounded-2xl bg-surface-2 ring-1 ring-line">{icon ?? <Inbox className="size-5 text-text-3" />}</div>
      <div className="text-[14.5px] font-semibold">{title}</div>
      {text && <p className="mt-1 max-w-[360px] text-[13px] text-text-2">{text}</p>}
    </div>
  );
}

export function ErrorBox({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl bg-danger/10 p-4 text-[13.5px] text-danger ring-1 ring-inset ring-danger/25">
      <CircleAlert className="size-5 shrink-0" />
      <span className="flex-1">{text}</span>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          Повторить
        </Button>
      )}
    </div>
  );
}

export function KV({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="divide-y divide-line">
      {items.map(([k, v], i) => (
        <div key={i} className="flex items-start justify-between gap-4 px-5 py-2.5 text-[13.5px]">
          <dt className="shrink-0 text-text-3">{k}</dt>
          <dd className="min-w-0 break-words text-right font-medium">{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

// --- form controls -----------------------------------------------------------------

const fieldBase = "w-full rounded-xl bg-surface-2 px-3.5 text-[14px] text-text outline-none ring-1 ring-inset ring-line transition placeholder:text-text-3 focus:ring-2 focus:ring-accent disabled:opacity-60";

export function Label({ label, hint, children, error }: { label: string; hint?: ReactNode; children: ReactNode; error?: string | null }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12.5px] font-semibold text-text-2">{label}</span>
      {children}
      {(error || hint) && <span className={cn("mt-1.5 block text-[12px]", error ? "text-danger" : "text-text-3")}>{error || hint}</span>}
    </label>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={cn(fieldBase, "h-10", className)} {...rest} />;
});

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(fieldBase, "min-h-[96px] py-2.5 leading-relaxed", className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(fieldBase, "h-10 pr-8", className)} {...rest}>
      {children}
    </select>
  );
}

export function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  const id = useId();
  return (
    <label htmlFor={id} className="flex cursor-pointer items-start gap-3">
      <input id={id} type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span
        aria-hidden
        className="relative mt-0.5 h-6 w-10 shrink-0 rounded-full bg-surface-3 ring-1 ring-inset ring-line transition peer-checked:bg-accent peer-focus-visible:ring-2 peer-focus-visible:ring-accent after:absolute after:left-0.5 after:top-0.5 after:size-5 after:rounded-full after:bg-white after:shadow after:transition peer-checked:after:translate-x-4"
      />
      <span>
        <span className="block text-[13.5px] font-semibold">{label}</span>
        {hint && <span className="block text-[12px] text-text-3">{hint}</span>}
      </span>
    </label>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: string }[] }) {
  return (
    <div role="tablist" className="no-scrollbar flex gap-1 overflow-x-auto rounded-xl bg-surface-2 p-1 ring-1 ring-inset ring-line">
      {items.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={t.id === value}
          onClick={() => onChange(t.id)}
          className={cn("whitespace-nowrap rounded-lg px-3 py-1.5 text-[13px] font-semibold transition", t.id === value ? "bg-surface text-text shadow-card ring-1 ring-line" : "text-text-3 hover:text-text-2")}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Pagination({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (offset: number) => void }) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-3 text-[13px] text-text-2">
      <span>
        {offset + 1}–{Math.min(offset + limit, total)} из {total}
      </span>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onChange(Math.max(0, offset - limit))}>
          Назад
        </Button>
        <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => onChange(offset + limit)}>
          Вперёд
        </Button>
      </div>
    </div>
  );
}

// --- modal ------------------------------------------------------------------------

export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    setTimeout(() => panel.current?.querySelector<HTMLElement>("input, textarea, select, button")?.focus(), 30);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [open, onClose]);
  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6">
          <motion.div className="absolute inset-0 bg-black/60 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.div
            ref={panel}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 24 }}
            transition={{ type: "spring", stiffness: 420, damping: 36 }}
            className={cn("relative z-10 max-h-[92dvh] w-full overflow-y-auto rounded-t-2xl bg-surface ring-1 ring-line shadow-2xl sm:rounded-2xl", wide ? "sm:max-w-[720px]" : "sm:max-w-[480px]")}
          >
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-surface px-5 py-4">
              <h2 className="text-[15.5px] font-semibold">{title}</h2>
              <button onClick={onClose} aria-label="Закрыть" className="rounded-lg p-1.5 text-text-3 hover:bg-surface-2 hover:text-text">
                <X className="size-5" />
              </button>
            </div>
            <div className="space-y-4 p-5">{children}</div>
            {footer && <div className="sticky bottom-0 flex justify-end gap-2 border-t border-line bg-surface px-5 py-4">{footer}</div>}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

// --- toasts -----------------------------------------------------------------------

type Toast = { id: number; text: string; tone: "success" | "error" };
const ToastCtx = createContext<(text: string, tone?: "success" | "error") => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const counter = useRef(0);
  const push = useCallback((text: string, tone: "success" | "error" = "success") => {
    const id = ++counter.current;
    setItems((l) => [...l.slice(-3), { id, text, tone }]);
    setTimeout(() => setItems((l) => l.filter((t) => t.id !== id)), 4200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex flex-col items-end gap-2" aria-live="polite">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="pointer-events-auto flex max-w-[380px] items-center gap-2.5 rounded-xl bg-surface-2 px-4 py-3 text-[13.5px] font-medium shadow-2xl ring-1 ring-line"
              role={t.tone === "error" ? "alert" : "status"}
            >
              {t.tone === "error" ? <CircleAlert className="size-5 shrink-0 text-danger" /> : <CircleCheck className="size-5 shrink-0 text-success" />}
              {t.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
