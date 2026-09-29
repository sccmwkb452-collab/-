import "server-only";
import { emailChannel } from "./email";
import { telegramChannel } from "./telegram";
import type { LeadNotification, NotificationChannel } from "./types";

const channels: NotificationChannel[] = [telegramChannel, emailChannel];

export function enabledChannels() {
  return channels.filter((c) => c.enabled()).map((c) => c.name);
}

/** Отправляет уведомление во все включённые каналы. Ошибки канала не мешают остальным. */
export async function notifyNewLead(lead: LeadNotification) {
  const results = await Promise.allSettled(channels.filter((c) => c.enabled()).map((c) => c.send(lead)));
  results.forEach((r) => {
    if (r.status === "rejected") console.error("[notifications]", r.reason);
  });
}

export type { LeadNotification };
