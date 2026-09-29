"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { Controller, useForm, type Path } from "react-hook-form";
import { toast } from "sonner";
import { Field } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { createProjectAction, updateProjectAction } from "@/lib/actions/projects";
import { slugify } from "@/lib/utils";
import { projectSchema, type ProjectFormInput, type ProjectFormOutput } from "@/lib/validation/admin";

interface ProjectFormProps {
  projectId?: string;
  defaults: ProjectFormInput;
  houseTypes: { id: string; name: string }[];
  technologies: { id: string; name: string }[];
}

const FLAGS: { name: "hasGarage" | "hasTerrace" | "hasOffice" | "hasSecondLight" | "hasPanoramicWindows" | "featured"; label: string }[] = [
  { name: "hasGarage", label: "Гараж" },
  { name: "hasTerrace", label: "Терраса" },
  { name: "hasOffice", label: "Кабинет" },
  { name: "hasSecondLight", label: "Второй свет" },
  { name: "hasPanoramicWindows", label: "Панорамные окна" },
  { name: "featured", label: "Показывать на главной" },
];

export function ProjectForm({ projectId, defaults, houseTypes, technologies }: ProjectFormProps) {
  const router = useRouter();
  const form = useForm<ProjectFormInput, unknown, ProjectFormOutput>({ resolver: zodResolver(projectSchema), defaultValues: defaults, mode: "onTouched" });
  const { register, control, formState: { errors, isSubmitting } } = form;
  const err = (name: keyof ProjectFormInput) => errors[name]?.message as string | undefined;

  const onSubmit = form.handleSubmit(async (values) => {
    const res = projectId ? await updateProjectAction(projectId, values) : await createProjectAction(values);
    if (!res.ok) {
      Object.entries(res.fieldErrors ?? {}).forEach(([k, v]) => v?.[0] && form.setError(k as Path<ProjectFormInput>, { message: v[0] }));
      toast.error(res.error);
      return;
    }
    toast.success(res.message ?? "Сохранено");
    if (!projectId && res.data && "id" in res.data) router.push(`/admin/projects/${res.data.id}?created=1`);
    else router.refresh();
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Основное</CardTitle></CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <Field id="title" label="Название" required error={err("title")}>
            <Input
              id="title"
              placeholder="Дом «Артем»"
              {...register("title", {
                onBlur: (e: React.FocusEvent<HTMLInputElement>) => {
                  if (!form.getValues("slug")) form.setValue("slug", slugify(e.target.value.replace(/дом/i, "dom")), { shouldValidate: true });
                },
              })}
            />
          </Field>
          <Field id="slug" label="Адрес страницы (slug)" required error={err("slug")} hint="/projects/адрес — латиница и дефисы">
            <Input id="slug" placeholder="dom-artem" {...register("slug")} />
          </Field>
          <Field id="subtitle" label="Подзаголовок" error={err("subtitle")} className="sm:col-span-2">
            <Input id="subtitle" placeholder="Современный двухэтажный дом со вторым светом" {...register("subtitle")} />
          </Field>
          <Field id="description" label="Описание" required error={err("description")} className="sm:col-span-2">
            <Textarea id="description" rows={6} {...register("description")} />
          </Field>
          <Field id="featuresText" label="Особенности (каждая с новой строки)" error={err("featuresText")} className="sm:col-span-2">
            <Textarea id="featuresText" rows={5} placeholder={"Кухня-гостиная 34 м²\nМастер-спальня с гардеробной"} {...register("featuresText")} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Параметры</CardTitle></CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Field id="area" label="Площадь, м²" required error={err("area")}>
            <Input id="area" type="number" step="0.1" inputMode="decimal" {...register("area")} />
          </Field>
          <Field id="bedrooms" label="Спальни" required error={err("bedrooms")}>
            <Input id="bedrooms" type="number" inputMode="numeric" {...register("bedrooms")} />
          </Field>
          <Field id="bathrooms" label="Санузлы" required error={err("bathrooms")}>
            <Input id="bathrooms" type="number" inputMode="numeric" {...register("bathrooms")} />
          </Field>
          <Field id="priceFrom" label="Цена от, ₽" required error={err("priceFrom")}>
            <Input id="priceFrom" type="number" inputMode="numeric" step="10000" {...register("priceFrom")} />
          </Field>
          <Field id="houseTypeId" label="Этажность" required error={err("houseTypeId")}>
            <Controller
              control={control}
              name="houseTypeId"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="houseTypeId"><SelectValue placeholder="Выберите" /></SelectTrigger>
                  <SelectContent>
                    {houseTypes.map((h) => <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
          </Field>
          <Field id="technologyId" label="Технология" error={err("technologyId")}>
            <Controller
              control={control}
              name="technologyId"
              render={({ field }) => (
                <Select value={field.value ?? "none"} onValueChange={field.onChange}>
                  <SelectTrigger id="technologyId"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">На выбор клиента</SelectItem>
                    {technologies.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
          </Field>
          <Field id="dimensions" label="Габариты" error={err("dimensions")}>
            <Input id="dimensions" placeholder="11,6 × 10,6 м" {...register("dimensions")} />
          </Field>
          <Field id="ceilingHeight" label="Высота потолков, м" error={err("ceilingHeight")}>
            <Input id="ceilingHeight" type="number" step="0.1" inputMode="decimal" {...register("ceilingHeight")} />
          </Field>
          <div className="grid gap-3 sm:col-span-2 sm:grid-cols-2 lg:col-span-4 lg:grid-cols-3">
            {FLAGS.map((f) => (
              <Controller
                key={f.name}
                control={control}
                name={f.name}
                render={({ field }) => (
                  <label className="flex items-center justify-between gap-3 rounded-xl border border-border px-4 py-3 text-sm font-medium cursor-pointer">
                    {f.label}
                    <Switch checked={Boolean(field.value)} onCheckedChange={field.onChange} />
                  </label>
                )}
              />
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Публикация и SEO</CardTitle></CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <Field id="status" label="Статус" required>
            <Controller
              control={control}
              name="status"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="status"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="PUBLISHED">Опубликован</SelectItem>
                    <SelectItem value="DRAFT">Черновик</SelectItem>
                    <SelectItem value="HIDDEN">Скрыт</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </Field>
          <Field id="sortOrder" label="Порядок сортировки" error={err("sortOrder")} hint="Меньше — выше в каталоге">
            <Input id="sortOrder" type="number" inputMode="numeric" {...register("sortOrder")} />
          </Field>
          <Field id="seoTitle" label="SEO title" error={err("seoTitle")} className="sm:col-span-2">
            <Input id="seoTitle" maxLength={120} {...register("seoTitle")} />
          </Field>
          <Field id="seoDescription" label="SEO description" error={err("seoDescription")} className="sm:col-span-2">
            <Textarea id="seoDescription" rows={2} maxLength={300} {...register("seoDescription")} />
          </Field>
        </CardContent>
      </Card>

      <div className="sticky bottom-4 z-10 flex justify-end">
        <Button type="submit" size="lg" disabled={isSubmitting} className="shadow-xl">
          {isSubmitting ? <Loader2 className="animate-spin" /> : <Save />}
          {projectId ? "Сохранить изменения" : "Создать проект"}
        </Button>
      </div>
    </form>
  );
}
