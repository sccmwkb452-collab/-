/** Thin typed wrapper over the official Telegram Mini Apps SDK
 * (telegram-web-app.js). Every call is feature-detected so the app also
 * works in a regular browser and on older Telegram clients. */

type HapticImpact = "light" | "medium" | "heavy" | "rigid" | "soft";
type HapticNotice = "error" | "success" | "warning";
export type InvoiceStatus = "paid" | "cancelled" | "failed" | "pending";

interface BackButton {
  show(): void;
  hide(): void;
  onClick(cb: () => void): void;
  offClick(cb: () => void): void;
}

interface WebApp {
  initData: string;
  initDataUnsafe: {
    user?: { id: number; first_name: string; last_name?: string; username?: string; photo_url?: string; is_premium?: boolean; allows_write_to_pm?: boolean };
    start_param?: string;
  };
  version: string;
  platform: string;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  isExpanded: boolean;
  isFullscreen?: boolean;
  safeAreaInset?: { top: number; bottom: number; left: number; right: number };
  contentSafeAreaInset?: { top: number; bottom: number; left: number; right: number };
  BackButton: BackButton;
  HapticFeedback?: {
    impactOccurred(style: HapticImpact): void;
    notificationOccurred(type: HapticNotice): void;
    selectionChanged(): void;
  };
  ready(): void;
  expand(): void;
  close(): void;
  isVersionAtLeast(version: string): boolean;
  setHeaderColor(color: string): void;
  setBackgroundColor(color: string): void;
  setBottomBarColor?(color: string): void;
  enableClosingConfirmation(): void;
  disableClosingConfirmation(): void;
  disableVerticalSwipes?(): void;
  openLink(url: string, options?: { try_instant_view?: boolean }): void;
  openTelegramLink(url: string): void;
  openInvoice?(url: string, cb?: (status: InvoiceStatus) => void): void;
  requestWriteAccess?(cb?: (granted: boolean) => void): void;
  onEvent(event: string, cb: () => void): void;
  offEvent(event: string, cb: () => void): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: WebApp };
  }
}

export const tg: WebApp | undefined = typeof window !== "undefined" ? window.Telegram?.WebApp : undefined;

/** True only when opened inside Telegram with signed launch data. */
export const isTelegram = Boolean(tg && tg.initData);

function supports(version: string): boolean {
  try {
    return Boolean(tg?.isVersionAtLeast(version));
  } catch {
    return false;
  }
}

export function initTelegram(): void {
  if (!tg || !isTelegram) return;
  tg.ready();
  tg.expand();
  if (supports("7.7")) tg.disableVerticalSwipes?.();
}

export function paintChrome(background: string): void {
  if (!tg || !isTelegram || !supports("6.1")) return;
  try {
    tg.setHeaderColor(background);
    tg.setBackgroundColor(background);
    if (supports("7.10")) tg.setBottomBarColor?.(background);
  } catch {
    /* older clients reject custom colors */
  }
}

export const haptic = {
  tap(style: HapticImpact = "light") {
    if (supports("6.1")) tg?.HapticFeedback?.impactOccurred(style);
  },
  success() {
    if (supports("6.1")) tg?.HapticFeedback?.notificationOccurred("success");
  },
  error() {
    if (supports("6.1")) tg?.HapticFeedback?.notificationOccurred("error");
  },
  select() {
    if (supports("6.1")) tg?.HapticFeedback?.selectionChanged();
  },
};

/** Opens a payment page. A Telegram Stars invoice opens in the native payment
 * sheet (Bot API 6.1+); `onInvoiceClosed` gets its final status. */
export function openPayment(
  url: string,
  kind: "telegram" | "external" | "internal" | "invoice" | null,
  onInvoiceClosed?: (status: InvoiceStatus) => void,
): void {
  if (kind === "invoice" && tg && isTelegram && tg.openInvoice && supports("6.1")) {
    tg.openInvoice(url, (status) => onInvoiceClosed?.(status));
  } else if ((kind === "telegram" || kind === "invoice") && tg && isTelegram) {
    tg.openTelegramLink(url);
  } else if (tg && isTelegram) {
    tg.openLink(url);
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

/** The Telegram share sheet for a link (or a new tab outside Telegram). */
export function shareLink(url: string, text: string): void {
  openExternal(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`);
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Older WebViews: a hidden textarea and execCommand.
    try {
      const el = document.createElement("textarea");
      el.value = text;
      el.setAttribute("readonly", "");
      el.style.position = "fixed";
      el.style.opacity = "0";
      document.body.appendChild(el);
      el.select();
      const ok = document.execCommand("copy");
      el.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

export function openExternal(url: string): void {
  if (url.startsWith("https://t.me/") && tg && isTelegram) tg.openTelegramLink(url);
  else if (tg && isTelegram) tg.openLink(url);
  else window.open(url, "_blank", "noopener,noreferrer");
}

export function setClosingConfirmation(enabled: boolean): void {
  if (!tg || !isTelegram || !supports("6.2")) return;
  if (enabled) tg.enableClosingConfirmation();
  else tg.disableClosingConfirmation();
}

export function requestWriteAccess(): Promise<boolean> {
  return new Promise((resolve) => {
    const user = tg?.initDataUnsafe.user;
    if (!tg || !isTelegram || !supports("6.9") || !tg.requestWriteAccess || user?.allows_write_to_pm) {
      resolve(true);
      return;
    }
    try {
      tg.requestWriteAccess((granted) => resolve(granted));
    } catch {
      resolve(false);
    }
  });
}

export function startParam(): string | undefined {
  return tg?.initDataUnsafe.start_param;
}

export function telegramColorScheme(): "light" | "dark" | undefined {
  return isTelegram ? tg?.colorScheme : undefined;
}

export function onTelegramEvent(event: string, cb: () => void): () => void {
  if (!tg || !isTelegram) return () => {};
  tg.onEvent(event, cb);
  return () => tg.offEvent(event, cb);
}
