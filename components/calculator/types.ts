import type { ConstructionPeriodCode } from "@/lib/constants";

export interface CalculatorState {
  houseType: string | null;
  area: number;
  bedrooms: number;
  technology: string | null;
  package: string | null;
  options: string[];
  period: ConstructionPeriodCode | null;
}

export interface ProjectContext {
  slug: string;
  title: string;
  cover: string | null;
}

export const STEP_TITLES = [
  "Какой дом вы хотите?",
  "Площадь дома",
  "Количество спален",
  "Технология строительства",
  "Комплектация",
  "Дополнительные опции",
  "Когда планируете строительство?",
] as const;

export const STEP_HINTS = [
  "Выберите тип дома — от этого зависит конструктив и стоимость квадратного метра.",
  "Укажите общую площадь дома. Её можно изменить на любом шаге.",
  "Количество спален влияет на число перегородок, дверей и инженерных точек.",
  "Каждая технология отличается сроками, ощущением от дома и бюджетом.",
  "Выберите, в какой степени готовности вы хотите получить дом.",
  "Отметьте всё, что хотите видеть в своём доме. Можно пропустить.",
  "Это поможет нам спланировать загрузку бригад и подготовить предложение.",
] as const;
