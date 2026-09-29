"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { trackEvent } from "@/lib/analytics/events";
import { ContactLeadForm } from "./contact-lead-form";

interface LeadDialogProps {
  trigger: React.ReactNode;
  title: string;
  description: string;
  projectSlug?: string;
}

export function LeadDialog({ trigger, title, description, projectSlug }: LeadDialogProps) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (v) trackEvent("lead_form_open", { source: projectSlug ? "project" : "dialog", project: projectSlug });
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-2xl">{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <ContactLeadForm source={projectSlug ? "PROJECT" : "CONTACT_FORM"} projectSlug={projectSlug} idPrefix="dialog" />
      </DialogContent>
    </Dialog>
  );
}
