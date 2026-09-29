export interface ProjectCardData {
  id: string;
  slug: string;
  title: string;
  subtitle: string | null;
  area: number;
  floors: number;
  houseTypeCode: string;
  houseTypeName: string;
  bedrooms: number;
  bathrooms: number;
  priceFrom: number;
  technologyName: string | null;
  cover: { url: string; alt: string } | null;
  hasGarage: boolean;
  hasTerrace: boolean;
  hasOffice: boolean;
  hasSecondLight: boolean;
  hasPanoramicWindows: boolean;
  featured: boolean;
}
