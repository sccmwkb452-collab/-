/**
 * Параметрическое описание демо-домов для генератора визуализаций.
 * Координаты в метрах: x — от левого края дома, y — высота от уровня земли.
 */

export type Material = "dark" | "wood" | "plaster" | "stone" | "brick" | "graphite";
export type Roof = "flat" | "gable" | "shed-l" | "shed-r";

export interface Win {
  x: number;
  y: number;
  w: number;
  h: number;
  cols?: number;
  rows?: number;
  door?: boolean;
}

export interface Volume {
  x: number;
  w: number;
  h: number;
  material: Material;
  roof: Roof;
  roofH?: number;
  back?: boolean;
  windows: Win[];
}

export interface Deck {
  x: number;
  w: number;
  canopy?: { h: number };
}

export interface PlanRoom {
  name: string;
  w: number;
}

export interface PlanRow {
  h: number;
  rooms: PlanRoom[];
}

export interface FloorPlan {
  title: string;
  width: number;
  rows: PlanRow[];
}

export interface HouseSpec {
  slug: string;
  volumes: Volume[];
  decks?: Deck[];
  garageDoor?: { x: number; w: number; h: number };
  plans: FloorPlan[];
}

export const houses: HouseSpec[] = [
  {
    slug: "dom-artem",
    volumes: [
      {
        x: 0, w: 9, h: 3.4, material: "plaster", roof: "flat",
        windows: [
          { x: 0.8, y: 0, w: 5.2, h: 2.8, cols: 4, door: true },
          { x: 6.8, y: 0.9, w: 1.4, h: 1.6 },
        ],
      },
      {
        x: 3.2, w: 8.6, h: 6.6, material: "wood", roof: "flat",
        windows: [
          { x: 0.6, y: 4.0, w: 3.6, h: 2.0, cols: 3 },
          { x: 5.6, y: 3.6, w: 2.4, h: 2.6, cols: 2 },
          { x: 6.0, y: 0.9, w: 1.8, h: 1.9, cols: 1 },
        ],
      },
    ],
    decks: [{ x: -2.5, w: 6.5, canopy: { h: 3.0 } }],
    plans: [
      {
        title: "План 1 этажа · 84 м²",
        width: 11.6,
        rows: [
          { h: 4.6, rooms: [{ name: "Кухня-гостиная", w: 7.4 }, { name: "Кабинет", w: 4.2 }] },
          { h: 2.2, rooms: [{ name: "Холл", w: 3.6 }, { name: "Лестница", w: 2.4 }, { name: "Санузел", w: 2.6 }, { name: "Котельная", w: 3.0 }] },
          { h: 3.8, rooms: [{ name: "Столовая · второй свет", w: 6.2 }, { name: "Гардероб", w: 2.2 }, { name: "Прихожая", w: 3.2 }] },
        ],
      },
      {
        title: "План 2 этажа · 72 м²",
        width: 11.6,
        rows: [
          { h: 4.2, rooms: [{ name: "Мастер-спальня", w: 5.0 }, { name: "Гардеробная", w: 2.4 }, { name: "Спальня", w: 4.2 }] },
          { h: 2.0, rooms: [{ name: "Холл", w: 5.8 }, { name: "Санузел", w: 2.8 }, { name: "Постирочная", w: 3.0 }] },
          { h: 3.6, rooms: [{ name: "Спальня", w: 4.0 }, { name: "Спальня", w: 3.8 }, { name: "Второй свет", w: 3.8 }] },
        ],
      },
    ],
  },
  {
    slug: "dom-nordik",
    volumes: [
      {
        x: 0, w: 7.2, h: 3.0, material: "dark", roof: "gable", roofH: 3.4,
        windows: [
          { x: 1.2, y: 0, w: 4.8, h: 2.6, cols: 3, door: true },
          { x: 2.6, y: 3.3, w: 2.0, h: 1.6, cols: 1 },
        ],
      },
    ],
    decks: [{ x: -1.6, w: 11.0 }],
    plans: [
      {
        title: "План · 98 м²",
        width: 14.0,
        rows: [
          { h: 4.4, rooms: [{ name: "Кухня-гостиная", w: 7.6 }, { name: "Спальня", w: 3.4 }, { name: "Спальня", w: 3.0 }] },
          { h: 2.6, rooms: [{ name: "Прихожая", w: 3.4 }, { name: "Санузел", w: 2.6 }, { name: "Котельная", w: 2.2 }, { name: "Гардероб", w: 2.4 }, { name: "Кладовая", w: 3.4 }] },
        ],
      },
    ],
  },
  {
    slug: "dom-lesnoy",
    volumes: [
      {
        x: 0, w: 9.6, h: 3.1, material: "wood", roof: "gable", roofH: 4.4,
        windows: [
          { x: 1.4, y: 0, w: 6.8, h: 2.7, cols: 4, door: true },
          { x: 3.2, y: 3.5, w: 3.2, h: 2.4, cols: 2 },
        ],
      },
    ],
    decks: [{ x: -2.0, w: 13.6, canopy: { h: 2.9 } }],
    plans: [
      {
        title: "План 1 этажа · 78 м²",
        width: 9.6,
        rows: [
          { h: 5.0, rooms: [{ name: "Гостиная", w: 5.6 }, { name: "Кухня", w: 4.0 }] },
          { h: 3.0, rooms: [{ name: "Прихожая", w: 3.0 }, { name: "Лестница", w: 2.2 }, { name: "Санузел", w: 2.2 }, { name: "Котельная", w: 2.2 }] },
        ],
      },
      {
        title: "План мансарды · 54 м²",
        width: 9.6,
        rows: [
          { h: 4.0, rooms: [{ name: "Спальня", w: 4.8 }, { name: "Спальня", w: 4.8 }] },
          { h: 2.8, rooms: [{ name: "Спальня", w: 4.2 }, { name: "Холл", w: 2.8 }, { name: "Санузел", w: 2.6 }] },
        ],
      },
    ],
  },
  {
    slug: "dom-grafit",
    volumes: [
      {
        x: 0, w: 5.4, h: 3.2, material: "graphite", roof: "flat",
        windows: [{ x: 3.8, y: 0.9, w: 1.2, h: 1.7 }],
      },
      {
        x: 5.4, w: 10.4, h: 6.9, material: "brick", roof: "flat",
        windows: [
          { x: 0.8, y: 0, w: 4.2, h: 6.1, cols: 3, rows: 2, door: true },
          { x: 6.2, y: 4.0, w: 3.4, h: 2.1, cols: 2 },
          { x: 6.2, y: 0.8, w: 3.4, h: 2.0, cols: 2 },
        ],
      },
    ],
    garageDoor: { x: 0.6, w: 2.9, h: 2.4 },
    decks: [{ x: 15.8, w: 3.4 }],
    plans: [
      {
        title: "План 1 этажа · 124 м²",
        width: 15.8,
        rows: [
          { h: 5.2, rooms: [{ name: "Гараж", w: 5.4 }, { name: "Гостиная · второй свет", w: 6.2 }, { name: "Кухня", w: 4.2 }] },
          { h: 2.4, rooms: [{ name: "Тамбур", w: 2.4 }, { name: "Котельная", w: 3.0 }, { name: "Холл", w: 4.0 }, { name: "Санузел", w: 2.6 }, { name: "Кладовая", w: 3.8 }] },
          { h: 3.4, rooms: [{ name: "Кабинет", w: 4.2 }, { name: "Гостевая спальня", w: 4.4 }, { name: "Прихожая", w: 3.2 }, { name: "Гардероб", w: 4.0 }] },
        ],
      },
      {
        title: "План 2 этажа · 90 м²",
        width: 10.4,
        rows: [
          { h: 4.4, rooms: [{ name: "Мастер-спальня", w: 5.6 }, { name: "Спальня", w: 4.8 }] },
          { h: 2.2, rooms: [{ name: "Холл", w: 4.4 }, { name: "Санузел", w: 3.0 }, { name: "Санузел", w: 3.0 }] },
          { h: 3.8, rooms: [{ name: "Спальня", w: 3.6 }, { name: "Спальня", w: 3.4 }, { name: "Гардеробная", w: 3.4 }] },
        ],
      },
    ],
  },
  {
    slug: "dom-gorizont",
    volumes: [
      {
        x: 0, w: 18.4, h: 3.3, material: "stone", roof: "flat",
        windows: [
          { x: 3.8, y: 0, w: 8.4, h: 2.8, cols: 6, door: true },
          { x: 13.4, y: 0.9, w: 3.6, h: 1.8, cols: 2 },
        ],
      },
    ],
    garageDoor: { x: 0.6, w: 2.7, h: 2.3 },
    decks: [{ x: 3.2, w: 9.6, canopy: { h: 3.3 } }],
    plans: [
      {
        title: "План · 148 м²",
        width: 18.4,
        rows: [
          { h: 5.0, rooms: [{ name: "Гараж", w: 3.6 }, { name: "Кухня-гостиная", w: 8.6 }, { name: "Мастер-спальня", w: 6.2 }] },
          { h: 2.2, rooms: [{ name: "Тамбур", w: 3.6 }, { name: "Холл", w: 6.0 }, { name: "Санузел", w: 2.8 }, { name: "Санузел", w: 2.6 }, { name: "Гардероб", w: 3.4 }] },
          { h: 3.4, rooms: [{ name: "Котельная", w: 3.6 }, { name: "Прихожая", w: 3.4 }, { name: "Спальня", w: 5.4 }, { name: "Спальня", w: 6.0 }] },
        ],
      },
    ],
  },
  {
    slug: "dom-skandi",
    volumes: [
      {
        x: 0, w: 8.4, h: 3.0, material: "plaster", roof: "gable", roofH: 4.2,
        windows: [
          { x: 0.9, y: 0.8, w: 1.4, h: 1.7 },
          { x: 3.2, y: 0, w: 2.0, h: 2.4, cols: 1, door: true },
          { x: 6.1, y: 0.8, w: 1.4, h: 1.7 },
          { x: 3.1, y: 3.4, w: 2.2, h: 2.0, cols: 2 },
        ],
      },
    ],
    decks: [{ x: 8.4, w: 4.2, canopy: { h: 2.7 } }],
    plans: [
      {
        title: "План 1 этажа · 70 м²",
        width: 8.4,
        rows: [
          { h: 5.0, rooms: [{ name: "Кухня-гостиная", w: 8.4 }] },
          { h: 3.4, rooms: [{ name: "Спальня", w: 3.6 }, { name: "Прихожая", w: 2.4 }, { name: "Санузел", w: 2.4 }] },
        ],
      },
      {
        title: "План мансарды · 48 м²",
        width: 8.4,
        rows: [
          { h: 3.8, rooms: [{ name: "Спальня", w: 4.2 }, { name: "Спальня", w: 4.2 }] },
          { h: 2.6, rooms: [{ name: "Холл", w: 3.6 }, { name: "Санузел", w: 2.4 }, { name: "Кладовая", w: 2.4 }] },
        ],
      },
    ],
  },
  {
    slug: "dom-rezidentsiya",
    volumes: [
      {
        x: 0, w: 6.2, h: 3.4, material: "stone", roof: "flat",
        windows: [{ x: 4.6, y: 0.9, w: 1.1, h: 1.8 }],
      },
      {
        x: 6.2, w: 9.0, h: 7.2, material: "plaster", roof: "flat", back: true,
        windows: [
          { x: 0.7, y: 0, w: 5.4, h: 6.4, cols: 4, rows: 2, door: true },
          { x: 6.8, y: 4.2, w: 1.6, h: 2.2 },
          { x: 6.8, y: 0.8, w: 1.6, h: 2.0 },
        ],
      },
      {
        x: 15.2, w: 6.4, h: 6.9, material: "wood", roof: "flat",
        windows: [
          { x: 0.8, y: 3.9, w: 4.8, h: 2.3, cols: 3 },
          { x: 0.8, y: 0, w: 4.8, h: 2.8, cols: 3 },
        ],
      },
    ],
    garageDoor: { x: 0.6, w: 3.6, h: 2.5 },
    decks: [{ x: 21.6, w: 3.6, canopy: { h: 3.2 } }],
    plans: [
      {
        title: "План 1 этажа · 162 м²",
        width: 21.6,
        rows: [
          { h: 5.4, rooms: [{ name: "Гараж на 2 авто", w: 6.2 }, { name: "Гостиная · второй свет", w: 8.0 }, { name: "Кухня-столовая", w: 7.4 }] },
          { h: 2.4, rooms: [{ name: "Тамбур", w: 3.2 }, { name: "Котельная", w: 3.0 }, { name: "Холл", w: 6.4 }, { name: "Санузел", w: 3.0 }, { name: "Кладовая", w: 6.0 }] },
          { h: 3.6, rooms: [{ name: "Мастерская", w: 6.2 }, { name: "Прихожая", w: 4.0 }, { name: "Кабинет", w: 4.8 }, { name: "Гостевая", w: 6.6 }] },
        ],
      },
      {
        title: "План 2 этажа · 124 м²",
        width: 15.4,
        rows: [
          { h: 4.8, rooms: [{ name: "Мастер-спальня", w: 6.4 }, { name: "Второй свет", w: 4.4 }, { name: "Спальня", w: 4.6 }] },
          { h: 2.4, rooms: [{ name: "Гардеробная", w: 3.6 }, { name: "Холл", w: 5.0 }, { name: "Санузел", w: 3.4 }, { name: "Санузел", w: 3.4 }] },
          { h: 3.8, rooms: [{ name: "Спальня", w: 5.2 }, { name: "Спальня", w: 5.0 }, { name: "Постирочная", w: 5.2 }] },
        ],
      },
    ],
  },
  {
    slug: "dom-kubik",
    volumes: [
      {
        x: 0, w: 9.8, h: 3.3, material: "graphite", roof: "flat",
        windows: [
          { x: 0.8, y: 0, w: 4.4, h: 2.8, cols: 3, door: true },
          { x: 6.4, y: 0.9, w: 2.6, h: 1.8, cols: 2 },
        ],
      },
    ],
    decks: [{ x: -1.8, w: 7.4 }],
    plans: [
      {
        title: "План · 86 м²",
        width: 9.8,
        rows: [
          { h: 4.6, rooms: [{ name: "Кухня-гостиная", w: 5.8 }, { name: "Спальня", w: 4.0 }] },
          { h: 2.2, rooms: [{ name: "Прихожая", w: 3.0 }, { name: "Санузел", w: 2.4 }, { name: "Котельная", w: 1.8 }, { name: "Гардероб", w: 2.6 }] },
          { h: 2.0, rooms: [{ name: "Спальня", w: 5.0 }, { name: "Кладовая", w: 4.8 }] },
        ],
      },
    ],
  },
  {
    slug: "dom-riviera",
    volumes: [
      {
        x: 0, w: 12.6, h: 3.2, material: "wood", roof: "shed-r", roofH: 1.6,
        windows: [
          { x: 1.2, y: 0, w: 7.0, h: 2.8, cols: 5, door: true },
          { x: 9.4, y: 0.9, w: 2.2, h: 1.8, cols: 1 },
        ],
      },
    ],
    decks: [{ x: -2.2, w: 11.0, canopy: { h: 3.0 } }],
    plans: [
      {
        title: "План · 124 м²",
        width: 12.6,
        rows: [
          { h: 5.2, rooms: [{ name: "Кухня-гостиная", w: 7.2 }, { name: "Мастер-спальня", w: 5.4 }] },
          { h: 2.4, rooms: [{ name: "Холл", w: 4.4 }, { name: "Санузел", w: 2.6 }, { name: "Санузел", w: 2.6 }, { name: "Котельная", w: 3.0 }] },
          { h: 3.2, rooms: [{ name: "Прихожая", w: 3.6 }, { name: "Спальня", w: 4.6 }, { name: "Спальня", w: 4.4 }] },
        ],
      },
    ],
  },
];
