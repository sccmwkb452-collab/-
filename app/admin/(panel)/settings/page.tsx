import { BellRing, CheckCircle2, CircleOff } from "lucide-react";
import type { Metadata } from "next";
import { AdminPageHeader } from "@/components/admin/page-header";
import { AdminsCard, PasswordCard } from "@/components/admin/settings/admins-card";
import { FaqEditor } from "@/components/admin/settings/faq-editor";
import { LogoUpload } from "@/components/admin/settings/logo-upload";
import { SettingsForm } from "@/components/admin/settings/settings-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { requireAdmin } from "@/lib/auth/session";
import { prisma } from "@/lib/db";
import { enabledChannels } from "@/lib/notifications";
import { getSiteSettings } from "@/lib/settings";

export const metadata: Metadata = { title: "Настройки" };

export default async function SettingsPage() {
  const me = await requireAdmin();
  const [settings, admins, faqs] = await Promise.all([
    getSiteSettings(),
    prisma.admin.findMany({ orderBy: { createdAt: "asc" }, select: { id: true, name: true, email: true, lastLoginAt: true } }),
    prisma.faq.findMany({ orderBy: { sortOrder: "asc" } }),
  ]);
  const channels = enabledChannels();
  const integrations = [
    { name: "Telegram-бот", enabled: channels.includes("telegram"), env: "TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID" },
    { name: "Email (SMTP)", enabled: channels.includes("email"), env: "SMTP_HOST, NOTIFY_EMAIL_TO" },
    { name: "Яндекс Метрика", enabled: Boolean(process.env.NEXT_PUBLIC_YANDEX_METRIKA_ID), env: "NEXT_PUBLIC_YANDEX_METRIKA_ID" },
    { name: "Google Analytics", enabled: Boolean(process.env.NEXT_PUBLIC_GA_ID), env: "NEXT_PUBLIC_GA_ID" },
    { name: "S3-хранилище", enabled: process.env.STORAGE_DRIVER === "s3", env: "STORAGE_DRIVER=s3, S3_*" },
  ];

  return (
    <>
      <AdminPageHeader title="Настройки" description="Бренд, контакты и SEO применяются на всём публичном сайте." />
      <div className="grid gap-6 xl:grid-cols-[1fr_24rem]">
        <div className="min-w-0 space-y-6">
          <LogoUpload logoUrl={settings.logoUrl} />
          <SettingsForm
            defaults={{
              companyName: settings.companyName,
              slogan: settings.slogan,
              description: settings.description,
              phone: settings.phone,
              email: settings.email,
              address: settings.address,
              workingHours: settings.workingHours,
              telegram: settings.telegram ?? "",
              whatsapp: settings.whatsapp ?? "",
              vk: settings.vk ?? "",
              primaryColor: settings.primaryColor,
              accentColor: settings.accentColor,
              footerText: settings.footerText,
              seoTitle: settings.seoTitle,
              seoDescription: settings.seoDescription,
            }}
          />
          <FaqEditor faqs={faqs.map((f) => ({ id: f.id, question: f.question, answer: f.answer, category: (["general", "construction", "payment"].includes(f.category) ? f.category : "general") as "general" | "construction" | "payment", sortOrder: f.sortOrder, published: f.published }))} />
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><BellRing className="size-4 text-accent" />Интеграции</CardTitle>
              <p className="text-sm text-muted-foreground">Включаются переменными окружения в файле .env — секреты не хранятся в базе и не попадают в браузер.</p>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3">
                {integrations.map((i) => (
                  <li key={i.name} className="flex items-start gap-3 text-sm">
                    {i.enabled ? <CheckCircle2 className="mt-0.5 size-4 text-success" /> : <CircleOff className="mt-0.5 size-4 text-muted-foreground" />}
                    <span>
                      <span className="block font-medium">{i.name} · {i.enabled ? "включено" : "выключено"}</span>
                      <span className="block font-mono text-xs text-muted-foreground">{i.env}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <PasswordCard />
          <AdminsCard admins={admins.map((a) => ({ ...a, lastLoginAt: a.lastLoginAt?.toISOString() ?? null }))} currentId={me.id} />
        </div>
      </div>
    </>
  );
}
