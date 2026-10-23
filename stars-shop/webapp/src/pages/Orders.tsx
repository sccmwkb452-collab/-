import type { OrderFilter } from "@starshop/shared";
import { ORDER_FILTERS } from "@starshop/shared";
import { ReceiptText } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Page, PageHeader } from "../components/Layout";
import { OrderRow } from "../components/home/Sections";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Segmented } from "../components/ui/Segmented";
import { Skeleton } from "../components/ui/Skeleton";
import { EmptyState, ErrorState } from "../components/ui/States";
import { canAuthenticate, errorMessage } from "../lib/api";
import { useOrders } from "../lib/queries";

const EMPTY: Record<OrderFilter, string> = {
  all: "Здесь появятся ваши заказы. Начните с любого пакета звёзд.",
  pending: "Нет заказов, ожидающих оплаты.",
  processing: "Сейчас нет заказов в обработке.",
  completed: "Выполненных заказов пока нет.",
  closed: "Нет отменённых заказов и возвратов.",
};

export function Orders() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const filter = (ORDER_FILTERS.find((f) => f.id === params.get("status"))?.id ?? "all") as OrderFilter;
  const [limit, setLimit] = useState(20);
  const orders = useOrders(filter, limit, canAuthenticate);

  // Deep link from the bot: ?number=7KQ2M9XD
  const number = params.get("number");
  useEffect(() => {
    if (!number || !orders.data) return;
    const match = orders.data.items.find((o) => o.number === number.toUpperCase());
    if (match) navigate(`/orders/${match.id}`, { replace: true });
  }, [number, orders.data, navigate]);

  return (
    <>
      <PageHeader title="Мои заказы" subtitle={orders.data ? `Всего: ${orders.data.total}` : undefined} />
      <Page className="space-y-4">
        <Segmented
          label="Фильтр заказов"
          scrollable
          value={filter}
          options={ORDER_FILTERS}
          onChange={(v) => {
            setLimit(20);
            setParams(v === "all" ? {} : { status: v }, { replace: true });
          }}
        />
        {orders.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-[72px] rounded-[22px]" />
            ))}
          </div>
        ) : orders.isError ? (
          <ErrorState text={errorMessage(orders.error)} onRetry={() => orders.refetch()} />
        ) : orders.data.items.length === 0 ? (
          <EmptyState
            icon={<ReceiptText className="size-7 text-accent" />}
            title={filter === "all" ? "Заказов пока нет" : "Ничего не найдено"}
            text={EMPTY[filter]}
            action={filter === "all" && <Button onClick={() => navigate("/catalog")}>Выбрать пакет</Button>}
          />
        ) : (
          <>
            <Card className="divide-y divide-line overflow-hidden">
              {orders.data.items.map((o) => (
                <OrderRow key={o.id} order={o} />
              ))}
            </Card>
            {orders.data.total > orders.data.items.length && (
              <Button variant="secondary" block loading={orders.isFetching} onClick={() => setLimit((l) => l + 20)}>
                Показать ещё
              </Button>
            )}
          </>
        )}
      </Page>
    </>
  );
}
