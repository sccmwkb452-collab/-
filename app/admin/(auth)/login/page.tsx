import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { LoginForm } from "@/components/admin/login-form";
import { Logo } from "@/components/layout/logo";
import { getCurrentAdmin } from "@/lib/auth/session";
import { getSiteSettings } from "@/lib/settings";

export const metadata: Metadata = { title: "Вход в админ-панель", robots: { index: false, follow: false } };

export default async function LoginPage() {
  if (await getCurrentAdmin()) redirect("/admin");
  const settings = await getSiteSettings();
  return (
    <main className="grid min-h-dvh lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-primary lg:block">
        <div className="absolute inset-0 bg-[url(/demo/hero.webp)] bg-cover bg-center opacity-70" aria-hidden />
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-black/10" aria-hidden />
        <div className="absolute bottom-12 left-12 max-w-md text-white">
          <p className="text-3xl font-semibold tracking-tight">{settings.slogan}</p>
          <p className="mt-3 text-white/60">Панель управления проектами, ценами и заявками.</p>
        </div>
      </div>
      <div className="flex flex-col justify-center px-6 py-12 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <Logo name={settings.companyName} logoUrl={settings.logoUrl} />
          <h1 className="mt-12 text-3xl font-semibold tracking-tight">Вход в админ-панель</h1>
          <p className="mt-2 text-muted-foreground">Введите данные учётной записи администратора.</p>
          <LoginForm />
        </div>
      </div>
    </main>
  );
}
