import type { ProjectCardData } from "@/types/project";

export const AREA_BUCKETS = [
  { value: "lt100", label: "до 100 м²", test: (a: number) => a < 100 },
  { value: "100-150", label: "100–150 м²", test: (a: number) => a >= 100 && a < 150 },
  { value: "150-200", label: "150–200 м²", test: (a: number) => a >= 150 && a < 200 },
  { value: "gt200", label: "200+ м²", test: (a: number) => a >= 200 },
] as const;

export const FLOOR_OPTIONS = [
  { value: "1", label: "1 этаж" },
  { value: "2", label: "2 этажа" },
  { value: "mansard", label: "Мансарда" },
] as const;

export const BEDROOM_OPTIONS = [
  { value: "2", label: "2" },
  { value: "3", label: "3" },
  { value: "4", label: "4" },
  { value: "5", label: "5+" },
] as const;

export const FEATURE_OPTIONS = [
  { value: "garage", label: "Гараж", key: "hasGarage" },
  { value: "terrace", label: "Терраса", key: "hasTerrace" },
  { value: "office", label: "Кабинет", key: "hasOffice" },
  { value: "second-light", label: "Второй свет", key: "hasSecondLight" },
  { value: "panoramic", label: "Панорамные окна", key: "hasPanoramicWindows" },
] as const satisfies readonly { value: string; label: string; key: keyof ProjectCardData }[];

export const SORT_OPTIONS = [
  { value: "popular", label: "Сначала популярные" },
  { value: "price-asc", label: "Сначала дешевле" },
  { value: "price-desc", label: "Сначала дороже" },
  { value: "area-asc", label: "По площади ↑" },
  { value: "area-desc", label: "По площади ↓" },
] as const;

export interface CatalogFilters {
  area: string[];
  floors: string[];
  bedrooms: string[];
  features: string[];
  priceMin: number | null;
  priceMax: number | null;
  sort: string;
}

export const EMPTY_FILTERS: CatalogFilters = { area: [], floors: [], bedrooms: [], features: [], priceMin: null, priceMax: null, sort: "popular" };

const list = (v: string | null) => (v ? v.split(",").filter(Boolean) : []);
const num = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : null);

export function parseFilters(params: URLSearchParams): CatalogFilters {
  return {
    area: list(params.get("area")),
    floors: list(params.get("floors")),
    bedrooms: list(params.get("bedrooms")),
    features: list(params.get("features")),
    priceMin: num(params.get("priceMin")),
    priceMax: num(params.get("priceMax")),
    sort: params.get("sort") ?? "popular",
  };
}

export function filtersToParams(f: CatalogFilters) {
  const p = new URLSearchParams();
  if (f.area.length) p.set("area", f.area.join(","));
  if (f.floors.length) p.set("floors", f.floors.join(","));
  if (f.bedrooms.length) p.set("bedrooms", f.bedrooms.join(","));
  if (f.features.length) p.set("features", f.features.join(","));
  if (f.priceMin !== null) p.set("priceMin", String(f.priceMin));
  if (f.priceMax !== null) p.set("priceMax", String(f.priceMax));
  if (f.sort !== "popular") p.set("sort", f.sort);
  return p;
}

export function countActive(f: CatalogFilters) {
  return f.area.length + f.floors.length + f.bedrooms.length + f.features.length + (f.priceMin !== null || f.priceMax !== null ? 1 : 0);
}

export function applyFilters(projects: ProjectCardData[], f: CatalogFilters) {
  const result = projects.filter((p) => {
    if (f.area.length && !AREA_BUCKETS.some((b) => f.area.includes(b.value) && b.test(p.area))) return false;
    if (f.floors.length) {
      const floorKey = p.houseTypeCode === "mansard" ? "mansard" : String(p.floors);
      if (!f.floors.includes(floorKey)) return false;
    }
    if (f.bedrooms.length) {
      const bedKey = p.bedrooms >= 5 ? "5" : String(p.bedrooms);
      if (!f.bedrooms.includes(bedKey)) return false;
    }
    for (const feature of FEATURE_OPTIONS) {
      if (f.features.includes(feature.value) && !p[feature.key]) return false;
    }
    if (f.priceMin !== null && p.priceFrom < f.priceMin) return false;
    if (f.priceMax !== null && p.priceFrom > f.priceMax) return false;
    return true;
  });
  const sorters: Record<string, (a: ProjectCardData, b: ProjectCardData) => number> = {
    "price-asc": (a, b) => a.priceFrom - b.priceFrom,
    "price-desc": (a, b) => b.priceFrom - a.priceFrom,
    "area-asc": (a, b) => a.area - b.area,
    "area-desc": (a, b) => b.area - a.area,
  };
  const sorter = sorters[f.sort];
  return sorter ? [...result].sort(sorter) : result;
}
