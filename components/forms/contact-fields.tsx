"use client";

import Link from "next/link";
import { Controller, type UseFormReturn } from "react-hook-form";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { BUDGET_RANGES } from "@/lib/constants";
import { formatPhoneInput } from "@/lib/leads/client";
import type { ContactFieldsInput } from "@/lib/validation/lead";
import { Field } from "./field";

interface ContactFieldsProps {
  form: UseFormReturn<ContactFieldsInput>;
  idPrefix: string;
  extended?: boolean;
}

export function ContactFields({ form, idPrefix, extended = false }: ContactFieldsProps) {
  const {
    register,
    control,
    formState: { errors },
  } = form;
  const id = (name: string) => `${idPrefix}-${name}`;
  const aria = (name: keyof ContactFieldsInput) => ({
    "aria-invalid": errors[name] ? true : undefined,
    "aria-describedby": errors[name] ? `${id(name)}-error` : undefined,
  });

  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <Field id={id("name")} label="Имя" required error={errors.name?.message}>
        <Input id={id("name")} autoComplete="name" placeholder="Как к вам обращаться" {...register("name")} {...aria("name")} />
      </Field>
      <Field id={id("phone")} label="Телефон" required error={errors.phone?.message}>
        <Controller
          control={control}
          name="phone"
          render={({ field }) => (
            <Input
              id={id("phone")}
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              placeholder="+7 (___) ___-__-__"
              {...field}
              onChange={(e) => field.onChange(formatPhoneInput(e.target.value))}
              {...aria("phone")}
            />
          )}
        />
      </Field>
      <Field id={id("email")} label="Email" error={errors.email?.message}>
        <Input id={id("email")} type="email" autoComplete="email" placeholder="name@mail.ru" {...register("email")} {...aria("email")} />
      </Field>
      <Field id={id("telegram")} label="Telegram" error={errors.telegram?.message}>
        <Input id={id("telegram")} autoComplete="off" placeholder="@username" {...register("telegram")} {...aria("telegram")} />
      </Field>
      {extended && (
        <>
          <Field id={id("region")} label="Где участок" error={errors.region?.message}>
            <Input id={id("region")} placeholder="Например, Истринский район" {...register("region")} {...aria("region")} />
          </Field>
          <Field id={id("budget")} label="Планируемый бюджет" error={errors.budget?.message}>
            <Controller
              control={control}
              name="budget"
              render={({ field }) => (
                <Select value={field.value ?? ""} onValueChange={field.onChange}>
                  <SelectTrigger id={id("budget")}>
                    <SelectValue placeholder="Выберите диапазон" />
                  </SelectTrigger>
                  <SelectContent>
                    {BUDGET_RANGES.map((b) => (
                      <SelectItem key={b.code} value={b.code}>{b.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </Field>
        </>
      )}
      <Field id={id("comment")} label="Комментарий" error={errors.comment?.message} className="sm:col-span-2">
        <Textarea id={id("comment")} rows={3} placeholder="Расскажите об участке или пожеланиях к дому" {...register("comment")} {...aria("comment")} />
      </Field>
      <input type="text" tabIndex={-1} autoComplete="off" aria-hidden className="hidden" {...register("website")} />
      <div className="sm:col-span-2">
        <Controller
          control={control}
          name="consent"
          render={({ field }) => (
            <div className="flex items-start gap-3">
              <Checkbox
                id={id("consent")}
                checked={field.value === true}
                onCheckedChange={(v) => field.onChange(v === true)}
                aria-invalid={errors.consent ? true : undefined}
                className="mt-0.5"
              />
              <label htmlFor={id("consent")} className="text-sm leading-snug text-muted-foreground cursor-pointer">
                Согласен на обработку персональных данных в соответствии с{" "}
                <Link href="/privacy" target="_blank" className="text-foreground underline underline-offset-2">политикой конфиденциальности</Link>
              </label>
            </div>
          )}
        />
        {errors.consent && <p role="alert" className="mt-2 text-[13px] text-destructive">{errors.consent.message}</p>}
      </div>
    </div>
  );
}
