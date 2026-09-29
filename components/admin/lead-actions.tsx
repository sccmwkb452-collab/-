"use client";

import type { LeadStatus } from "@prisma/client";
import { Loader2, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { addLeadCommentAction, deleteLeadAction, updateLeadStatusAction } from "@/lib/actions/leads";
import { LEAD_STATUS_LABELS, LEAD_STATUS_ORDER } from "@/lib/constants";

export function LeadStatusSelect({ leadId, status }: { leadId: string; status: LeadStatus }) {
  const [value, setValue] = useState(status);
  const [pending, start] = useTransition();
  const router = useRouter();
  return (
    <div className="flex items-center gap-2">
      <Select
        value={value}
        disabled={pending}
        onValueChange={(next) => {
          const prev = value;
          setValue(next as LeadStatus);
          start(async () => {
            const res = await updateLeadStatusAction(leadId, next as LeadStatus);
            if (res.ok) {
              toast.success(res.message ?? "Статус обновлён");
              router.refresh();
            } else {
              setValue(prev);
              toast.error(res.error);
            }
          });
        }}
      >
        <SelectTrigger className="h-11 min-w-56" aria-label="Статус заявки">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {LEAD_STATUS_ORDER.map((s) => (
            <SelectItem key={s} value={s}>{LEAD_STATUS_LABELS[s]}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {pending && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
    </div>
  );
}

export function LeadCommentForm({ leadId }: { leadId: string }) {
  const [text, setText] = useState("");
  const [pending, start] = useTransition();
  const router = useRouter();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const res = await addLeadCommentAction(leadId, text);
          if (res.ok) {
            setText("");
            toast.success(res.message ?? "Сохранено");
            router.refresh();
          } else toast.error(res.error);
        });
      }}
      className="space-y-3"
    >
      <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Итог звонка, договорённости, следующий шаг…" rows={3} maxLength={2000} aria-label="Комментарий менеджера" />
      <Button type="submit" disabled={pending || !text.trim()}>
        {pending && <Loader2 className="animate-spin" />}
        Добавить комментарий
      </Button>
    </form>
  );
}

export function DeleteLeadButton({ leadId }: { leadId: string }) {
  const [pending, start] = useTransition();
  const router = useRouter();
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" className="text-destructive hover:bg-destructive/10">
          <Trash2 />
          Удалить
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Удалить заявку?</DialogTitle>
          <DialogDescription>Заявка и вся история работы с ней будут удалены без возможности восстановления.</DialogDescription>
        </DialogHeader>
        <div className="flex justify-end gap-2">
          <DialogClose asChild><Button variant="outline">Отмена</Button></DialogClose>
          <Button
            variant="destructive"
            disabled={pending}
            onClick={() =>
              start(async () => {
                const res = await deleteLeadAction(leadId);
                if (res.ok) {
                  toast.success(res.message ?? "Удалено");
                  router.push("/admin/leads");
                } else toast.error(res.error);
              })
            }
          >
            {pending && <Loader2 className="animate-spin" />}
            Удалить
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
