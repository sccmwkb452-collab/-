"use client";

import { Loader2, Trash2, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Field } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { changePasswordAction, createAdminAction, deleteAdminAction } from "@/lib/actions/settings";
import { formatDate } from "@/lib/utils";

interface AdminRow {
  id: string;
  name: string;
  email: string;
  lastLoginAt: string | null;
}

export function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [pending, start] = useTransition();
  return (
    <Card>
      <CardHeader><CardTitle>Смена пароля</CardTitle></CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            start(async () => {
              const res = await changePasswordAction({ current, next });
              if (res.ok) {
                toast.success(res.message ?? "Готово");
                setCurrent("");
                setNext("");
                setErrors({});
              } else {
                setErrors({ current: res.fieldErrors?.current?.[0], next: res.fieldErrors?.next?.[0] });
                toast.error(res.error);
              }
            });
          }}
        >
          <Field id="pwd-current" label="Текущий пароль" error={errors.current}>
            <Input id="pwd-current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
          </Field>
          <Field id="pwd-next" label="Новый пароль" error={errors.next} hint="Минимум 10 символов, буквы и цифры">
            <Input id="pwd-next" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
          </Field>
          <Button type="submit" disabled={pending || !current || !next}>
            {pending && <Loader2 className="animate-spin" />}
            Изменить пароль
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function AdminsCard({ admins, currentId }: { admins: AdminRow[]; currentId: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});

  return (
    <Card>
      <CardHeader><CardTitle>Администраторы</CardTitle></CardHeader>
      <CardContent className="space-y-6">
        <ul className="divide-y divide-border rounded-xl border border-border">
          {admins.map((a) => (
            <li key={a.id} className="flex items-center gap-3 p-3">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{a.name}{a.id === currentId && " (вы)"}</span>
                <span className="block truncate text-xs text-muted-foreground">{a.email} · {a.lastLoginAt ? `вход ${formatDate(a.lastLoginAt, true)}` : "ещё не входил"}</span>
              </span>
              {a.id !== currentId && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Удалить ${a.email}`}
                  className="text-destructive hover:bg-destructive/10"
                  disabled={pending}
                  onClick={() =>
                    window.confirm(`Удалить администратора ${a.email}?`) &&
                    start(async () => {
                      const res = await deleteAdminAction(a.id);
                      if (res.ok) {
                        toast.success(res.message ?? "Удалено");
                        router.refresh();
                      } else toast.error(res.error);
                    })
                  }
                >
                  <Trash2 />
                </Button>
              )}
            </li>
          ))}
        </ul>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            start(async () => {
              const res = await createAdminAction(form);
              if (res.ok) {
                toast.success(res.message ?? "Готово");
                setForm({ name: "", email: "", password: "" });
                setErrors({});
                router.refresh();
              } else {
                setErrors({ name: res.fieldErrors?.name?.[0], email: res.fieldErrors?.email?.[0], password: res.fieldErrors?.password?.[0] });
                toast.error(res.error);
              }
            });
          }}
        >
          <p className="text-sm font-semibold">Добавить администратора</p>
          <Field id="adm-name" label="Имя" error={errors.name}>
            <Input id="adm-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field id="adm-email" label="Email" error={errors.email}>
            <Input id="adm-email" type="email" autoComplete="off" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </Field>
          <Field id="adm-password" label="Пароль" error={errors.password} hint="Минимум 10 символов, буквы и цифры">
            <Input id="adm-password" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </Field>
          <Button type="submit" variant="outline" disabled={pending}>
            {pending ? <Loader2 className="animate-spin" /> : <UserPlus />}
            Добавить
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
