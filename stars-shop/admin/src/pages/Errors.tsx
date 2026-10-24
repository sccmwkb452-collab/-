import { formatDate } from "@starshop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bug, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Badge, Button, Card, Empty, ErrorBox, PageTitle, Pagination, Skeleton, Tabs, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { can, useAdmin } from "../lib/auth";

interface ErrorItem {
  id: number;
  source: string;
  message: string;
  path: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

const SOURCES = [
  { id: "", label: "Все" },
  { id: "api", label: "API" },
  { id: "bot", label: "Бот" },
  { id: "client", label: "Mini App" },
  { id: "worker", label: "Фоновые задачи" },
];
const SOURCE_LABEL: Record<string, string> = { api: "API", bot: "Бот", client: "Mini App", worker: "Задачи" };
const LIMIT = 50;

export default function Errors() {
  const admin = useAdmin();
  const qc = useQueryClient();
  const toast = useToast();
  const [source, setSource] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const data = useQuery({
    queryKey: ["errors", source, offset],
    queryFn: () =>
      api<{ items: ErrorItem[]; total: number; problems: Record<string, number> }>(
        `/errors?limit=${LIMIT}&offset=${offset}${source ? `&source=${source}` : ""}`,
      ),
    refetchInterval: 30_000,
  });
  const clear = useMutation({
    mutationFn: () => api<{ removed: number }>("/errors", { method: "DELETE" }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["errors"] });
      toast(`Удалено записей: ${r.removed}`, "success");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const p = data.data?.problems;

  return (
    <>
      <PageTitle
        title="Ошибки"
        subtitle="Сбои API, бота, фоновых задач и Mini App у покупателей. Секреты и токены в записи не попадают."
        actions={
          can(admin, "owner") && (
            <Button variant="danger" icon={<Trash2 className="size-4" />} loading={clear.isPending} onClick={() => window.confirm("Очистить журнал ошибок?") && clear.mutate()}>
              Очистить
            </Button>
          )
        }
      />
      {p && (
        <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Link to="/orders?status=failed">
            <Card className="p-4 transition hover:ring-line-strong">
              <div className="text-[12.5px] font-semibold text-text-3">Заказы с ошибкой выполнения</div>
              <div className={`mt-1 text-[22px] font-semibold ${p.failed_orders ? "text-danger" : ""}`}>{p.failed_orders}</div>
            </Card>
          </Link>
          <Card className="p-4">
            <div className="text-[12.5px] font-semibold text-text-3">Доставки ждут оператора</div>
            <div className={`mt-1 text-[22px] font-semibold ${p.deliveries_need_attention ? "text-warning" : ""}`}>{p.deliveries_need_attention}</div>
          </Card>
          <Card className="p-4">
            <div className="text-[12.5px] font-semibold text-text-3">Неотправленные уведомления</div>
            <div className="mt-1 text-[22px] font-semibold">{p.failed_notifications}</div>
          </Card>
        </div>
      )}
      <div className="mb-4">
        <Tabs
          value={source}
          onChange={(v) => {
            setSource(v);
            setOffset(0);
          }}
          items={SOURCES}
        />
      </div>
      {data.isError && <ErrorBox text={errorMessage(data.error)} onRetry={() => data.refetch()} />}
      <Card className="overflow-hidden">
        {data.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : !data.data?.items.length ? (
          <Empty title="Ошибок нет" text="Здесь появятся сбои, если они случатся." icon={<Bug className="size-6" />} />
        ) : (
          <ul className="divide-y divide-line">
            {data.data.items.map((e) => (
              <li key={e.id}>
                <button type="button" onClick={() => setOpen(open === e.id ? null : e.id)} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-surface-2/60">
                  <Badge tone={e.source === "client" ? "info" : "danger"}>{SOURCE_LABEL[e.source] ?? e.source}</Badge>
                  <span className="min-w-0 flex-1">
                    <span className="block break-words text-[13px] font-semibold">{e.message}</span>
                    <span className="block text-[12px] text-text-3">
                      {formatDate(e.created_at)}
                      {e.path ? ` · ${e.path}` : ""}
                    </span>
                  </span>
                </button>
                {open === e.id && e.details && (
                  <pre className="mx-4 mb-3 max-h-64 overflow-auto rounded-xl bg-surface-2 p-3 text-[11.5px] leading-relaxed text-text-2">
                    {JSON.stringify(e.details, null, 2)}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {data.data && data.data.total > LIMIT && <Pagination total={data.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
    </>
  );
}
