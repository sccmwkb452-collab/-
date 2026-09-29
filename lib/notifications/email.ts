import nodemailer from "nodemailer";
import { escapeHtml, leadAdminUrl, leadLines } from "./format";
import type { NotificationChannel } from "./types";

export const emailChannel: NotificationChannel = {
  name: "email",
  enabled: () => Boolean(process.env.SMTP_HOST && process.env.NOTIFY_EMAIL_TO),
  async send(lead) {
    const port = Number(process.env.SMTP_PORT ?? 465);
    const transport = nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port,
      secure: port === 465,
      auth: process.env.SMTP_USER ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASSWORD } : undefined,
    });
    const lines = leadLines(lead);
    const rows = lines
      .map(([k, v]) => `<tr><td style="padding:6px 16px 6px 0;color:#7a7266">${escapeHtml(k)}</td><td style="padding:6px 0;color:#171717">${escapeHtml(v)}</td></tr>`)
      .join("");
    await transport.sendMail({
      from: process.env.SMTP_FROM || process.env.SMTP_USER,
      to: process.env.NOTIFY_EMAIL_TO,
      subject: `Новая заявка: ${lead.name}, ${lead.phone}`,
      text: ["НОВАЯ ЗАЯВКА", ...lines.map(([k, v]) => `${k}: ${v}`), leadAdminUrl(lead.id)].join("\n"),
      html: `<div style="font-family:Arial,sans-serif"><h2 style="margin:0 0 16px">Новая заявка</h2><table>${rows}</table><p><a href="${escapeHtml(leadAdminUrl(lead.id))}">Открыть в CRM</a></p></div>`,
    });
  },
};
