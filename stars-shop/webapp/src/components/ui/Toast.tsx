import { AnimatePresence, motion } from "motion/react";
import { CircleAlert, CircleCheck, Info } from "lucide-react";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { haptic } from "../../lib/telegram";

type Tone = "success" | "error" | "info";
interface Toast {
  id: number;
  tone: Tone;
  text: string;
}

const ToastContext = createContext<(text: string, tone?: Tone) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const counter = useRef(0);
  const push = useCallback((text: string, tone: Tone = "info") => {
    const id = ++counter.current;
    if (tone === "error") haptic.error();
    if (tone === "success") haptic.success();
    setItems((list) => [...list.slice(-2), { id, tone, text }]);
    setTimeout(() => setItems((list) => list.filter((t) => t.id !== id)), 3800);
  }, []);
  const icon = { success: <CircleCheck className="size-5 text-success" />, error: <CircleAlert className="size-5 text-danger" />, info: <Info className="size-5 text-accent" /> };
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 top-[calc(var(--safe-top)+12px)] z-[60] flex flex-col items-center gap-2 px-4" aria-live="polite">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: -12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -12 }}
              className="pointer-events-auto flex max-w-[440px] items-center gap-2.5 rounded-2xl bg-surface-2/95 px-4 py-3 text-[14px] font-medium text-text shadow-2xl ring-1 ring-line backdrop-blur-xl"
              role={t.tone === "error" ? "alert" : "status"}
            >
              {icon[t.tone]}
              <span>{t.text}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
