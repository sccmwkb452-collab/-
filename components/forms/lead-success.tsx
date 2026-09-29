"use client";

import { motion } from "framer-motion";
import { Check } from "lucide-react";

export function LeadSuccess({ onReset, compact = false }: { onReset?: () => void; compact?: boolean }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={compact ? "py-4 text-center" : "py-10 text-center"}
      role="status"
    >
      <motion.span
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.15, type: "spring", stiffness: 260, damping: 18 }}
        className="mx-auto flex size-16 items-center justify-center rounded-full bg-success text-white"
      >
        <Check className="size-8" strokeWidth={2.5} />
      </motion.span>
      <p className="mt-6 text-3xl font-semibold tracking-tight">Спасибо!</p>
      <p className="mx-auto mt-3 max-w-sm text-muted-foreground">
        Ваш запрос принят. Специалист свяжется с вами для уточнения деталей.
      </p>
      {onReset && (
        <button type="button" onClick={onReset} className="mt-6 text-sm font-medium underline underline-offset-4 cursor-pointer">
          Отправить ещё одну заявку
        </button>
      )}
    </motion.div>
  );
}
