export type OptionPricingType = "FIXED" | "PER_M2";

export interface PricingHouseType {
  code: string;
  name: string;
  description: string;
  floors: number;
  multiplier: number;
}

export interface PricingTechnology {
  slug: string;
  name: string;
  shortDescription: string;
  pricePerM2: number;
}

export interface PricingPackage {
  code: string;
  name: string;
  description: string;
  includes: string[];
  multiplier: number;
}

export interface PricingOption {
  code: string;
  name: string;
  description: string;
  pricingType: OptionPricingType;
  price: number;
}

export interface PricingParams {
  areaMin: number;
  areaMax: number;
  bedroomBaseCount: number;
  bedroomSurcharge: number;
  roundingStep: number;
  spreadPercent: number;
}

export interface PricingConfig {
  houseTypes: PricingHouseType[];
  technologies: PricingTechnology[];
  packages: PricingPackage[];
  options: PricingOption[];
  params: PricingParams;
}

export interface EstimateInput {
  houseType: string;
  area: number;
  bedrooms: number;
  technology: string;
  package: string;
  options: string[];
}

export type EstimateLine = {
  code: string;
  label: string;
  amount: number;
}

export type EstimateResult = {
  base: number;
  houseTypeAdjustment: number;
  packageAdjustment: number;
  bedroomsAdjustment: number;
  optionsTotal: number;
  options: EstimateLine[];
  total: number;
  rangeMin: number;
  rangeMax: number;
  labels: {
    houseType: string;
    technology: string;
    package: string;
  };
}
