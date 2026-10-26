"use client";

import { ExternalLink, Store } from "lucide-react";
import Link from "next/link";

import { Async, Empty, Notice, PageHeader } from "@/components/app/blocks";
import { StatusBadge } from "@/components/app/status";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { useApi } from "@/lib/api";
import { ago, money, num } from "@/lib/format";
import { PURCHASE_MODE, SUPPLIER_STATUS } from "@/lib/status";
import type { Supplier } from "@/lib/types";

const CAPABILITY_LABELS: Record<string, string> = {
  price_list: "Прайс-лист",
  balance: "Баланс",
  purchase: "Закупка через API",
  order_status: "Статус заказа",
  returns_codes: "Возвращает коды",
  reconcile_by_key: "Сверка по ключу",
};

export default function SuppliersPage() {
  const state = useApi<{ items: Supplier[] }>("/suppliers");
  return (
    <>
      <PageHeader
        title="Поставщики"
        description="Подключение, режим закупки, лимиты и каталог. Каждый поставщик проверен на допустимость метода интеграции — источники на его странице."
      />
      <Notice className="mb-5">
        Четыре режима закупки: <b>мониторинг цен</b>, <b>ручная закупка</b>, <b>после подтверждения</b> и <b>автоматически в лимитах</b>. Автоматический режим
        работает только при заданных лимитах, только для разрешённых товаров и только в боевом режиме. Аварийная остановка — в разделе «Безопасность».
      </Notice>
      <Async state={state} rows={6}>
        {(d) =>
          d.items.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {d.items.map((s) => (
                <Card key={s.id} className="flex flex-col">
                  <CardHeader
                    title={
                      <Link href={`/suppliers/${s.id}`} className="hover:text-highlight">
                        {s.name}
                      </Link>
                    }
                    description={s.adapter_title}
                    actions={<StatusBadge map={SUPPLIER_STATUS} value={s.status} />}
                  />
                  <CardBody className="flex flex-1 flex-col gap-4">
                    {s.status_reason && <p className="text-[13px] text-muted-foreground">{s.status_reason}</p>}
                    <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px] sm:grid-cols-3">
                      <div>
                        <p className="text-xs text-muted-foreground">Режим</p>
                        <p>{PURCHASE_MODE[s.purchase_mode]?.label ?? s.purchase_mode_label}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Позиций в каталоге</p>
                        <p className="tabular-nums">{num(s.products_count ?? 0)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Баланс</p>
                        <p className="tabular-nums">{s.balance !== null ? money(s.balance, s.balance_currency ?? s.currency) : "—"}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Потрачено сегодня</p>
                        <p className="tabular-nums">
                          {money(s.spent_today_rub)} {Number(s.daily_limit) > 0 && <span className="text-muted-foreground">из {money(s.daily_limit)}</span>}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Синхронизация</p>
                        <p>{ago(s.last_sync_at)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Успешно / ошибок</p>
                        <p className="tabular-nums">
                          {s.success_count} / <span className={s.error_count ? "text-red-300" : ""}>{s.error_count}</span>
                        </p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(s.capabilities).map(([k, v]) => (
                        <span
                          key={k}
                          className={`rounded-full border px-2 py-0.5 text-[11px] ${v ? "border-success/30 text-green-300" : "border-border text-subtle line-through"}`}
                        >
                          {CAPABILITY_LABELS[k] ?? k}
                        </span>
                      ))}
                    </div>
                    {s.last_error && <Notice tone="danger">{s.last_error}</Notice>}
                    <div className="mt-auto flex items-center justify-between pt-1 text-[13px]">
                      <Link href={`/suppliers/${s.id}`} className="text-highlight hover:underline">
                        Настроить и каталог →
                      </Link>
                      {s.website && (
                        <a href={s.website} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground">
                          сайт <ExternalLink className="size-3" />
                        </a>
                      )}
                    </div>
                  </CardBody>
                </Card>
              ))}
            </div>
          ) : (
            <Empty title="Поставщиков нет" icon={Store}>
              Запустите начальную настройку командой <code>python -m autocommerce.cli init</code>.
            </Empty>
          )
        }
      </Async>
    </>
  );
}
