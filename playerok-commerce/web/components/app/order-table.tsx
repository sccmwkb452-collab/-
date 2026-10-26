import { AlertTriangle, FlaskConical, PauseCircle } from "lucide-react";
import Link from "next/link";

import { StatusBadge } from "@/components/app/status";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { dt, money } from "@/lib/format";
import { ORDER_STATUS } from "@/lib/status";
import type { Order } from "@/lib/types";

export function OrderTable({ orders, compact }: { orders: Order[]; compact?: boolean }) {
  return (
    <Table>
      <THead>
        <TR className="hover:bg-transparent">
          <TH>Заказ</TH>
          <TH>Товар</TH>
          <TH>Статус</TH>
          <TH className="text-right">Сумма</TH>
          {!compact && <TH className="text-right">Прибыль</TH>}
          {!compact && <TH>Создан</TH>}
        </TR>
      </THead>
      <TBody>
        {orders.map((o) => (
          <TR key={o.id}>
            <TD className="whitespace-nowrap">
              <Link href={`/orders/${o.id}`} className="font-medium text-foreground hover:text-highlight">
                {o.number}
              </Link>
              <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                {o.external_id && <span>PlayerOK {o.external_id}</span>}
                {o.is_test && (
                  <span className="inline-flex items-center gap-0.5 text-yellow-300" title="Тестовый заказ">
                    <FlaskConical className="size-3" /> тест
                  </span>
                )}
              </div>
            </TD>
            <TD className="max-w-72">
              <p className="truncate">{o.items.map((i) => (i.quantity > 1 ? `${i.product} × ${i.quantity}` : i.product)).join(", ")}</p>
              {o.buyer_name && <p className="truncate text-xs text-muted-foreground">{o.buyer_name}</p>}
            </TD>
            <TD>
              <div className="flex flex-wrap items-center gap-1.5">
                <StatusBadge map={ORDER_STATUS} value={o.status} />
                {o.needs_attention && (
                  <span className="inline-flex items-center gap-1 text-xs text-yellow-300" title={o.status_reason ?? ""}>
                    <AlertTriangle className="size-3.5" /> внимание
                  </span>
                )}
                {o.automation_paused && (
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <PauseCircle className="size-3.5" /> пауза
                  </span>
                )}
              </div>
              {o.status_reason && !compact && <p className="mt-1 max-w-80 truncate text-xs text-muted-foreground">{o.status_reason}</p>}
            </TD>
            <TD className="text-right tabular-nums whitespace-nowrap">{money(o.total_amount)}</TD>
            {!compact && (
              <TD className="text-right tabular-nums whitespace-nowrap">
                {o.net_profit === null ? <span className="text-muted-foreground">—</span> : (
                  <span className={Number(o.net_profit) < 0 ? "text-red-300" : "text-green-300"}>{money(o.net_profit)}</span>
                )}
              </TD>
            )}
            {!compact && <TD className="whitespace-nowrap text-muted-foreground">{dt(o.placed_at)}</TD>}
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
