"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { useForm, useWatch, type Path } from "react-hook-form";
import { toast } from "sonner";
import { Field } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { saveSettingsAction } from "@/lib/actions/settings";
import { settingsSchema, type SettingsInput } from "@/lib/validation/admin";

type Output = import("zod").output<typeof settingsSchema>;

function ColorField({ id, label, value, onChange, error }: { id: string; label: string; value: string; onChange: (v: string) => void; error?: string }) {
  return (
    <Field id={id} label={label} error={error}>
      <div className="flex gap-2">
        <input
          type="color"
          value={/^#[0-9a-f]{6}$/i.test(value) ? value : "#000000"}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="h-12 w-14 cursor-pointer rounded-xl border border-input bg-white p-1"
          aria-label={`${label}: палитра`}
        />
        <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} className="font-mono uppercase" maxLength={7} />
      </div>
    </Field>
  );
}

export function SettingsForm({ defaults }: { defaults: SettingsInput }) {
  const router = useRouter();
  const form = useForm<SettingsInput, unknown, Output>({ resolver: zodResolver(settingsSchema), defaultValues: defaults, mode: "onTouched" });
  const { register, setValue, control, formState: { errors, isSubmitting } } = form;
  const [primaryColor, accentColor] = useWatch({ control, name: ["primaryColor", "accentColor"] });
  const err = (k: keyof SettingsInput) => errors[k]?.message as string | undefined;

  const onSubmit = form.handleSubmit(async (values) => {
    const res = await saveSettingsAction(values);
    if (!res.ok) {
      Object.entries(res.fieldErrors ?? {}).forEach(([k, v]) => v?.[0] && form.setError(k as Path<SettingsInput>, { message: v[0] }));
      toast.error(res.error);
      return;
    }
    toast.success(res.message ?? "Сохранено");
    router.refresh();
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Бренд</CardTitle></CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <Field id="companyName" label="Название компании" required error={err("companyName")}>
            <Input id="companyName" {...register("companyName")} />
          </Field>
          <Field id="slogan" label="Слоган" required error={err("slogan")}>
            <Input id="slogan" {...register("slogan")} />
          </Field>
          <Field id="description" label="Описание компании" required error={err("description")} className="sm:col-span-2">
            <Textarea id="description" rows={3} {...register("description")} />
          </Field>
          <ColorField id="primaryColor" label="Основной цвет" value={primaryColor} onChange={(v) => setValue("primaryColor", v, { shouldDirty: true, shouldValidate: true })} error={err("primaryColor")} />
          <ColorField id="accentColor" label="Акцентный цвет" value={accentColor} onChange={(v) => setValue("accentColor", v, { shouldDirty: true, shouldValidate: true })} error={err("accentColor")} />
          <Field id="footerText" label="Текст в футере" error={err("footerText")} className="sm:col-span-2">
            <Textarea id="footerText" rows={2} {...register("footerText")} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Контакты</CardTitle></CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <Field id="phone" label="Телефон" required error={err("phone")}>
            <Input id="phone" {...register("phone")} />
          </Field>
          <Field id="email" label="Email" required error={err("email")}>
            <Input id="email" type="email" {...register("email")} />
          </Field>
          <Field id="address" label="Адрес" required error={err("address")} className="sm:col-span-2">
            <Input id="address" {...register("address")} />
          </Field>
          <Field id="workingHours" label="Режим работы" required error={err("workingHours")}>
            <Input id="workingHours" {...register("workingHours")} />
          </Field>
          <Field id="telegram" label="Telegram (ссылка)" error={err("telegram")}>
            <Input id="telegram" placeholder="https://t.me/company" {...register("telegram")} />
          </Field>
          <Field id="whatsapp" label="WhatsApp (ссылка)" error={err("whatsapp")}>
            <Input id="whatsapp" placeholder="https://wa.me/79990000000" {...register("whatsapp")} />
          </Field>
          <Field id="vk" label="ВКонтакте (ссылка)" error={err("vk")}>
            <Input id="vk" placeholder="https://vk.com/company" {...register("vk")} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>SEO по умолчанию</CardTitle></CardHeader>
        <CardContent className="grid gap-5">
          <Field id="seoTitle" label="SEO title" required error={err("seoTitle")}>
            <Input id="seoTitle" maxLength={120} {...register("seoTitle")} />
          </Field>
          <Field id="seoDescription" label="SEO description" required error={err("seoDescription")}>
            <Textarea id="seoDescription" rows={3} maxLength={300} {...register("seoDescription")} />
          </Field>
        </CardContent>
      </Card>

      <div className="sticky bottom-4 z-10 flex justify-end">
        <Button type="submit" size="lg" disabled={isSubmitting} className="shadow-xl">
          {isSubmitting ? <Loader2 className="animate-spin" /> : <Save />}
          Сохранить настройки
        </Button>
      </div>
    </form>
  );
}
