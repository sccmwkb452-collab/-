"use client";

import * as React from "react";

import { Field, Input, NativeSelect, Textarea } from "@/components/ui/input";
import { DELIVERY_TYPE } from "@/lib/status";
import type { Category } from "@/lib/types";

export type ProductFormValue = {
  name: string;
  category_id: string;
  sku: string;
  description: string;
  region: string;
  face_value: string;
  face_currency: string;
  delivery_type: string;
  delivery_time: string;
  activation_notes: string;
  buyer_instructions: string;
  required_buyer_data: string;
  supplier_quantity: string;
  manual_unit_cost: string;
};

export const EMPTY_PRODUCT: ProductFormValue = {
  name: "",
  category_id: "",
  sku: "",
  description: "",
  region: "",
  face_value: "",
  face_currency: "",
  delivery_type: "manual",
  delivery_time: "до 30 минут",
  activation_notes: "",
  buyer_instructions: "",
  required_buyer_data: "",
  supplier_quantity: "1",
  manual_unit_cost: "",
};

export function toPayload(v: ProductFormValue, creating: boolean) {
  const dec = (s: string) => (s.trim() ? s.trim().replace(",", ".") : null);
  const payload: Record<string, unknown> = {
    name: v.name.trim(),
    description: v.description,
    region: v.region.trim(),
    face_value: dec(v.face_value),
    face_currency: v.face_currency.trim().toUpperCase() || null,
    delivery_type: v.delivery_type,
    delivery_time: v.delivery_time.trim(),
    activation_notes: v.activation_notes,
    buyer_instructions: v.buyer_instructions,
    required_buyer_data: v.required_buyer_data.trim(),
    supplier_quantity: Number(v.supplier_quantity) || 1,
    manual_unit_cost: dec(v.manual_unit_cost),
  };
  if (creating) {
    payload.category_id = Number(v.category_id);
    payload.sku = v.sku.trim() || null;
  }
  return payload;
}

export function ProductForm({
  value,
  onChange,
  categories,
  creating,
}: {
  value: ProductFormValue;
  onChange: (v: ProductFormValue) => void;
  categories?: Category[];
  creating?: boolean;
}) {
  const set = (patch: Partial<ProductFormValue>) => onChange({ ...value, ...patch });
  const category = categories?.find((c) => String(c.id) === value.category_id);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Название" className="sm:col-span-2">
        <Input value={value.name} onChange={(e) => set({ name: e.target.value })} placeholder="Telegram Stars — 100 звёзд" />
      </Field>
      {creating && (
        <>
          <Field
            label="Категория"
            hint={category ? `${category.compliance_label.replace(/^\S+\s/, "")}${category.compliance_note ? " — " + category.compliance_note : ""}` : undefined}
            className="sm:col-span-2"
          >
            <NativeSelect value={value.category_id} onChange={(e) => set({ category_id: e.target.value })}>
              <option value="">Выберите категорию…</option>
              {categories?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.compliance_status !== "approved" ? " — требует проверки/запрещено" : ""}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Артикул (SKU)" hint="Пусто — сгенерируется автоматически">
            <Input value={value.sku} onChange={(e) => set({ sku: e.target.value })} />
          </Field>
        </>
      )}
      <Field label="Способ выдачи">
        <NativeSelect value={value.delivery_type} onChange={(e) => set({ delivery_type: e.target.value })}>
          {Object.entries(DELIVERY_TYPE).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <Field label="Номинал" hint="Например 100 (звёзд), 3 (месяца), 5 (USD)">
        <Input inputMode="decimal" value={value.face_value} onChange={(e) => set({ face_value: e.target.value })} />
      </Field>
      <Field label="Валюта или единица номинала" hint="STARS, MONTHS, USD, UC…">
        <Input value={value.face_currency} onChange={(e) => set({ face_currency: e.target.value })} />
      </Field>
      <Field label="Регион">
        <Input value={value.region} onChange={(e) => set({ region: e.target.value })} placeholder="Глобальный, RU, TR…" />
      </Field>
      <Field label="Срок выдачи">
        <Input value={value.delivery_time} onChange={(e) => set({ delivery_time: e.target.value })} />
      </Field>
      <Field label="Единиц у поставщика на одну продажу" hint="Например 100 звёзд = 100 единиц прайса">
        <Input inputMode="numeric" value={value.supplier_quantity} onChange={(e) => set({ supplier_quantity: e.target.value.replace(/\D/g, "") })} />
      </Field>
      <Field label="Себестоимость вручную, ₽" hint="Если нет поставщика с API — используется для расчёта цены">
        <Input inputMode="decimal" value={value.manual_unit_cost} onChange={(e) => set({ manual_unit_cost: e.target.value })} />
      </Field>
      <Field label="Что нужно от покупателя" className="sm:col-span-2" hint="Например: @username в Telegram">
        <Input value={value.required_buyer_data} onChange={(e) => set({ required_buyer_data: e.target.value })} />
      </Field>
      <Field label="Описание" className="sm:col-span-2">
        <Textarea value={value.description} onChange={(e) => set({ description: e.target.value })} />
      </Field>
      <Field label="Инструкция для покупателя" className="sm:col-span-2">
        <Textarea value={value.buyer_instructions} onChange={(e) => set({ buyer_instructions: e.target.value })} className="min-h-16" />
      </Field>
      <Field label="Заметки по активации (внутренние)" className="sm:col-span-2">
        <Textarea value={value.activation_notes} onChange={(e) => set({ activation_notes: e.target.value })} className="min-h-16" />
      </Field>
    </div>
  );
}
