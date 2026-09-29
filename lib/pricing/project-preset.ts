interface ProjectLike {
  area: number;
  bedrooms: number;
  hasGarage: boolean;
  hasTerrace: boolean;
  hasSecondLight: boolean;
  hasPanoramicWindows: boolean;
  houseType: { code: string };
  technology: { slug: string } | null;
}

/** Сопоставление характеристик проекта с кодами опций калькулятора. */
export function projectOptionCodes(p: ProjectLike) {
  return [
    p.hasTerrace && "terrace",
    p.hasGarage && "garage",
    p.hasSecondLight && "second-light",
    p.hasPanoramicWindows && "panoramic-windows",
  ].filter((v): v is string => Boolean(v));
}

export function projectPreset(p: ProjectLike) {
  return {
    houseType: p.houseType.code,
    area: Math.round(p.area),
    bedrooms: Math.min(Math.max(p.bedrooms, 2), 5),
    technology: p.technology?.slug ?? "",
    options: projectOptionCodes(p),
  };
}
