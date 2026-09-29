import { Clock, Mail, MapPin, MessageCircle, Phone, Send } from "lucide-react";
import type { Metadata } from "next";
import { ContactLeadForm } from "@/components/forms/contact-lead-form";
import { PageHero } from "@/components/shared/page-hero";
import { pageMetadata } from "@/lib/seo";
import { getSiteSettings } from "@/lib/settings";
import { phoneHref } from "@/lib/utils";

export const metadata: Metadata = pageMetadata({
  title: "Контакты",
  description: "Телефон, email и адрес офиса. Оставьте заявку — инженер ответит на вопросы о строительстве дома.",
  path: "/contacts",
});

export default async function ContactsPage() {
  const s = await getSiteSettings();
  const items = [
    { icon: Phone, label: "Телефон", value: s.phone, href: phoneHref(s.phone) },
    { icon: Mail, label: "Email", value: s.email, href: `mailto:${s.email}` },
    { icon: MapPin, label: "Офис", value: s.address },
    { icon: Clock, label: "Режим работы", value: s.workingHours },
    ...(s.telegram ? [{ icon: Send, label: "Telegram", value: "Написать в Telegram", href: s.telegram }] : []),
    ...(s.whatsapp ? [{ icon: MessageCircle, label: "WhatsApp", value: "Написать в WhatsApp", href: s.whatsapp }] : []),
  ];
  return (
    <>
      <PageHero eyebrow="Контакты" title="Давайте обсудим ваш дом" description="Позвоните, напишите или оставьте заявку — ответим в течение рабочего часа." breadcrumbs={[{ name: "Контакты", path: "/contacts" }]} />
      <section className="container-page grid gap-10 pb-24 lg:grid-cols-12">
        <ul className="grid gap-3 self-start sm:grid-cols-2 lg:col-span-5 lg:grid-cols-1">
          {items.map((it) => {
            const content = (
              <>
                <it.icon className="size-5 text-accent" />
                <span>
                  <span className="block text-xs text-muted-foreground">{it.label}</span>
                  <span className="mt-0.5 block font-semibold">{it.value}</span>
                </span>
              </>
            );
            return (
              <li key={it.label}>
                {it.href ? (
                  <a href={it.href} target={it.href.startsWith("http") ? "_blank" : undefined} rel="noopener noreferrer" className="flex items-start gap-4 rounded-2xl bg-white p-5 transition hover:shadow-md">
                    {content}
                  </a>
                ) : (
                  <div className="flex items-start gap-4 rounded-2xl bg-white p-5">{content}</div>
                )}
              </li>
            );
          })}
        </ul>
        <div className="rounded-3xl border border-border bg-white p-6 sm:p-10 lg:col-span-7">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Оставить заявку</h2>
          <p className="mt-2 mb-8 text-muted-foreground">Расскажите о планах — перезвоним и ответим на вопросы.</p>
          <ContactLeadForm source="CONTACT_FORM" idPrefix="contacts" />
        </div>
      </section>
    </>
  );
}
