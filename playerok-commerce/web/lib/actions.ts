"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "./api";

/** Runs a mutating call with a busy flag and toasts for the outcome. */
export function useAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>, success?: string | ((r: T) => string | undefined)) => {
    setBusy(key);
    try {
      const result = await fn();
      const msg = typeof success === "function" ? success(result) : success;
      if (msg) toast.success(msg);
      return result;
    } catch (err) {
      const e = err as ApiError;
      toast.error(e.message || "Операция не выполнена");
      return undefined;
    } finally {
      setBusy(null);
    }
  }, []);
  return { busy, run };
}
