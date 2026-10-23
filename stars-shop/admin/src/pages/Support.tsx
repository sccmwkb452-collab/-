import { formatDate } from "@starshop/shared";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router";
import { Badge, Card, Empty, ErrorBox, PageTitle, Skeleton, Tabs } from "../components/ui";
import { api, errorMessage } from "../lib/api";

export const TICKET_STATUS = {
  open: { label: "Ждёт ответа", tone: "warning" as const },
  answered: { label: "Отвечено", tone: "success" as const },
  closed: { label: "Закрыто", tone: "neutral" as const },
};

type Row = { id: number; subject: string; status: keyof typeof TICKET_STATUS; last_message_at: string; order_id: string | null; user: { id: number; telegram_id: number; username: string | null; display_name: string } };

export default function Support() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const status = (params.get("status") ?? "open") as "open" | "answered" | "closed" | "all";
  const tickets = useQuery({
    queryKey: ["tickets", status],
    queryFn: () => api<{ items: Row[]; total: number }>(`/tickets${status === "all" ? "" : `?status=${status}`}`),
    placeholderData: keepPreviousData,
    refetchInterval: 20_000,
  });
  return (
    <>
      <PageTitle title="Поддержка" subtitle="Ответы уходят пользователю в чат с ботом." />
      <div className="mb-4">
        <Tabs
          value={status}
          onChange={(v) => setParams({ status: v }, { replace: true })}
          items={[
            { id: "open", label: "Ждут ответа" },
            { id: "answered", label: "Отвечено" },
            { id: "closed", label: "Закрыто" },
            { id: "all", label: "Все" },
          ]}
        />
      </div>
      {tickets.isError && <ErrorBox text={errorMessage(tickets.error)} />}
      <Card className="overflow-hidden">
        {tickets.isPending ? (
          <Skeleton className="m-4 h-32" />
        ) : !tickets.data?.items.length ? (
          <Empty title="Обращений нет" text="Здесь появятся вопросы пользователей из бота и мини-приложения." />
        ) : (
          <table className="data w-full">
            <thead>
              <tr>
                <th>Обращение</th>
                <th>Пользователь</th>
                <th>Последнее сообщение</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {tickets.data.items.map((t) => (
                <tr key={t.id} className="clickable" onClick={() => navigate(`/support/${t.id}`)}>
                  <td>
                    <div className="font-semibold">#{t.id} · {t.subject}</div>
                    {t.order_id && <div className="text-[12px] text-text-3">по заказу</div>}
                  </td>
                  <td>{t.user.username ? `@${t.user.username}` : t.user.display_name}</td>
                  <td className="text-text-2">{formatDate(t.last_message_at)}</td>
                  <td>
                    <Badge tone={TICKET_STATUS[t.status].tone}>{TICKET_STATUS[t.status].label}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
