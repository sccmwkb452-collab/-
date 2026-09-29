import { Calculator, Inbox, LayoutDashboard, Settings, House } from "lucide-react";

export const ADMIN_NAV = [
  { href: "/admin", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { href: "/admin/projects", label: "Проекты", icon: House },
  { href: "/admin/leads", label: "Заявки", icon: Inbox },
  { href: "/admin/pricing", label: "Цены", icon: Calculator },
  { href: "/admin/settings", label: "Настройки", icon: Settings },
] as const;
