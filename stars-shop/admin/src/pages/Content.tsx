import type { Brand, Content as ContentT } from "@starshop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button, Card, ErrorBox, Input, Label, PageTitle, Select, Skeleton, Tabs, Textarea, Toggle, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";

type TabId = "hero" | "texts" | "support" | "legal" | "announcements" | "banners" | "brand";
const TABS: { id: TabId; label: string }[] = [
  { id: "hero", label: "Главный баннер" },
  { id: "texts", label: "Заголовки" },
  { id: "support", label: "Поддержка" },
  { id: "legal", label: "Условия" },
  { id: "announcements", label: "Объявления" },
  { id: "banners", label: "Акции" },
  { id: "brand", label: "Бренд и цвета" },
];

function ListEditor<T>({ items, onChange, create, render, max }: { items: T[]; onChange: (v: T[]) => void; create: () => T; render: (item: T, update: (patch: Partial<T>) => void) => ReactNode; max: number }) {
  const move = (i: number, d: -1 | 1) => {
    const next = [...items];
    const j = i + d;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };
  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={i} className="rounded-xl bg-surface-2/60 p-4 ring-1 ring-inset ring-line">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-[12px] font-semibold text-text-3">#{i + 1}</span>
            <div className="flex gap-1">
              <button className="rounded-md p-1 text-text-3 hover:text-text disabled:opacity-30" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Выше">
                <ArrowUp className="size-4" />
              </button>
              <button className="rounded-md p-1 text-text-3 hover:text-text disabled:opacity-30" onClick={() => move(i, 1)} disabled={i === items.length - 1} aria-label="Ниже">
                <ArrowDown className="size-4" />
              </button>
              <button className="rounded-md p-1 text-text-3 hover:text-danger" onClick={() => onChange(items.filter((_, k) => k !== i))} aria-label="Удалить">
                <Trash2 className="size-4" />
              </button>
            </div>
          </div>
          <div className="space-y-3">{render(item, (patch) => onChange(items.map((it, k) => (k === i ? { ...it, ...patch } : it))))}</div>
        </div>
      ))}
      <Button variant="secondary" size="sm" icon={<Plus className="size-4" />} disabled={items.length >= max} onClick={() => onChange([...items, create()])}>
        Добавить
      </Button>
    </div>
  );
}

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <Label label={label}>
      <div className="flex items-center gap-2">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value.toUpperCase())} className="h-10 w-12 cursor-pointer rounded-lg bg-transparent" aria-label={label} />
        <Input value={value} onChange={(e) => onChange(e.target.value)} maxLength={7} className="font-mono" />
      </div>
    </Label>
  );
}

const uid = () => Math.random().toString(36).slice(2, 10);

export default function Content() {
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabId>("hero");
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api<{ settings: { content: ContentT; brand: Brand } }>("/settings") });
  const [content, setContent] = useState<ContentT | null>(null);
  const [brand, setBrand] = useState<Brand | null>(null);

  useEffect(() => {
    if (settings.data) {
      setContent(structuredClone(settings.data.settings.content));
      setBrand(structuredClone(settings.data.settings.brand));
    }
  }, [settings.data]);

  const save = useMutation({
    mutationFn: (key: "content" | "brand") => api(`/settings/${key}`, { method: "PUT", body: key === "content" ? content : brand }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast("Сохранено — изменения уже в мини-приложении");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (settings.isError) return <ErrorBox text={errorMessage(settings.error)} onRetry={() => settings.refetch()} />;
  if (!content || !brand) return <Skeleton className="h-96" />;
  const c = content;
  const setC = (patch: Partial<ContentT>) => setContent({ ...c, ...patch });
  const key = tab === "brand" ? "brand" : "content";

  return (
    <>
      <PageTitle
        title="Контент"
        subtitle="Тексты и оформление мини-приложения. Изменения применяются без пересборки фронтенда."
        actions={
          <Button icon={<Save className="size-4" />} loading={save.isPending} onClick={() => save.mutate(key)}>
            Сохранить
          </Button>
        }
      />
      <div className="mb-5">
        <Tabs value={tab} onChange={setTab} items={TABS} />
      </div>
      <Card className="p-5">
        <div className="max-w-[760px] space-y-4">
          {tab === "hero" && (
            <>
              <Label label="Надпись над заголовком">
                <Input value={c.hero.eyebrow} onChange={(e) => setC({ hero: { ...c.hero, eyebrow: e.target.value } })} />
              </Label>
              <Label label="Заголовок" hint="Вторая фраза после точки выделяется градиентом">
                <Input value={c.hero.title} onChange={(e) => setC({ hero: { ...c.hero, title: e.target.value } })} />
              </Label>
              <Label label="Подзаголовок">
                <Textarea value={c.hero.subtitle} onChange={(e) => setC({ hero: { ...c.hero, subtitle: e.target.value } })} rows={3} />
              </Label>
              <Label label="Текст кнопки">
                <Input value={c.hero.cta_label} onChange={(e) => setC({ hero: { ...c.hero, cta_label: e.target.value } })} />
              </Label>
              <Label label="Преимущества (до 3, по одному в строке)">
                <Textarea value={c.hero.benefits.join("\n")} onChange={(e) => setC({ hero: { ...c.hero, benefits: e.target.value.split("\n").slice(0, 4) } })} rows={3} />
              </Label>
            </>
          )}
          {tab === "texts" && (
            <>
              <Label label="Заголовок каталога">
                <Input value={c.catalog_title} onChange={(e) => setC({ catalog_title: e.target.value })} />
              </Label>
              <Label label="Подзаголовок каталога">
                <Input value={c.catalog_subtitle} onChange={(e) => setC({ catalog_subtitle: e.target.value })} />
              </Label>
            </>
          )}
          {tab === "support" && (
            <>
              <Label label="Telegram поддержки" hint="username без @">
                <Input value={c.support.telegram} onChange={(e) => setC({ support: { ...c.support, telegram: e.target.value.replace(/^@/, "") } })} />
              </Label>
              <Label label="Email">
                <Input type="email" value={c.support.email} onChange={(e) => setC({ support: { ...c.support, email: e.target.value } })} />
              </Label>
              <Label label="Часы работы">
                <Input value={c.support.hours} onChange={(e) => setC({ support: { ...c.support, hours: e.target.value } })} />
              </Label>
              <Label label="Время ответа">
                <Input value={c.support.response_time} onChange={(e) => setC({ support: { ...c.support, response_time: e.target.value } })} />
              </Label>
            </>
          )}
          {tab === "legal" && (
            <>
              <Label label="Условия покупки" hint="Каждый абзац с новой строки">
                <Textarea value={c.legal.terms} onChange={(e) => setC({ legal: { ...c.legal, terms: e.target.value } })} rows={8} />
              </Label>
              <Label label="Правила возврата">
                <Textarea value={c.legal.refund_policy} onChange={(e) => setC({ legal: { ...c.legal, refund_policy: e.target.value } })} rows={4} />
              </Label>
            </>
          )}
          {tab === "announcements" && (
            <ListEditor
              items={c.announcements}
              max={5}
              onChange={(announcements) => setC({ announcements })}
              create={() => ({ id: uid(), text: "", tone: "info" as const, link: null, active: true })}
              render={(item, update) => (
                <>
                  <Label label="Текст">
                    <Textarea value={item.text} onChange={(e) => update({ text: e.target.value })} rows={2} maxLength={280} />
                  </Label>
                  <div className="grid grid-cols-2 gap-3">
                    <Label label="Тон">
                      <Select value={item.tone} onChange={(e) => update({ tone: e.target.value as "info" | "success" | "warning" })}>
                        <option value="info">Информация</option>
                        <option value="success">Хорошая новость</option>
                        <option value="warning">Предупреждение</option>
                      </Select>
                    </Label>
                    <Label label="Ссылка (необязательно)">
                      <Input value={item.link ?? ""} onChange={(e) => update({ link: e.target.value || null })} placeholder="https://…" />
                    </Label>
                  </div>
                  <Toggle checked={item.active} onChange={(active) => update({ active })} label="Показывать" />
                </>
              )}
            />
          )}
          {tab === "banners" && (
            <ListEditor
              items={c.promo_banners}
              max={5}
              onChange={(promo_banners) => setC({ promo_banners })}
              create={() => ({ id: uid(), title: "", subtitle: "", cta_label: null, link: null, accent: "#1D8CFF", active: true })}
              render={(item, update) => (
                <>
                  <Label label="Заголовок">
                    <Input value={item.title} onChange={(e) => update({ title: e.target.value })} maxLength={80} />
                  </Label>
                  <Label label="Текст">
                    <Input value={item.subtitle} onChange={(e) => update({ subtitle: e.target.value })} maxLength={200} />
                  </Label>
                  <div className="grid grid-cols-3 gap-3">
                    <Label label="Текст кнопки">
                      <Input value={item.cta_label ?? ""} onChange={(e) => update({ cta_label: e.target.value || null })} maxLength={40} />
                    </Label>
                    <Label label="Ссылка">
                      <Input value={item.link ?? ""} onChange={(e) => update({ link: e.target.value || null })} placeholder="https://…" />
                    </Label>
                    <ColorField label="Акцент" value={item.accent} onChange={(accent) => update({ accent })} />
                  </div>
                  <Toggle checked={item.active} onChange={(active) => update({ active })} label="Показывать" />
                  <p className="text-[12px] text-text-3">Не публикуйте фиктивные скидки и счётчики — только реальные условия.</p>
                </>
              )}
            />
          )}
          {tab === "brand" && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Label label="Название магазина">
                  <Input value={brand.name} onChange={(e) => setBrand({ ...brand, name: e.target.value })} maxLength={40} />
                </Label>
                <Label label="Слоган">
                  <Input value={brand.tagline} onChange={(e) => setBrand({ ...brand, tagline: e.target.value })} maxLength={120} />
                </Label>
              </div>
              <Label label="URL логотипа (необязательно)" hint="Квадратное изображение; по умолчанию — фирменный знак">
                <Input value={brand.logo_url ?? ""} onChange={(e) => setBrand({ ...brand, logo_url: e.target.value || null })} placeholder="https://…/logo.png" />
              </Label>
              <div className="grid grid-cols-3 gap-3">
                <ColorField label="Основной акцент" value={brand.accent_primary} onChange={(v) => setBrand({ ...brand, accent_primary: v })} />
                <ColorField label="Второй акцент" value={brand.accent_secondary} onChange={(v) => setBrand({ ...brand, accent_secondary: v })} />
                <ColorField label="Третий акцент" value={brand.accent_tertiary} onChange={(v) => setBrand({ ...brand, accent_tertiary: v })} />
              </div>
              <div className="h-14 rounded-xl" style={{ background: `linear-gradient(120deg, ${brand.accent_primary}, ${brand.accent_secondary} 60%, ${brand.accent_tertiary})` }} aria-label="Превью градиента" />
            </>
          )}
        </div>
      </Card>
    </>
  );
}
