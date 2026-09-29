"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { trackEvent } from "@/lib/analytics/events";
import { LeadSubmitError, postJson } from "@/lib/leads/client";
import { contactFieldsSchema, type ContactFieldsInput } from "@/lib/validation/lead";
import { ContactFields } from "./contact-fields";
import { LeadSuccess } from "./lead-success";

interface ContactLeadFormProps {
  source: "PROJECT" | "CONTACT_FORM";
  projectSlug?: string;
  idPrefix: string;
  submitLabel?: string;
}

export const EMPTY_CONTACT: ContactFieldsInput = { name: "", phone: "", email: "", telegram: "", comment: "", region: "", consent: false, website: "" };

export function ContactLeadForm({ source, projectSlug, idPrefix, submitLabel = "Отправить заявку" }: ContactLeadFormProps) {
  const [done, setDone] = useState(false);
  const form = useForm<ContactFieldsInput>({ resolver: zodResolver(contactFieldsSchema), defaultValues: EMPTY_CONTACT, mode: "onTouched" });

  const onSubmit = form.handleSubmit(async (contact) => {
    try {
      await postJson("/api/leads", { source, projectSlug, contact });
      trackEvent("lead_submitted", { source, project: projectSlug });
      toast.success("Заявка отправлена", { description: "Мы свяжемся с вами в ближайшее время." });
      setDone(true);
      form.reset(EMPTY_CONTACT);
    } catch (error) {
      if (error instanceof LeadSubmitError && error.fieldErrors) {
        for (const [key, messages] of Object.entries(error.fieldErrors)) {
          if (messages?.[0]) form.setError(key as keyof ContactFieldsInput, { message: messages[0] });
        }
      }
      toast.error("Не удалось отправить заявку", { description: error instanceof Error ? error.message : undefined });
    }
  });

  if (done) return <LeadSuccess onReset={() => setDone(false)} />;

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <ContactFields form={form} idPrefix={idPrefix} />
      <Button type="submit" size="lg" className="w-full sm:w-auto" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting && <Loader2 className="animate-spin" />}
        {submitLabel}
      </Button>
    </form>
  );
}
