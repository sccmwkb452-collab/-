import type { Ticket } from "@starshop/shared";
import { formatDate } from "@starshop/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Lock, MessageCircle, Send } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { useBoot } from "../components/BootContext";
import { Page, PageHeader } from "../components/Layout";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Skeleton } from "../components/ui/Skeleton";
import { EmptyState, ErrorState } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { cn } from "../components/ui/cn";
import { api, canAuthenticate, errorMessage } from "../lib/api";
import { keys, useTicket, useTickets } from "../lib/queries";
import { openExternal } from "../lib/telegram";

const TICKET_STATUS = {
  open: { label: "Открыто", tone: "warning" as const },
  answered: { label: "Есть ответ", tone: "success" as const },
  closed: { label: "Закрыто", tone: "neutral" as const },
};

function Composer({ placeholder, onSend, loading }: { placeholder: string; onSend: (text: string) => Promise<unknown>; loading: boolean }) {
  const [text, setText] = useState("");
  return (
    <form
      className="rounded-[22px] bg-surface p-2 ring-1 ring-inset ring-line focus-within:ring-2 focus-within:ring-accent"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!text.trim() || loading) return;
        try {
          await onSend(text.trim());
          setText("");
        } catch {
          /* toast shown by caller */
        }
      }}
    >
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder}
        rows={4}
        maxLength={4000}
        className="w-full resize-none bg-transparent px-3 py-2 text-[15px] leading-relaxed outline-none placeholder:text-text-3"
        aria-label="Сообщение"
      />
      <div className="flex items-center justify-between gap-2 px-2 pb-1">
        <span className="flex items-center gap-1 text-[11.5px] text-text-3">
          <Lock className="size-3" /> Не отправляйте пароли и коды
        </span>
        <Button size="sm" type="submit" loading={loading} disabled={!text.trim()} icon={<Send className="size-4" />}>
          Отправить
        </Button>
      </div>
    </form>
  );
}

export function Support() {
  const boot = useBoot();
  const tickets = useTickets();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const orderId = params.get("order");
  const create = useMutation({
    mutationFn: (text: string) => api<Ticket>("/support/tickets", { method: "POST", body: { text, order_id: orderId } }),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: keys.tickets });
      toast("Обращение отправлено. Ответ придёт в чат с ботом", "success");
      navigate(`/support/${t.id}`, { replace: true });
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const s = boot.content.support;

  return (
    <>
      <PageHeader title="Поддержка" subtitle={s.response_time} />
      <Page className="space-y-4">
        <Card className="p-5">
          <div className="flex items-start gap-3">
            <MessageCircle className="mt-0.5 size-5 text-accent" />
            <div className="text-[13.5px] leading-relaxed text-text-2">
              <b className="text-text">{s.hours}.</b> Опишите вопрос — ответ придёт сюда и в чат с ботом.
              {orderId && " Мы приложим к обращению номер заказа."}
            </div>
          </div>
          {(s.telegram || s.email) && (
            <div className="mt-4 flex flex-wrap gap-2">
              {s.telegram && (
                <Button size="sm" variant="secondary" onClick={() => openExternal(`https://t.me/${s.telegram.replace(/^@/, "")}`)}>
                  @{s.telegram.replace(/^@/, "")}
                </Button>
              )}
              {s.email && (
                <Button size="sm" variant="secondary" onClick={() => openExternal(`mailto:${s.email}`)}>
                  {s.email}
                </Button>
              )}
            </div>
          )}
        </Card>

        {canAuthenticate ? (
          <Composer placeholder={orderId ? "Что случилось с заказом?" : "Ваш вопрос"} onSend={(t) => create.mutateAsync(t)} loading={create.isPending} />
        ) : (
          <EmptyState icon={<Lock className="size-7 text-accent" />} title="Откройте магазин в Telegram" text="Обращения доступны в мини-приложении." />
        )}

        {tickets.isPending && canAuthenticate ? (
          <Skeleton className="h-[120px] rounded-[24px]" />
        ) : tickets.data && tickets.data.items.length > 0 ? (
          <Card className="divide-y divide-line overflow-hidden">
            {tickets.data.items.map((t) => (
              <button key={t.id} onClick={() => navigate(`/support/${t.id}`)} className="flex w-full items-center gap-3 px-4 py-3.5 text-left hover:bg-surface-2/60">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14.5px] font-semibold">{t.subject}</span>
                  <span className="text-[12px] text-text-3">
                    #{t.id} · {formatDate(t.last_message_at, boot.timezone)}
                  </span>
                </span>
                <Badge tone={TICKET_STATUS[t.status].tone}>{TICKET_STATUS[t.status].label}</Badge>
                <ChevronRight className="size-4 text-text-3" />
              </button>
            ))}
          </Card>
        ) : null}
      </Page>
    </>
  );
}

export function TicketPage() {
  const { id = "0" } = useParams();
  const boot = useBoot();
  const ticket = useTicket(Number(id));
  const qc = useQueryClient();
  const toast = useToast();
  const send = useMutation({
    mutationFn: (text: string) => api<Ticket>(`/support/tickets/${id}/messages`, { method: "POST", body: { text } }),
    onSuccess: (t) => qc.setQueryData(keys.ticket(Number(id)), t),
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <>
      <PageHeader title={`Обращение #${id}`} subtitle={ticket.data?.subject} right={ticket.data && <Badge tone={TICKET_STATUS[ticket.data.status].tone}>{TICKET_STATUS[ticket.data.status].label}</Badge>} />
      <Page className="space-y-4">
        {ticket.isPending ? (
          <Skeleton className="h-[200px] rounded-[24px]" />
        ) : ticket.isError || !ticket.data ? (
          <ErrorState text={errorMessage(ticket.error)} onRetry={() => ticket.refetch()} />
        ) : (
          <>
            <div className="space-y-3">
              {ticket.data.messages?.map((m) => (
                <div key={m.id} className={cn("flex", m.author === "user" ? "justify-end" : "justify-start")}>
                  <div className={cn("max-w-[85%] rounded-[22px] px-4 py-3", m.author === "user" ? "rounded-br-md bg-accent-gradient text-white" : "rounded-bl-md bg-surface ring-1 ring-line")}>
                    {m.author !== "user" && <div className="mb-1 text-[12px] font-semibold text-accent">Поддержка</div>}
                    <p className="whitespace-pre-wrap text-[14.5px] leading-relaxed">{m.text}</p>
                    <div className={cn("mt-1 text-right text-[11px]", m.author === "user" ? "text-white/70" : "text-text-3")}>{formatDate(m.at, boot.timezone)}</div>
                  </div>
                </div>
              ))}
            </div>
            {ticket.data.status === "closed" ? (
              <p className="text-center text-[13px] text-text-3">Обращение закрыто. Если вопрос остался — создайте новое.</p>
            ) : (
              <Composer placeholder="Ответить" onSend={(t) => send.mutateAsync(t)} loading={send.isPending} />
            )}
          </>
        )}
      </Page>
    </>
  );
}
