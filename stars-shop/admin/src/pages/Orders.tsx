import type { OrderStatus } from "@starshop/shared";
import { formatDate, formatMoney, formatStars, STATUS_META } from "@starshop/shared";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Download, Search } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Button, Card, Empty, ErrorBox, Input, ModeBadge, PageTitle, Pagination, Select, Skeleton, StatusBadge, cn } from "../components/ui";
import { api, errorMessage, exportUrl } from "../lib/api";
import type { AdminOrder } from "../lib/types";

const LIMIT = 50;

export default function Orders() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const status = params.get("status") ?? "";
  const mode = params.get("mode") ?? "";
  const q = params.get("q") ?? "";
  const offset = Number(params.get("offset") ?? 0);
  const [search, setSearch] = useState(q);

  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (!("offset" in patch)) next.delete("offset");
    setParams(next, { replace: true });
  };

  const orders = useQuery({
    queryKey: ["orders", status, mode, q, offset],
    queryFn: () => {
      const s = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
      if (status) s.set("status", status);
      if (mode) s.set("mode", mode);
      if (q) s.set("q", q);
      return api<{ items: AdminOrder[]; total: number }>(`/orders?${s}`);
    },
    placeholderData: keepPreviousData,
    refetchInterval: 20_000,
  });

  return (
    <>
      <PageTitle
        title="Заказы"
        subtitle={orders.data ? `Найдено: ${orders.data.total}` : undefined}
        actions={
          <a href={exportUrl("/orders/export.csv", { status, mode, q })} download>
            <Button variant="secondary" icon={<Download className="size-4" />}>
              Экспорт CSV
            </Button>
          </a>
        }
      />
      <div className="mb-4 flex flex-wrap gap-3">
        <form
          className="relative min-w-[240px] flex-1"
          onSubmit={(e) => {
            e.preventDefault();
            set({ q: search.trim() });
          }}
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-3" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Номер заказа, Telegram ID, @username" className="pl-9" aria-label="Поиск" />
        </form>
        <Select value={status} onChange={(e) => set({ status: e.target.value })} className="w-auto min-w-[200px]" aria-label="Статус">
          <option value="">Все статусы</option>
          {(Object.keys(STATUS_META) as OrderStatus[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_META[s].label}
            </option>
          ))}
        </Select>
        <Select value={mode} onChange={(e) => set({ mode: e.target.value })} className="w-auto" aria-label="Режим">
          <option value="">Любой режим</option>
          <option value="production">Production</option>
          <option value="demo">DEMO</option>
        </Select>
      </div>
      {orders.isError && <ErrorBox text={errorMessage(orders.error)} onRetry={() => orders.refetch()} />}
      <Card className="overflow-hidden">
        {orders.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : !orders.data?.items.length ? (
          <Empty title="Заказов нет" text="Измените фильтры или дождитесь первых покупок." />
        ) : (
          <div className={cn("overflow-x-auto transition-opacity", orders.isFetching && "opacity-70")}>
            <table className="data w-full min-w-[860px]">
              <thead>
                <tr>
                  <th>Заказ</th>
                  <th>Дата</th>
                  <th>Покупатель</th>
                  <th>Получатель</th>
                  <th className="text-right">Stars</th>
                  <th className="text-right">Сумма</th>
                  <th>Оплата</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {orders.data.items.map((o) => (
                  <tr key={o.id} className="clickable" onClick={() => navigate(`/orders/${o.id}`)}>
                    <td>
                      <span className="font-semibold tabular">#{o.number}</span> <ModeBadge mode={o.mode} />
                    </td>
                    <td className="whitespace-nowrap text-text-2">{formatDate(o.created_at)}</td>
                    <td>{o.user ? (o.user.username ? `@${o.user.username}` : o.user.telegram_id) : "—"}</td>
                    <td className="text-text-2">{o.recipient.type === "self" ? "себе" : `@${o.recipient.username}`}</td>
                    <td className="text-right tabular">{formatStars(o.stars_amount)}</td>
                    <td className="text-right font-semibold tabular">{formatMoney(o.total, o.currency)}</td>
                    <td className="text-text-2">{o.payment_method}</td>
                    <td>
                      <StatusBadge status={o.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {orders.data && <Pagination total={orders.data.total} limit={LIMIT} offset={offset} onChange={(o) => set({ offset: String(o) })} />}
      </Card>
    </>
  );
}
