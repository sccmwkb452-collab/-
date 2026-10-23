import { formatDate, formatMoney } from "@starshop/shared";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Badge, Card, Empty, ErrorBox, Input, PageTitle, Pagination, Select, Skeleton, cn } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { useShop } from "../lib/shop";
import type { AdminUserRow } from "../lib/types";

const LIMIT = 50;

export default function Users() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { currency } = useShop();
  const q = params.get("q") ?? "";
  const blocked = params.get("blocked") ?? "";
  const offset = Number(params.get("offset") ?? 0);
  const [search, setSearch] = useState(q);
  const users = useQuery({
    queryKey: ["users", q, blocked, offset],
    queryFn: () => {
      const s = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
      if (q) s.set("q", q);
      if (blocked) s.set("blocked", blocked);
      return api<{ items: AdminUserRow[]; total: number }>(`/users?${s}`);
    },
    placeholderData: keepPreviousData,
  });
  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (!("offset" in patch)) next.delete("offset");
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageTitle title="Пользователи" subtitle={users.data ? `Всего: ${users.data.total}` : undefined} />
      <div className="mb-4 flex flex-wrap gap-3">
        <form
          className="relative min-w-[240px] flex-1"
          onSubmit={(e) => {
            e.preventDefault();
            set({ q: search.trim() });
          }}
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-3" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Telegram ID, @username, имя или реферальный код" className="pl-9" aria-label="Поиск" />
        </form>
        <Select value={blocked} onChange={(e) => set({ blocked: e.target.value })} className="w-auto" aria-label="Блокировка">
          <option value="">Все</option>
          <option value="false">Активные</option>
          <option value="true">Заблокированные</option>
        </Select>
      </div>
      {users.isError && <ErrorBox text={errorMessage(users.error)} onRetry={() => users.refetch()} />}
      <Card className="overflow-hidden">
        {users.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : !users.data?.items.length ? (
          <Empty title="Никого не нашли" />
        ) : (
          <div className={cn("overflow-x-auto", users.isFetching && "opacity-70")}>
            <table className="data w-full min-w-[760px]">
              <thead>
                <tr>
                  <th>Пользователь</th>
                  <th>Telegram ID</th>
                  <th>Первый запуск</th>
                  <th>Последний визит</th>
                  <th className="text-right">Бонусы</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {users.data.items.map((u) => (
                  <tr key={u.id} className="clickable" onClick={() => navigate(`/users/${u.id}`)}>
                    <td>
                      <div className="font-semibold">{u.display_name}</div>
                      <div className="text-[12px] text-text-3">{u.username ? `@${u.username}` : "без username"}</div>
                    </td>
                    <td className="tabular">{u.telegram_id}</td>
                    <td className="text-text-2">{formatDate(u.first_seen_at, undefined, false)}</td>
                    <td className="text-text-2">{formatDate(u.last_seen_at)}</td>
                    <td className="text-right tabular">{formatMoney(u.bonus_balance, currency)}</td>
                    <td>{u.is_blocked ? <Badge tone="danger">Заблокирован</Badge> : <Badge tone="success">Активен</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {users.data && <Pagination total={users.data.total} limit={LIMIT} offset={offset} onChange={(o) => set({ offset: String(o) })} />}
      </Card>
    </>
  );
}
