export interface LeadNotification {
  id: string;
  name: string;
  phone: string;
  email?: string | null;
  telegram?: string | null;
  comment?: string | null;
  region?: string | null;
  project?: string | null;
  houseType?: string | null;
  area?: number | null;
  bedrooms?: number | null;
  technology?: string | null;
  package?: string | null;
  options: string[];
  estimatedPrice?: number | null;
  period?: string | null;
  budget?: string | null;
  source: string;
}

export interface NotificationChannel {
  name: string;
  enabled(): boolean;
  send(lead: LeadNotification): Promise<void>;
}
