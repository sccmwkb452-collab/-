import { AlertTriangle, FlaskConical, PauseCircle } from "lucide-react";
import Link from "next/link";

import { StatusBadge } from "@/components/app/status";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { dt, money } from "@/lib/format";
import { ORDER_STATUS } from "@/lib/status";
import type { Order } from "@/lib/types";

function itemsText(o: Order) {
  return o.items.map((i) => (i.quantity > 1 ? `${i.product} × ${i.quantity}` : i.product)).join(", ");
}

function Flags({ o }: { o: Order }) {
  return (
    <>
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
    </>
  );
}

function TestMark() {
  return (
    <span className="inline-flex items-center gap-0.5 text-yellow-300" title="Тестовый заказ">
      <FlaskConical className="size-3" /> тест
    </span>
  );
}

/** Compact list for dashboard cards: number + items, status, amount. */
function CompactTable({ orders }: { orders: Order[] }) {
  return (
    <Table>
      <TBody>
        {orders.map((o) => (
          <TR key={o.id}>
            <TD className="max-w-0 w-full">
              <div className="flex items-center gap-2">
                <Link href={`/orders/${o.id}`} className="font-medium whitespace-nowrap hover:text-highlight">
                  {o.number}
                </Link>
                {o.is_test && <TestMark />}
              </div>
              <p className="truncate text-xs text-muted-foreground">{itemsText(o)}</p>
            </TD>
            <TD>
              <div className="flex flex-col items-start gap-1">
                <StatusBadge map={ORDER_STATUS} value={o.status} />
                <Flags o={o} />
              </div>
            </TD>
            <TD className="text-right tabular-nums whitespace-nowrap">{money(o.total_amount)}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

export function OrderTable({ orders, compact }: { orders: Order[]; compact?: boolean }) {
  if (compact) return <CompactTable orders={orders} />;
  return (
    <Table>
      <THead>
        <TR className="hover:bg-transparent">
          <TH>Заказ</TH>
          <TH>Товар</TH>
          <TH>Статус</TH>
          <TH className="text-right">Сумма</TH>
          <TH className="text-right">Прибыль</TH>
          <TH>Создан</TH>
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
                {o.is_test && <TestMark />}
              </div>
            </TD>
            <TD className="max-w-72">
              <p className="truncate">{itemsText(o)}</p>
              {o.buyer_name && <p className="truncate text-xs text-muted-foreground">{o.buyer_name}</p>}
            </TD>
            <TD>
              <div className="flex flex-wrap items-center gap-1.5">
                <StatusBadge map={ORDER_STATUS} value={o.status} />
                <Flags o={o} />
              </div>
              {o.status_reason && <p className="mt-1 max-w-80 truncate text-xs text-muted-foreground">{o.status_reason}</p>}
            </TD>
            <TD className="text-right tabular-nums whitespace-nowrap">{money(o.total_amount)}</TD>
            <TD className="text-right tabular-nums whitespace-nowrap">
              {o.net_profit === null ? (
                <span className="text-muted-foreground">—</span>
              ) : (
                <span className={Number(o.net_profit) < 0 ? "text-red-300" : "text-green-300"}>{money(o.net_profit)}</span>
              )}
            </TD>
            <TD className="whitespace-nowrap text-muted-foreground">{dt(o.placed_at)}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
