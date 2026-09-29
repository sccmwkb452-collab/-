import { z } from "zod";
import { BUDGET_RANGES, CONSTRUCTION_PERIODS } from "@/lib/constants";

const periodCodes = CONSTRUCTION_PERIODS.map((p) => p.code) as [string, ...string[]];
const budgetCodes = BUDGET_RANGES.map((b) => b.code) as [string, ...string[]];

export const phoneSchema = z
  .string()
  .trim()
  .min(1, "Укажите телефон")
  .refine((v) => /^[+\d\s()-]{7,22}$/.test(v), "Неверный формат телефона")
  .refine((v) => {
    const digits = v.replace(/\D/g, "");
    return digits.length >= 10 && digits.length <= 15;
  }, "Неверный номер телефона");

const optionalText = (max: number) =>
  z
    .string()
    .trim()
    .max(max, `Не более ${max} символов`)
    .optional()
    .transform((v) => (v ? v : undefined));

export const calculatorInputSchema = z.object({
  houseType: z.string().min(1, "Выберите тип дома").max(40),
  area: z.coerce.number().min(20, "Слишком маленькая площадь").max(1000, "Слишком большая площадь"),
  bedrooms: z.coerce.number().int().min(1).max(10),
  technology: z.string().min(1, "Выберите технологию").max(60),
  package: z.string().min(1, "Выберите комплектацию").max(40),
  options: z.array(z.string().max(40)).max(30).default([]),
  period: z.enum(periodCodes, { error: "Выберите срок" }),
  projectSlug: z.string().max(100).optional(),
});

export type CalculatorInput = z.infer<typeof calculatorInputSchema>;

export const contactFieldsSchema = z.object({
  name: z.string().trim().min(2, "Укажите имя").max(80, "Слишком длинное имя"),
  phone: phoneSchema,
  email: z
    .string()
    .trim()
    .max(120)
    .optional()
    .refine((v) => !v || z.email().safeParse(v).success, "Неверный email")
    .transform((v) => (v ? v.toLowerCase() : undefined)),
  telegram: z
    .string()
    .trim()
    .max(64)
    .optional()
    .refine((v) => !v || /^@?[a-zA-Z0-9_]{4,32}$/.test(v), "Ник в формате @username")
    .transform((v) => (v ? (v.startsWith("@") ? v : `@${v}`) : undefined)),
  comment: optionalText(2000),
  region: optionalText(120),
  budget: z.enum(budgetCodes).optional(),
  consent: z.boolean().refine((v) => v === true, "Необходимо согласие на обработку данных"),
  website: z.string().max(0).optional(),
});

export type ContactFieldsInput = z.input<typeof contactFieldsSchema>;

export const leadRequestSchema = z.discriminatedUnion("source", [
  z.object({
    source: z.literal("CALCULATOR"),
    calculationId: z.string().max(40).optional(),
    calculator: calculatorInputSchema,
    contact: contactFieldsSchema,
  }),
  z.object({
    source: z.enum(["PROJECT", "CONTACT_FORM"]),
    projectSlug: z.string().max(100).optional(),
    contact: contactFieldsSchema,
  }),
]);

export type LeadRequest = z.infer<typeof leadRequestSchema>;
