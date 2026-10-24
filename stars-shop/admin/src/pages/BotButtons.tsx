import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Globe, MessageSquareText, Package, Pencil, Plus, SquareMousePointer, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorBox, Input, Label, Modal, PageTitle, Select, Skeleton, Textarea, Toggle, cn, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { can, useAdmin } from "../lib/auth";
import type { AdminProduct } from "../lib/types";

type Action = "message" | "webapp" | "url" | "section" | "product";
type Style = "primary" | "success" | "danger";

interface BotButton {
  id: number;
  title: string;
  emoji: string | null;
  row: number;
  position: number;
  is_active: boolean;
  action: Action;
  style: Style | null;
  text: string | null;
  url: string | null;
  section: string | null;
  product_id: number | null;
}

interface Options {
  sections: { id: string; title: string }[];
  pages: { path: string; title: string }[];
}

const ACTIONS: { id: Action; label: string; hint: string; icon: typeof Globe }[] = [
  { id: "message", label: "Отправить сообщение", hint: "Бот ответит заданным текстом", icon: MessageSquareText },
  { id: "webapp", label: "Открыть страницу магазина", hint: "Mini App на выбранной странице", icon: SquareMousePointer },
  { id: "url", label: "Открыть ссылку", hint: "Только https://", icon: ExternalLink },
  { id: "section", label: "Раздел бота", hint: "Покупка, профиль, заказы, рефералы, поддержка", icon: Globe },
  { id: "product", label: "Информация о пакете", hint: "Описание и кнопка «Купить»", icon: Package },
];

const STYLES: { id: Style | ""; label: string; dot: string }[] = [
  { id: "", label: "Обычная", dot: "bg-surface-3" },
  { id: "primary", label: "Синяя", dot: "bg-[#2F6BFF]" },
  { id: "success", label: "Зелёная", dot: "bg-success" },
  { id: "danger", label: "Красная", dot: "bg-danger" },
];

type Form = Omit<BotButton, "id" | "style" | "row" | "position" | "product_id"> & { style: Style | ""; row: string; position: string; product_id: string };

const EMPTY: Form = { title: "", emoji: "", row: "0", position: "0", is_active: true, action: "message", style: "", text: "", url: "", section: "buy", product_id: "" };

function toForm(b: BotButton): Form {
  return {
    title: b.title,
    emoji: b.emoji ?? "",
    row: String(b.row),
    position: String(b.position),
    is_active: b.is_active,
    action: b.action,
    style: b.style ?? "",
    text: b.text ?? "",
    url: b.url ?? (b.action === "webapp" ? "/" : ""),
    section: b.section ?? "buy",
    product_id: b.product_id ? String(b.product_id) : "",
  };
}

function describe(b: BotButton, options: Options | undefined, products: AdminProduct[]): string {
  if (b.action === "message") return (b.text ?? "").slice(0, 80);
  if (b.action === "url") return b.url ?? "";
  if (b.action === "webapp") return `Mini App: ${options?.pages.find((p) => p.path === b.url)?.title ?? b.url}`;
  if (b.action === "section") return `Раздел: ${options?.sections.find((s) => s.id === b.section)?.title ?? b.section}`;
  const p = products.find((x) => x.id === b.product_id);
  return p ? `Пакет: ${p.stars_amount ?? p.title ?? "своё количество"} Stars` : "Пакет удалён";
}

export default function BotButtons() {
  const admin = useAdmin();
  const editable = can(admin, "manager");
  const qc = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<BotButton | "new" | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [formError, setFormError] = useState<string | null>(null);

  const data = useQuery({ queryKey: ["bot-buttons"], queryFn: () => api<{ items: BotButton[]; options: Options }>("/bot-buttons") });
  const products = useQuery({ queryKey: ["products"], queryFn: () => api<{ items: AdminProduct[] }>("/products") });

  const save = useMutation({
    mutationFn: () => {
      const body = {
        title: form.title.trim(),
        emoji: form.emoji?.trim() || null,
        row: Number(form.row) || 0,
        position: Number(form.position) || 0,
        is_active: form.is_active,
        action: form.action,
        style: form.style || null,
        text: form.text?.trim() || null,
        url: form.url?.trim() || null,
        section: form.section,
        product_id: form.product_id ? Number(form.product_id) : null,
      };
      return editing === "new" ? api("/bot-buttons", { method: "POST", body }) : api(`/bot-buttons/${(editing as BotButton).id}`, { method: "PUT", body });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bot-buttons"] });
      setEditing(null);
      toast("Сохранено — кнопка уже в меню бота", "success");
    },
    onError: (e) => setFormError(errorMessage(e)),
  });

  const remove = useMutation({
    mutationFn: (b: BotButton) => api(`/bot-buttons/${b.id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bot-buttons"] });
      toast("Кнопка удалена", "success");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const open = (b: BotButton | "new") => {
    setForm(b === "new" ? EMPTY : toForm(b));
    setFormError(null);
    setEditing(b);
  };

  const items = data.data?.items ?? [];
  const options = data.data?.options;
  const packages = (products.data?.items ?? []).filter((p) => !p.is_archived);
  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));

  return (
    <>
      <PageTitle
        title="Кнопки бота"
        subtitle="Дополнительные кнопки главного меню. Изменения видны пользователям сразу, без перезапуска бота."
        actions={
          editable && (
            <Button icon={<Plus className="size-4" />} onClick={() => open("new")} disabled={items.length >= 30}>
              Добавить кнопку
            </Button>
          )
        }
      />
      {data.isError && <ErrorBox text={errorMessage(data.error)} onRetry={() => data.refetch()} />}
      <Card className="mb-5 p-4 text-[13px] text-text-2">
        Основные кнопки меню всегда на месте: <b>🌐 Открыть магазин</b>, <b>⭐️ Купить Stars</b>, профиль, заказы, рефералы и поддержка. Ваши кнопки
        идут ниже, по строкам (0–19) и порядку внутри строки. Цвет кнопки — стиль Telegram: синий, зелёный или красный; в старых версиях Telegram
        кнопка будет обычной.
      </Card>
      <Card className="overflow-hidden">
        {data.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <Empty title="Кнопок пока нет" text="Добавьте ссылку на канал, новости или кнопку конкретного пакета." icon={<SquareMousePointer className="size-6" />} />
        ) : (
          <ul className="divide-y divide-line">
            {items.map((b) => {
              const action = ACTIONS.find((a) => a.id === b.action);
              const style = STYLES.find((s) => s.id === (b.style ?? ""));
              return (
                <li key={b.id} className={cn("flex items-center gap-3 px-4 py-3", !b.is_active && "opacity-55")}>
                  <span className={cn("size-2.5 shrink-0 rounded-full", style?.dot)} title={style?.label} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 font-semibold">
                      {b.emoji} {b.title}
                      {!b.is_active && <Badge>выключена</Badge>}
                    </div>
                    <div className="truncate text-[12.5px] text-text-3">
                      {action?.label} · {describe(b, options, packages)} · строка {b.row}, позиция {b.position}
                    </div>
                  </div>
                  {editable && (
                    <div className="flex shrink-0 gap-1.5">
                      <Button size="sm" variant="secondary" icon={<Pencil className="size-3.5" />} onClick={() => open(b)}>
                        Изменить
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        icon={<Trash2 className="size-3.5" />}
                        loading={remove.isPending && remove.variables?.id === b.id}
                        onClick={() => window.confirm(`Удалить кнопку «${b.title}»?`) && remove.mutate(b)}
                      >
                        Удалить
                      </Button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Новая кнопка" : "Кнопка бота"}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditing(null)}>
              Отмена
            </Button>
            <Button loading={save.isPending} onClick={() => save.mutate()} disabled={!form.title.trim()}>
              Сохранить
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {formError && <ErrorBox text={formError} />}
          <div className="grid grid-cols-[88px_1fr] gap-3">
            <Label label="Эмодзи">
              <Input value={form.emoji ?? ""} maxLength={8} placeholder="📣" onChange={(e) => set("emoji", e.target.value)} />
            </Label>
            <Label label="Название">
              <Input value={form.title} maxLength={48} placeholder="Наш канал" onChange={(e) => set("title", e.target.value)} />
            </Label>
          </div>
          <Label label="Действие">
            <div className="grid gap-2 sm:grid-cols-2">
              {ACTIONS.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => set("action", a.id)}
                  className={cn(
                    "flex items-start gap-2.5 rounded-xl p-3 text-left ring-1 ring-inset transition",
                    form.action === a.id ? "bg-accent/12 ring-accent" : "bg-surface-2 ring-line hover:ring-line-strong",
                  )}
                >
                  <a.icon className="mt-0.5 size-4 shrink-0 text-accent" />
                  <span>
                    <span className="block text-[13px] font-semibold">{a.label}</span>
                    <span className="block text-[11.5px] text-text-3">{a.hint}</span>
                  </span>
                </button>
              ))}
            </div>
          </Label>
          {form.action === "message" && (
            <Label label="Текст сообщения" hint="Обычный текст, до 2000 символов">
              <Textarea rows={4} maxLength={2000} value={form.text ?? ""} onChange={(e) => set("text", e.target.value)} />
            </Label>
          )}
          {form.action === "url" && (
            <Label label="Ссылка" hint="Только https://, например https://t.me/your_channel">
              <Input value={form.url ?? ""} placeholder="https://" onChange={(e) => set("url", e.target.value)} />
            </Label>
          )}
          {form.action === "webapp" && (
            <Label label="Страница магазина">
              <Select value={form.url || "/"} onChange={(e) => set("url", e.target.value)}>
                {options?.pages.map((p) => (
                  <option key={p.path} value={p.path}>
                    {p.title}
                  </option>
                ))}
              </Select>
            </Label>
          )}
          {form.action === "section" && (
            <Label label="Раздел бота">
              <Select value={form.section ?? "buy"} onChange={(e) => set("section", e.target.value)}>
                {options?.sections.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
              </Select>
            </Label>
          )}
          {form.action === "product" && (
            <>
              <Label label="Пакет">
                <Select value={form.product_id} onChange={(e) => set("product_id", e.target.value)}>
                  <option value="">Выберите пакет</option>
                  {packages.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.kind === "custom" ? p.title || "Своё количество" : `${p.stars_amount} Stars`}
                    </option>
                  ))}
                </Select>
              </Label>
              <Label label="Описание" hint="Необязательно">
                <Textarea rows={3} maxLength={2000} value={form.text ?? ""} onChange={(e) => set("text", e.target.value)} />
              </Label>
            </>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Label label="Строка" hint="0–19">
              <Input type="number" min={0} max={19} value={form.row} onChange={(e) => set("row", e.target.value)} />
            </Label>
            <Label label="Позиция в строке" hint="0–19, до 4 кнопок в строке">
              <Input type="number" min={0} max={19} value={form.position} onChange={(e) => set("position", e.target.value)} />
            </Label>
          </div>
          <Label label="Цвет">
            <div className="flex flex-wrap gap-2">
              {STYLES.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => set("style", s.id)}
                  className={cn(
                    "inline-flex h-9 items-center gap-2 rounded-xl px-3 text-[13px] font-semibold ring-1 ring-inset transition",
                    form.style === s.id ? "bg-accent/12 ring-accent" : "bg-surface-2 ring-line",
                  )}
                >
                  <span className={cn("size-2.5 rounded-full", s.dot)} />
                  {s.label}
                </button>
              ))}
            </div>
          </Label>
          <Toggle checked={form.is_active} onChange={(v) => set("is_active", v)} label="Показывать в меню" />
        </div>
      </Modal>
    </>
  );
}
