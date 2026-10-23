import { formatDate } from "@starshop/shared";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link } from "react-router";
import { Card, Empty, ErrorBox, Input, PageTitle, Pagination, Select, Skeleton } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import type { AuditRow } from "../lib/types";

const LIMIT = 100;
const LINKS: Record<string, string> = { order: "/orders/", user: "/users/", ticket: "/support/" };

export default function Audit() {
  const [entity, setEntity] = useState("");
  const [action, setAction] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const log = useQuery({
    queryKey: ["audit", entity, action, offset],
    queryFn: () => {
      const s = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
      if (entity) s.set("entity_type", entity);
      if (action) s.set("action", action);
      return api<{ items: AuditRow[]; total: number }>(`/audit?${s}`);
    },
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <PageTitle title="Журнал действий" subtitle="Все изменения, сделанные сотрудниками: кто, что и когда." />
      <div className="mb-4 flex flex-wrap gap-3">
        <Select value={entity} onChange={(e) => (setEntity(e.target.value), setOffset(0))} className="w-auto" aria-label="Объект">
          <option value="">Все объекты</option>
          <option value="order">Заказы</option>
          <option value="product">Каталог</option>
          <option value="user">Пользователи</option>
          <option value="promo">Промокоды</option>
          <option value="settings">Настройки</option>
          <option value="admin">Администраторы</option>
          <option value="ticket">Поддержка</option>
        </Select>
        <Input value={action} onChange={(e) => (setAction(e.target.value), setOffset(0))} placeholder="Действие, например order.refund" className="max-w-[320px]" />
      </div>
      {log.isError && <ErrorBox text={errorMessage(log.error)} />}
      <Card className="overflow-hidden">
        {log.isPending ? (
          <Skeleton className="m-4 h-40" />
        ) : !log.data?.items.length ? (
          <Empty title="Записей нет" />
        ) : (
          <div className="overflow-x-auto">
            <table className="data w-full min-w-[760px]">
              <thead>
                <tr>
                  <th>Когда</th>
                  <th>Кто</th>
                  <th>Действие</th>
                  <th>Объект</th>
                  <th>Описание</th>
                </tr>
              </thead>
              <tbody>
                {log.data.items.map((r) => (
                  <Fragment key={r.id}>
                    <tr className="clickable" onClick={() => setOpen(open === r.id ? null : r.id)}>
                      <td className="whitespace-nowrap text-text-2">{formatDate(r.at)}</td>
                      <td>admin #{r.admin_id ?? "—"}</td>
                      <td className="font-mono text-[12.5px]">{r.action}</td>
                      <td>
                        {r.entity_type && LINKS[r.entity_type] && r.entity_id ? (
                          <Link className="text-accent" to={`${LINKS[r.entity_type]}${r.entity_id}`} onClick={(e) => e.stopPropagation()}>
                            {r.entity_type} {r.entity_id.slice(0, 8)}
                          </Link>
                        ) : (
                          <span className="text-text-2">
                            {r.entity_type} {r.entity_id}
                          </span>
                        )}
                      </td>
                      <td className="max-w-[320px] truncate text-text-2">{r.summary}</td>
                    </tr>
                    {open === r.id && (
                      <tr>
                        <td colSpan={5}>
                          <div className="grid gap-3 md:grid-cols-2">
                            <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 text-[11px]">до: {JSON.stringify(r.before, null, 1)}</pre>
                            <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 text-[11px]">после: {JSON.stringify(r.after, null, 1)}</pre>
                          </div>
                          <div className="mt-2 text-[11.5px] text-text-3">IP: {r.ip ?? "—"}</div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {log.data && <Pagination total={log.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
      </Card>
    </>
  );
}
