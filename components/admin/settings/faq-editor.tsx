"use client";

import { Loader2, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { deleteFaqAction, saveFaqAction } from "@/lib/actions/settings";

interface FaqRow {
  id?: string;
  question: string;
  answer: string;
  category: "general" | "construction" | "payment";
  sortOrder: number;
  published: boolean;
}

const CATEGORIES = { general: "Общие", construction: "Строительство", payment: "Оплата" } as const;

function FaqItem({ row, onRemoveDraft }: { row: FaqRow; onRemoveDraft: () => void }) {
  const router = useRouter();
  const [value, setValue] = useState(row);
  const [pending, start] = useTransition();
  const dirty = JSON.stringify(value) !== JSON.stringify(row) || !row.id;
  const run = (fn: () => Promise<{ ok: boolean; error?: string; message?: string }>, after?: () => void) =>
    start(async () => {
      const res = await fn();
      if (res.ok) {
        toast.success(res.message ?? "Сохранено");
        after?.();
        router.refresh();
      } else toast.error(res.error ?? "Ошибка");
    });

  return (
    <li className="space-y-2 rounded-xl border border-border p-3">
      <Input value={value.question} onChange={(e) => setValue({ ...value, question: e.target.value })} placeholder="Вопрос" aria-label="Вопрос" className="h-10 font-medium" />
      <Textarea value={value.answer} onChange={(e) => setValue({ ...value, answer: e.target.value })} placeholder="Ответ" aria-label="Ответ" rows={3} />
      <div className="flex flex-wrap items-center gap-3">
        <Select value={value.category} onValueChange={(v) => setValue({ ...value, category: v as FaqRow["category"] })}>
          <SelectTrigger className="h-9 w-44 text-sm" aria-label="Категория"><SelectValue /></SelectTrigger>
          <SelectContent>
            {Object.entries(CATEGORIES).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Switch checked={value.published} onCheckedChange={(v) => setValue({ ...value, published: v })} />
          Опубликован
        </label>
        <div className="ml-auto flex gap-1">
          <Button size="sm" disabled={!dirty || pending} onClick={() => run(() => saveFaqAction(value), row.id ? undefined : onRemoveDraft)}>
            {pending && <Loader2 className="animate-spin" />}
            Сохранить
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Удалить вопрос"
            className="text-destructive hover:bg-destructive/10"
            disabled={pending}
            onClick={() => {
              if (!row.id) return onRemoveDraft();
              const id = row.id;
              if (window.confirm("Удалить вопрос?")) run(() => deleteFaqAction(id));
            }}
          >
            <Trash2 />
          </Button>
        </div>
      </div>
    </li>
  );
}

export function FaqEditor({ faqs }: { faqs: FaqRow[] }) {
  const [drafts, setDrafts] = useState<number[]>([]);
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Вопросы и ответы</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">Показываются на главной, странице FAQ и страницах проектов.</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setDrafts([...drafts, Date.now()])}>
          <Plus />
          Добавить
        </Button>
      </CardHeader>
      <CardContent>
        <ul className="space-y-3">
          {faqs.map((f) => <FaqItem key={f.id} row={f} onRemoveDraft={() => undefined} />)}
          {drafts.map((d) => (
            <FaqItem
              key={d}
              row={{ question: "", answer: "", category: "general", sortOrder: faqs.length + 1, published: true }}
              onRemoveDraft={() => setDrafts(drafts.filter((x) => x !== d))}
            />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
