import { formatDate } from "@starshop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Send } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Badge, Button, Card, ErrorBox, Skeleton, Textarea, cn, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import type { AdminUserRow } from "../lib/types";
import { TICKET_STATUS } from "./Support";

type Ticket = {
  id: number;
  subject: string;
  status: keyof typeof TICKET_STATUS;
  order_id: string | null;
  user: AdminUserRow | null;
  messages: { id: number; author: string; text: string; at: string }[];
};

export default function TicketPage() {
  const { id = "" } = useParams();
  const toast = useToast();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const ticket = useQuery({ queryKey: ["ticket", id], queryFn: () => api<Ticket>(`/tickets/${id}`), refetchInterval: 15_000 });
  const reply = useMutation({
    mutationFn: () => api<Ticket>(`/tickets/${id}/reply`, { method: "POST", body: { text } }),
    onSuccess: (t) => {
      qc.setQueryData(["ticket", id], t);
      qc.invalidateQueries({ queryKey: ["tickets"] });
      setText("");
      toast("Ответ отправлен пользователю");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const close = useMutation({
    mutationFn: () => api<Ticket>(`/tickets/${id}/close`, { method: "POST" }),
    onSuccess: (t) => {
      qc.setQueryData(["ticket", id], t);
      qc.invalidateQueries({ queryKey: ["tickets"] });
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (ticket.isPending) return <Skeleton className="h-96" />;
  if (ticket.isError || !ticket.data) return <ErrorBox text={errorMessage(ticket.error)} />;
  const t = ticket.data;
  return (
    <>
      <Link to="/support" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-semibold text-text-3 hover:text-text">
        <ArrowLeft className="size-4" /> Обращения
      </Link>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="font-display text-[22px] font-semibold tracking-[-0.03em]">
          #{t.id} · {t.subject}
        </h1>
        <Badge tone={TICKET_STATUS[t.status].tone}>{TICKET_STATUS[t.status].label}</Badge>
        {t.status !== "closed" && (
          <Button size="sm" variant="secondary" loading={close.isPending} onClick={() => close.mutate()}>
            Закрыть обращение
          </Button>
        )}
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <div className="space-y-3">
            {t.messages.map((m) => (
              <div key={m.id} className={cn("flex", m.author === "admin" ? "justify-end" : "justify-start")}>
                <div className={cn("max-w-[80%] rounded-2xl px-4 py-3", m.author === "admin" ? "bg-accent text-white" : "bg-surface-2 ring-1 ring-line")}>
                  <p className="whitespace-pre-wrap text-[14px] leading-relaxed">{m.text}</p>
                  <div className={cn("mt-1 text-[11px]", m.author === "admin" ? "text-white/70" : "text-text-3")}>
                    {m.author === "admin" ? "Поддержка" : "Пользователь"} · {formatDate(m.at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-5 space-y-2 border-t border-line pt-5">
            <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Ответ пользователю" rows={4} maxLength={4000} />
            <div className="flex justify-between gap-3">
              <p className="text-[12px] text-text-3">Никогда не просите пароль или код входа.</p>
              <Button icon={<Send className="size-4" />} disabled={!text.trim()} loading={reply.isPending} onClick={() => reply.mutate()}>
                Отправить
              </Button>
            </div>
          </div>
        </Card>
        <Card title="Пользователь">
          {t.user ? (
            <div className="space-y-2 p-5 text-[13.5px]">
              <Link className="font-semibold text-accent" to={`/users/${t.user.id}`}>
                {t.user.display_name}
              </Link>
              <div className="text-text-2">{t.user.username ? `@${t.user.username}` : "без username"}</div>
              <div className="text-text-3">Telegram ID: {t.user.telegram_id}</div>
              {t.order_id && (
                <Link className="block font-semibold text-accent" to={`/orders/${t.order_id}`}>
                  Открыть заказ →
                </Link>
              )}
            </div>
          ) : (
            <p className="p-5 text-text-3">—</p>
          )}
        </Card>
      </div>
    </>
  );
}
