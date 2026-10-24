/** Reports Mini App failures to the server (Admin → Ошибки). Only the error
 * text, the screen and a short stack are sent: never launch data, tokens or
 * form contents. */

const MAX_REPORTS = 10;
const RELOAD_FLAG = "starshop.chunk_reload";
let sent = 0;
const seen = new Set<string>();

function clip(text: string | undefined | null, n: number): string | undefined {
  return text ? text.slice(0, n) : undefined;
}

export function reportError(kind: string, error: unknown): void {
  const err = error instanceof Error ? error : new Error(typeof error === "string" ? error : "Unknown error");
  const message = clip(err.message || String(error), 500) ?? "Unknown error";
  const key = `${kind}:${message}`;
  if (seen.has(key) || sent >= MAX_REPORTS) return;
  seen.add(key);
  sent += 1;
  try {
    void fetch("/api/v1/client-errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: kind.slice(0, 32), message, path: clip(location.pathname, 256), stack: clip(err.stack, 4000) }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* reporting must never break the app */
  }
}

/** A script chunk of an older (or newer) build could not be loaded: after a
 * redeploy the old hashed files are gone. */
export function isChunkError(error: unknown): boolean {
  const text = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  return /dynamically imported module|Importing a module script failed|Failed to fetch|ChunkLoadError|Unable to preload CSS|error loading dynamically/i.test(text);
}

/** Reloads the page once to pick up the current build; false when it was already tried. */
export function reloadOnce(): boolean {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_FLAG) ?? 0);
    if (Date.now() - last < 60_000) return false;
    sessionStorage.setItem(RELOAD_FLAG, String(Date.now()));
  } catch {
    return false;
  }
  location.reload();
  return true;
}

export function installErrorReporting(): void {
  window.addEventListener("error", (e) => {
    // Resource errors (images) have no `error`; only script failures are reported.
    if (e.error) reportError("error", e.error);
  });
  window.addEventListener("unhandledrejection", (e) => reportError("promise", e.reason));
  // Vite: a preloaded chunk of the old build is gone after a redeploy.
  window.addEventListener("vite:preloadError", (e) => {
    e.preventDefault();
    reportError("chunk", (e as Event & { payload?: unknown }).payload ?? "preload error");
    reloadOnce();
  });
}
