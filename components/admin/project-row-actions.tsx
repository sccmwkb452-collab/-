"use client";

import { Eye, EyeOff, Loader2, MoreHorizontal, Pencil, Send, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { deleteProjectAction, setProjectStatusAction } from "@/lib/actions/projects";

interface Props {
  id: string;
  slug: string;
  title: string;
  status: "DRAFT" | "PUBLISHED" | "HIDDEN";
  redirectAfterDelete?: boolean;
}

export function ProjectRowActions({ id, slug, title, status, redirectAfterDelete }: Props) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [confirm, setConfirm] = useState(false);

  const setStatus = (next: Props["status"]) =>
    start(async () => {
      const res = await setProjectStatusAction(id, next);
      if (res.ok) {
        toast.success(res.message ?? "Готово");
        router.refresh();
      } else toast.error(res.error);
    });

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={`Действия: ${title}`} disabled={pending}>
            {pending ? <Loader2 className="animate-spin" /> : <MoreHorizontal />}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem asChild><Link href={`/admin/projects/${id}`}><Pencil />Редактировать</Link></DropdownMenuItem>
          {status === "PUBLISHED" && <DropdownMenuItem asChild><Link href={`/projects/${slug}`} target="_blank"><Eye />Открыть на сайте</Link></DropdownMenuItem>}
          <DropdownMenuSeparator />
          {status !== "PUBLISHED" && <DropdownMenuItem onSelect={() => setStatus("PUBLISHED")}><Send />Опубликовать</DropdownMenuItem>}
          {status === "PUBLISHED" && <DropdownMenuItem onSelect={() => setStatus("HIDDEN")}><EyeOff />Скрыть</DropdownMenuItem>}
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-destructive focus:bg-destructive/10" onSelect={() => setConfirm(true)}><Trash2 />Удалить</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Удалить «{title}»?</DialogTitle>
            <DialogDescription>Проект и все его изображения будут удалены. Заявки по проекту сохранятся. Чтобы убрать проект с сайта без удаления, используйте «Скрыть».</DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <DialogClose asChild><Button variant="outline">Отмена</Button></DialogClose>
            <Button
              variant="destructive"
              disabled={pending}
              onClick={() =>
                start(async () => {
                  const res = await deleteProjectAction(id);
                  if (res.ok) {
                    toast.success(res.message ?? "Удалено");
                    setConfirm(false);
                    if (redirectAfterDelete) router.push("/admin/projects");
                    else router.refresh();
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
    </>
  );
}
