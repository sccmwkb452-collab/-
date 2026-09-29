"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { motion } from "framer-motion";
import { ArrowRight, Info, Loader2, Pencil } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { ContactFields } from "@/components/forms/contact-fields";
import { EMPTY_CONTACT } from "@/components/forms/contact-lead-form";
import { LeadSuccess } from "@/components/forms/lead-success";
import { Button } from "@/components/ui/button";
import { trackEvent } from "@/lib/analytics/events";
import { LeadSubmitError, postJson } from "@/lib/leads/client";
import type { EstimateResult } from "@/lib/pricing/types";
import { formatPrice } from "@/lib/utils";
import { contactFieldsSchema, type ContactFieldsInput } from "@/lib/validation/lead";
import { AnimatedPrice } from "./animated-price";
import type { CalculatorState } from "./types";

interface ResultProps {
  estimate: EstimateResult;
  state: CalculatorState;
  calculationId: string | null;
  projectSlug?: string;
  onEdit: () => void;
  onSubmitted: () => void;
}

export function CalculatorResult({ estimate, state, calculationId, projectSlug, onEdit, onSubmitted }: ResultProps) {
  const [formOpen, setFormOpen] = useState(false);
  const [done, setDone] = useState(false);
  const form = useForm<ContactFieldsInput>({ resolver: zodResolver(contactFieldsSchema), defaultValues: EMPTY_CONTACT, mode: "onTouched" });

  const breakdown = [
    { label: `Базовая стоимость · ${estimate.labels.technology}`, amount: estimate.base },
    { label: `Тип дома · ${estimate.labels.houseType}`, amount: estimate.houseTypeAdjustment },
    { label: `Комплектация · ${estimate.labels.package}`, amount: estimate.packageAdjustment },
    { label: "Дополнительные спальни", amount: estimate.bedroomsAdjustment },
    ...estimate.options.map((o) => ({ label: o.label, amount: o.amount })),
  ].filter((r) => r.amount !== 0);

  const openForm = () => {
    setFormOpen(true);
    trackEvent("lead_form_open", { source: "calculator" });
    requestAnimationFrame(() => document.getElementById("lead-form")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const onSubmit = form.handleSubmit(async (contact) => {
    try {
      await postJson("/api/leads", {
        source: "CALCULATOR",
        calculationId: calculationId ?? undefined,
        calculator: { ...state, projectSlug },
        contact,
      });
      trackEvent("lead_submitted", { source: "calculator", price: estimate.total, project: projectSlug });
      toast.success("Заявка отправлена", { description: "Подробный расчёт подготовит инженер." });
      setDone(true);
      onSubmitted();
    } catch (error) {
      if (error instanceof LeadSubmitError && error.fieldErrors) {
        for (const [key, messages] of Object.entries(error.fieldErrors)) {
          if (messages?.[0] && key in EMPTY_CONTACT) form.setError(key as keyof ContactFieldsInput, { message: messages[0] });
        }
      }
      toast.error("Не удалось отправить заявку", { description: error instanceof Error ? error.message : undefined });
    }
  });

  if (done) {
    return (
      <div className="rounded-3xl border border-border bg-white p-6 sm:p-12">
        <LeadSuccess />
        <p className="text-center text-sm text-muted-foreground">
          Ваш предварительный расчёт: <span className="font-semibold text-foreground">{formatPrice(estimate.total)}</span>
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="overflow-hidden rounded-3xl bg-primary text-primary-foreground"
      >
        <div className="p-6 sm:p-10">
          <p className="eyebrow">Предварительная стоимость строительства</p>
          <AnimatedPrice value={estimate.total} duration={1.4} className="mt-4 block text-5xl font-semibold tracking-tight sm:text-7xl" />
          <p className="mt-3 text-white/55 tabular">
            Диапазон: {formatPrice(estimate.rangeMin)} — {formatPrice(estimate.rangeMax)}
          </p>
          <p className="mt-6 flex max-w-xl gap-3 text-sm leading-relaxed text-white/65">
            <Info className="mt-0.5 size-4 shrink-0 text-accent" />
            Итоговая стоимость зависит от проекта, участка, инженерных решений и выбранной комплектации.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            {!formOpen && (
              <Button size="xl" variant="accent" onClick={openForm}>
                Получить подробный расчёт
                <ArrowRight />
              </Button>
            )}
            <Button size="xl" variant="outline" className="border-white/20 text-white hover:border-white/50 hover:bg-white/5" onClick={onEdit}>
              <Pencil />
              Изменить параметры
            </Button>
          </div>
        </div>
        <div className="border-t border-white/10 bg-white/[0.03] p-6 sm:px-10">
          <p className="text-sm font-semibold">Из чего складывается стоимость</p>
          <dl className="mt-4 space-y-2.5 text-sm">
            {breakdown.map((r) => (
              <div key={r.label} className="flex justify-between gap-4">
                <dt className="text-white/60">{r.label}</dt>
                <dd className="font-medium whitespace-nowrap tabular">{r.amount > 0 ? "" : "−"}{formatPrice(Math.abs(r.amount))}</dd>
              </div>
            ))}
          </dl>
        </div>
      </motion.div>

      {formOpen && (
        <motion.div
          id="lead-form"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="scroll-mt-24 rounded-3xl border border-border bg-white p-6 sm:p-10"
        >
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Куда отправить подробный расчёт?</h2>
          <p className="mt-2 text-muted-foreground">Инженер проверит параметры, уточнит детали по участку и пришлёт смету.</p>
          <form onSubmit={onSubmit} noValidate className="mt-8 space-y-6">
            <ContactFields form={form} idPrefix="calc" extended />
            <Button type="submit" size="xl" className="w-full sm:w-auto" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting && <Loader2 className="animate-spin" />}
              Получить расчёт
            </Button>
          </form>
        </motion.div>
      )}
    </div>
  );
}
