import { escapeHtml, leadAdminUrl, leadLines } from "./format";
import type { NotificationChannel } from "./types";

export const telegramChannel: NotificationChannel = {
  name: "telegram",
  enabled: () => Boolean(process.env.TELEGRAM_BOT_TOKEN && process.env.TELEGRAM_CHAT_ID),
  async send(lead) {
    const text = [
      "🔔 <b>НОВАЯ ЗАЯВКА</b>",
      "",
      ...leadLines(lead).map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(v)}`),
      "",
      `<a href="${escapeHtml(leadAdminUrl(lead.id))}">Открыть в CRM</a>`,
    ].join("\n");
    const res = await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: process.env.TELEGRAM_CHAT_ID,
        text,
        parse_mode: "HTML",
        disable_web_page_preview: true,
      }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) throw new Error(`Telegram API ответил ${res.status}`);
  },
};
