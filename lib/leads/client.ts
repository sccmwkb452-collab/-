"use client";

export class LeadSubmitError extends Error {
  constructor(
    message: string,
    public fieldErrors?: Record<string, string[] | undefined>,
  ) {
    super(message);
  }
}

export async function postJson<T>(url: string, payload: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new LeadSubmitError("Нет соединения с сервером. Проверьте интернет и попробуйте ещё раз.");
  }
  const data = (await res.json().catch(() => null)) as { ok?: boolean; error?: string; fieldErrors?: Record<string, string[]> } | null;
  if (!res.ok || !data?.ok) {
    if (res.status === 429) throw new LeadSubmitError("Слишком много запросов. Подождите минуту и попробуйте снова.");
    throw new LeadSubmitError(data?.error ?? "Не удалось отправить данные. Попробуйте ещё раз.", data?.fieldErrors);
  }
  return data as T;
}

/** Маска телефона: +7 (999) 123-45-67 для российских номеров, остальные — как ввели. */
export function formatPhoneInput(value: string) {
  let digits = value.replace(/\D/g, "");
  if (!digits) return value.startsWith("+") ? "+" : "";
  if (digits[0] === "8") digits = `7${digits.slice(1)}`;
  if (digits[0] === "9") digits = `7${digits}`;
  if (digits[0] !== "7") return `+${digits.slice(0, 15)}`;
  const d = digits.slice(0, 11);
  let out = "+7";
  if (d.length > 1) out += ` (${d.slice(1, 4)}`;
  if (d.length >= 4) out += ")";
  if (d.length > 4) out += ` ${d.slice(4, 7)}`;
  if (d.length > 7) out += `-${d.slice(7, 9)}`;
  if (d.length > 9) out += `-${d.slice(9, 11)}`;
  return out;
}
