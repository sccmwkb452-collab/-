import "server-only";
import type { SiteSetting } from "@prisma/client";
import { cache } from "react";
import { prisma } from "@/lib/db";

export type SiteSettings = Omit<SiteSetting, "id" | "updatedAt">;

export const DEFAULT_SETTINGS: SiteSettings = {
  companyName: "FORMA HOUSE",
  slogan: "Дома, созданные для жизни",
  description: "Мы строим загородные дома с полным сопровождением — от выбора проекта до передачи ключей.",
  logoUrl: null,
  phone: "+7 (495) 120-45-67",
  email: "hello@forma-house.ru",
  address: "Москва",
  workingHours: "Ежедневно с 9:00 до 21:00",
  telegram: null,
  whatsapp: null,
  vk: null,
  primaryColor: "#171717",
  accentColor: "#A47B45",
  footerText: "",
  seoTitle: "FORMA HOUSE — строительство частных домов",
  seoDescription: "Проекты домов, калькулятор стоимости и строительство под ключ.",
};

export const getSiteSettings = cache(async (): Promise<SiteSettings> => {
  try {
    const row = await prisma.siteSetting.findUnique({ where: { id: 1 } });
    if (!row) return DEFAULT_SETTINGS;
    const { id: _id, updatedAt: _updatedAt, ...rest } = row;
    return rest;
  } catch (error) {
    console.error("[settings] failed to load", error);
    return DEFAULT_SETTINGS;
  }
});

const HEX = /^#[0-9a-fA-F]{6}$/;

/** Цвета из настроек подставляются в CSS только после строгой проверки формата. */
export function brandCss(settings: SiteSettings) {
  const primary = HEX.test(settings.primaryColor) ? settings.primaryColor : DEFAULT_SETTINGS.primaryColor;
  const accent = HEX.test(settings.accentColor) ? settings.accentColor : DEFAULT_SETTINGS.accentColor;
  return `:root{--brand-primary:${primary};--brand-accent:${accent};}`;
}
