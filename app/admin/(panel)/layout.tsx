import type { Metadata } from "next";
import { AdminShell } from "@/components/admin/admin-shell";
import { requireAdmin } from "@/lib/auth/session";
import { prisma } from "@/lib/db";
import { getSiteSettings } from "@/lib/settings";

export const metadata: Metadata = {
  title: { default: "Админ-панель", template: "%s — Админ-панель" },
  robots: { index: false, follow: false },
};

export default async function PanelLayout({ children }: { children: React.ReactNode }) {
  const admin = await requireAdmin();
  const [settings, newLeads] = await Promise.all([getSiteSettings(), prisma.lead.count({ where: { status: "NEW" } })]);
  return (
    <AdminShell companyName={settings.companyName} admin={admin} newLeads={newLeads}>
      {children}
    </AdminShell>
  );
}
