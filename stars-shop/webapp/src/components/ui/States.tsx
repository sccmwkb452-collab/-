import { RefreshCw, WifiOff } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";

export function EmptyState({ icon, title, text, action }: { icon: ReactNode; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <div className="relative mb-5 flex size-20 items-center justify-center">
        <div className="absolute inset-0 rounded-full bg-accent/20 blur-2xl" aria-hidden />
        <div className="relative flex size-16 items-center justify-center rounded-[22px] bg-surface-2 ring-1 ring-line">{icon}</div>
      </div>
      <h3 className="font-display text-[17px] font-semibold tracking-[-0.02em]">{title}</h3>
      {text && <p className="mt-2 max-w-[300px] text-[14px] leading-relaxed text-text-2">{text}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function ErrorState({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <EmptyState
      icon={<WifiOff className="size-7 text-danger" />}
      title="Не удалось загрузить"
      text={text}
      action={
        onRetry && (
          <Button variant="secondary" icon={<RefreshCw className="size-4" />} onClick={onRetry}>
            Повторить
          </Button>
        )
      }
    />
  );
}
