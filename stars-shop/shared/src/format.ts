const CURRENCY_FALLBACK: Record<string, string> = { RUB: "₽", USD: "$", EUR: "€", KZT: "₸", UAH: "₴", BYN: "Br" };

/** "1690.5" + RUB -> "1 690,50 ₽"; whole amounts are shown without kopecks. */
export function formatMoney(amount: string | number | null | undefined, currency: string): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  const value = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(value)) return "—";
  if (currency === "XTR") return `${formatStars(Math.round(value))} ⭐`; // Telegram Stars
  const whole = Math.round(value * 100) % 100 === 0;
  try {
    return new Intl.NumberFormat("ru-RU", {
      style: "currency",
      currency,
      minimumFractionDigits: whole ? 0 : 2,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    const symbol = CURRENCY_FALLBACK[currency] ?? currency;
    return `${value.toFixed(whole ? 0 : 2).replace(".", ",")} ${symbol}`;
  }
}

/** Price per star with up to 4 significant decimals: "1,69 ₽". */
export function formatRate(amount: string | null | undefined, currency: string): string {
  if (!amount) return "—";
  const value = Number(amount);
  const digits = value < 1 ? 3 : 2;
  try {
    return new Intl.NumberFormat("ru-RU", { style: "currency", currency, minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
  } catch {
    return `${value.toFixed(digits)} ${CURRENCY_FALLBACK[currency] ?? currency}`;
  }
}

export function formatStars(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("ru-RU").format(value);
}

export function formatDate(iso: string | null | undefined, timeZone?: string, withTime = true): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric", timeZone };
  if (withTime) Object.assign(opts, { hour: "2-digit", minute: "2-digit" });
  try {
    return new Intl.DateTimeFormat("ru-RU", opts).format(date);
  } catch {
    return new Intl.DateTimeFormat("ru-RU", { ...opts, timeZone: undefined }).format(date);
  }
}

/** "23 окт., 11:16" — compact form for lists. */
export function formatShortDate(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone };
  try {
    return new Intl.DateTimeFormat("ru-RU", opts).format(date);
  } catch {
    return new Intl.DateTimeFormat("ru-RU", { ...opts, timeZone: undefined }).format(date);
  }
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  const diff = (new Date(iso).getTime() - now.getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat("ru-RU", { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

/** Russian plural: plural(5, ["звезда", "звезды", "звёзд"]) -> "звёзд". */
export function plural(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
  return forms[2];
}
