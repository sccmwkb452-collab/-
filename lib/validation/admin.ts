import { z } from "zod";

const intField = (min: number, max: number, msg = "Введите число") =>
  z.coerce.number({ error: msg }).int("Должно быть целым").min(min, `Не меньше ${min}`).max(max, `Не больше ${max}`);
const floatField = (min: number, max: number) =>
  z.coerce.number({ error: "Введите число" }).min(min, `Не меньше ${min}`).max(max, `Не больше ${max}`);
const optionalString = (max: number) =>
  z
    .string()
    .trim()
    .max(max, `Не более ${max} символов`)
    .nullish()
    .transform((v) => (v ? v : null));

export const loginSchema = z.object({
  email: z.email("Неверный email").trim().toLowerCase().max(120),
  password: z.string().min(1, "Введите пароль").max(200),
});

export const passwordSchema = z
  .string()
  .min(10, "Минимум 10 символов")
  .max(200)
  .refine((v) => /[a-zа-я]/i.test(v) && /\d/.test(v), "Пароль должен содержать буквы и цифры");

export const projectSchema = z.object({
  title: z.string().trim().min(2, "Укажите название").max(120),
  slug: z
    .string()
    .trim()
    .toLowerCase()
    .min(2, "Укажите адрес")
    .max(100)
    .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Только латиница, цифры и дефисы"),
  subtitle: optionalString(200),
  description: z.string().trim().min(10, "Добавьте описание").max(5000),
  area: floatField(20, 2000),
  bedrooms: intField(0, 20),
  bathrooms: intField(0, 20),
  houseTypeId: z.string().min(1, "Выберите тип дома"),
  technologyId: z
    .string()
    .nullish()
    .transform((v) => (v && v !== "none" ? v : null)),
  priceFrom: intField(0, 2_000_000_000),
  dimensions: optionalString(40),
  ceilingHeight: z.preprocess((v) => (v === "" || v === null || v === undefined ? null : v), z.coerce.number().min(2).max(10).nullable()),
  hasGarage: z.boolean(),
  hasTerrace: z.boolean(),
  hasOffice: z.boolean(),
  hasSecondLight: z.boolean(),
  hasPanoramicWindows: z.boolean(),
  featuresText: z.string().max(3000).default(""),
  status: z.enum(["DRAFT", "PUBLISHED", "HIDDEN"]),
  featured: z.boolean(),
  sortOrder: intField(0, 10000),
  seoTitle: optionalString(120),
  seoDescription: optionalString(300),
});

export type ProjectFormInput = z.input<typeof projectSchema>;
export type ProjectFormOutput = z.output<typeof projectSchema>;

export const technologyPriceSchema = z.object({
  id: z.string().min(1),
  name: z.string().trim().min(2).max(60),
  pricePerM2: intField(1000, 10_000_000),
  buildTime: z.string().trim().min(1).max(40),
  warranty: z.string().trim().min(1).max(60),
  shortDescription: z.string().trim().min(5).max(200),
  active: z.boolean(),
});

export const packagePriceSchema = z.object({
  id: z.string().min(1),
  name: z.string().trim().min(2).max(60),
  description: z.string().trim().min(5).max(300),
  multiplier: floatField(0.1, 3),
  active: z.boolean(),
});

export const houseTypePriceSchema = z.object({
  id: z.string().min(1),
  name: z.string().trim().min(2).max(60),
  multiplier: floatField(0.3, 3),
  active: z.boolean(),
});

export const optionSchema = z.object({
  id: z.string().optional(),
  code: z
    .string()
    .trim()
    .toLowerCase()
    .min(2)
    .max(40)
    .regex(/^[a-z0-9-]+$/, "Только латиница, цифры и дефисы"),
  name: z.string().trim().min(2, "Укажите название").max(60),
  description: z.string().trim().max(200).default(""),
  pricingType: z.enum(["FIXED", "PER_M2"]),
  price: intField(0, 100_000_000),
  active: z.boolean(),
  sortOrder: intField(0, 1000),
});

export const priceParamSchema = z.object({
  key: z.string().min(1).max(60),
  value: floatField(0, 1_000_000_000),
});

const hex = z.string().trim().regex(/^#[0-9a-fA-F]{6}$/, "Цвет в формате #RRGGBB");
const url = z
  .string()
  .trim()
  .max(300)
  .nullish()
  .refine((v) => !v || /^https?:\/\//.test(v), "Ссылка должна начинаться с https://")
  .transform((v) => (v ? v : null));

export const settingsSchema = z.object({
  companyName: z.string().trim().min(2).max(60),
  slogan: z.string().trim().min(2).max(120),
  description: z.string().trim().min(10).max(500),
  phone: z.string().trim().min(5).max(40),
  email: z.email("Неверный email").trim().max(120),
  address: z.string().trim().min(3).max(200),
  workingHours: z.string().trim().min(3).max(100),
  telegram: url,
  whatsapp: url,
  vk: url,
  primaryColor: hex,
  accentColor: hex,
  footerText: z.string().trim().max(300).default(""),
  seoTitle: z.string().trim().min(5).max(120),
  seoDescription: z.string().trim().min(10).max(300),
});

export type SettingsInput = z.input<typeof settingsSchema>;

export const adminCreateSchema = z.object({
  name: z.string().trim().min(2).max(80),
  email: z.email("Неверный email").trim().toLowerCase().max(120),
  password: passwordSchema,
});

export const faqSchema = z.object({
  id: z.string().optional(),
  question: z.string().trim().min(5).max(300),
  answer: z.string().trim().min(5).max(3000),
  category: z.enum(["general", "construction", "payment"]),
  sortOrder: intField(0, 1000),
  published: z.boolean(),
});
