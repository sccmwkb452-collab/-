import { Mail, MapPin, MessageCircle, Phone, Send } from "lucide-react";
import Link from "next/link";
import { FOOTER_NAV } from "@/lib/navigation";
import type { SiteSettings } from "@/lib/settings";
import { phoneHref } from "@/lib/utils";
import { Logo } from "./logo";

export function Footer({ settings }: { settings: SiteSettings }) {
  const year = new Date().getFullYear();
  const socials = [
    settings.telegram && { href: settings.telegram, label: "Telegram", icon: Send },
    settings.whatsapp && { href: settings.whatsapp, label: "WhatsApp", icon: MessageCircle },
    settings.vk && { href: settings.vk, label: "ВКонтакте", icon: null },
  ].filter((s): s is { href: string; label: string; icon: typeof Send | null } => Boolean(s));

  return (
    <footer className="bg-primary text-primary-foreground">
      <div className="container-page grid gap-12 py-16 md:grid-cols-2 lg:grid-cols-12 lg:py-20">
        <div className="lg:col-span-5">
          <Logo name={settings.companyName} logoUrl={settings.logoUrl} inverted />
          <p className="mt-6 max-w-sm text-2xl font-semibold tracking-tight text-balance">{settings.slogan}</p>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-white/55">{settings.description}</p>
          {socials.length > 0 && (
            <div className="mt-8 flex gap-2">
              {socials.map((s) => (
                <a
                  key={s.label}
                  href={s.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={s.label}
                  className="flex h-10 min-w-10 items-center justify-center rounded-full border border-white/15 px-3 text-xs font-bold transition hover:border-white/50 hover:bg-white/5"
                >
                  {s.icon ? <s.icon className="size-4" /> : "VK"}
                </a>
              ))}
            </div>
          )}
        </div>

        <nav aria-label="Разделы сайта" className="lg:col-span-3">
          <p className="text-xs font-semibold tracking-[0.16em] text-white/40 uppercase">Разделы</p>
          <ul className="mt-5 space-y-3">
            {FOOTER_NAV.map((item) => (
              <li key={item.href}>
                <Link href={item.href} className="text-sm text-white/75 transition hover:text-white">
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="lg:col-span-4">
          <p className="text-xs font-semibold tracking-[0.16em] text-white/40 uppercase">Контакты</p>
          <ul className="mt-5 space-y-4 text-sm">
            <li>
              <a href={phoneHref(settings.phone)} className="flex items-start gap-3 text-white/85 hover:text-white">
                <Phone className="mt-0.5 size-4 text-accent" />
                <span>
                  <span className="block text-lg font-semibold tabular">{settings.phone}</span>
                  <span className="text-white/45">{settings.workingHours}</span>
                </span>
              </a>
            </li>
            <li>
              <a href={`mailto:${settings.email}`} className="flex items-center gap-3 text-white/85 hover:text-white">
                <Mail className="size-4 text-accent" />
                {settings.email}
              </a>
            </li>
            <li className="flex items-start gap-3 text-white/85">
              <MapPin className="mt-0.5 size-4 shrink-0 text-accent" />
              {settings.address}
            </li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/10">
        <div className="container-page flex flex-col gap-4 py-6 text-xs text-white/40 md:flex-row md:items-center md:justify-between">
          <p>
            © {year} {settings.companyName}. {settings.footerText}
          </p>
          <div className="flex gap-6">
            <Link href="/privacy" className="hover:text-white">Политика конфиденциальности</Link>
            <Link href="/terms" className="hover:text-white">Условия использования</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
