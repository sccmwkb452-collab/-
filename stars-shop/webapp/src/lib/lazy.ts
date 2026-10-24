import { lazy, type ComponentType } from "react";
import { isChunkError, reloadOnce } from "./errors";

/** React.lazy that survives a flaky network and a redeploy: one more attempt
 * after a pause, then a single page reload for the new build. If that does not
 * help either, the error reaches the ErrorBoundary with a retry button. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyPage<T extends ComponentType<any>>(load: () => Promise<T>) {
  return lazy(async () => {
    try {
      return { default: await load() };
    } catch (first) {
      await new Promise((r) => setTimeout(r, 700));
      try {
        return { default: await load() };
      } catch (second) {
        if (isChunkError(second) && reloadOnce()) return new Promise<never>(() => {});
        throw first;
      }
    }
  });
}
