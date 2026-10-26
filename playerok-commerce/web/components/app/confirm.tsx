"use client";

import * as React from "react";

import { Button, type ButtonProps } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";

/** Button that opens a confirmation dialog, optionally asking for a reason or a value. */
export function ConfirmAction({
  label,
  title,
  description,
  confirmLabel = "Подтвердить",
  variant = "secondary",
  confirmVariant = "primary",
  size = "sm",
  input,
  onConfirm,
  disabled,
  icon,
}: {
  label: React.ReactNode;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  variant?: ButtonProps["variant"];
  confirmVariant?: ButtonProps["variant"];
  size?: ButtonProps["size"];
  input?: { label: string; placeholder?: string; required?: boolean; multiline?: boolean; type?: string; hint?: string; initial?: string };
  onConfirm: (value: string) => Promise<unknown>;
  disabled?: boolean;
  icon?: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  const [value, setValue] = React.useState(input?.initial ?? "");
  const [busy, setBusy] = React.useState(false);

  async function confirm() {
    setBusy(true);
    try {
      const result = await onConfirm(value.trim());
      if (result !== undefined) {
        setOpen(false);
        setValue(input?.initial ?? "");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={variant} size={size} disabled={disabled}>
          {icon}
          {label}
        </Button>
      </DialogTrigger>
      <DialogContent
        title={title}
        description={description}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button variant={confirmVariant} loading={busy} disabled={Boolean(input?.required && !value.trim())} onClick={confirm}>
              {confirmLabel}
            </Button>
          </>
        }
      >
        {input ? (
          <Field label={input.label} hint={input.hint}>
            {input.multiline ? (
              <Textarea value={value} onChange={(e) => setValue(e.target.value)} placeholder={input.placeholder} autoFocus />
            ) : (
              <Input type={input.type ?? "text"} value={value} onChange={(e) => setValue(e.target.value)} placeholder={input.placeholder} autoFocus />
            )}
          </Field>
        ) : (
          <p className="text-sm text-muted-foreground">Действие будет записано в журнал операций.</p>
        )}
      </DialogContent>
    </Dialog>
  );
}
