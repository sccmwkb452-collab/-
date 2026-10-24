import { formatDate, formatMoney } from "@starshop/shared";
import { useQuery } from "@tanstack/react-query";
import { Settings } from "lucide-react";
import { Link } from "react-router";
import { Badge, Button, Card, Empty, ErrorBox, PageTitle, Skeleton } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { useShop } from "../lib/shop";

const STATUS: Record<string, { label: string; tone: "warning" | "success" | "danger" | "neutral" }> = {
  pending: { label: "Ждёт заказа", tone: "warning" },
  rewarded: { label: "Начислено", tone: "success" },
  rejected: { label: "Отклонено", tone: "danger" },
  reversed: { label: "Отменено (возврат)", tone: "neutral" },
};

const REASONS: Record<string, string> = {
  gift_to_referrer: "подарок пригласившему",
  referrer_unavailable: "пригласивший заблокирован",
  referrer_limit_reached: "лимит наград",
};

export default function Referrals() {
  const { currency } = useShop();
  const data = useQuery({
    queryKey: ["referrals"],
    queryFn: () =>
      api<{
        summary: { by_status: Record<string, number>; rewards_total: string };
        items: { id: number; referrer_id: number; referred_id: number; status: string; reject_reason: string | null; reward_amount: string | null; qualifying_order_id: string | null; created_at: string }[];
      }>("/referrals"),
  });
  return (
    <>
      <PageTitle
        title="Реферальная программа"
        subtitle="Награда начисляется только после оплаченного и выполненного первого заказа приглашённого (только PRODUCTION)."
        actions={
          <Link to="/settings?tab=referral">
            <Button variant="secondary" icon={<Settings className="size-4" />}>
              Настройки программы
            </Button>
          </Link>
        }
      />
      {data.isError && <ErrorBox text={errorMessage(data.error)} />}
      {data.data && (
        <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
          {Object.entries(STATUS).map(([k, v]) => (
            <Card key={k} className="p-4">
              <div className="text-[12.5px] font-semibold text-text-3">{v.label}</div>
              <div className="mt-1 text-[22px] font-semibold">{data.data.summary.by_status[k] ?? 0}</div>
            </Card>
          ))}
          <Card className="p-4">
            <div className="text-[12.5px] font-semibold text-text-3">Начислено бонусов</div>
            <div className="mt-1 text-[22px] font-semibold">{formatMoney(data.data.summary.rewards_total, currency)}</div>
          </Card>
        </div>
      )}
      <Card className="overflow-hidden">
        {data.isPending ? (
          <Skeleton className="m-4 h-32" />
        ) : !data.data?.items.length ? (
          <Empty title="Приглашений пока нет" />
        ) : (
          <div className="overflow-x-auto">
            <table className="data w-full min-w-[700px]">
              <thead>
                <tr>
                  <th>Пригласил</th>
                  <th>Приглашённый</th>
                  <th>Статус</th>
                  <th className="text-right">Награда</th>
                  <th>Дата</th>
                </tr>
              </thead>
              <tbody>
                {data.data.items.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link className="text-accent" to={`/users/${r.referrer_id}`}>
                        #{r.referrer_id}
                      </Link>
                    </td>
                    <td>
                      <Link className="text-accent" to={`/users/${r.referred_id}`}>
                        #{r.referred_id}
                      </Link>
                    </td>
                    <td>
                      <Badge tone={STATUS[r.status]?.tone ?? "neutral"}>{STATUS[r.status]?.label ?? r.status}</Badge>
                      {r.reject_reason && <span className="ml-2 text-[12px] text-text-3">{REASONS[r.reject_reason] ?? r.reject_reason}</span>}
                    </td>
                    <td className="text-right tabular">{r.reward_amount ? formatMoney(r.reward_amount, currency) : "—"}</td>
                    <td className="text-text-2">{formatDate(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <BonusLedger />
    </>
  );
}

const KINDS: Record<string, string> = {
  referral_reward: "Награда за реферала",
  referral_reversal: "Отмена награды",
  order_spend: "Оплата заказа",
  order_return: "Возврат бонусов",
  admin_adjustment: "Корректировка",
};

function BonusLedger() {
  const { currency } = useShop();
  const ledger = useQuery({
    queryKey: ["bonus-transactions"],
    queryFn: () =>
      api<{
        items: { id: number; user: { id: number; username: string | null; display_name: string }; kind: string; amount: string; comment: string | null; created_at: string }[];
        total: number;
      }>("/bonus-transactions?limit=50"),
  });
  return (
    <Card className="mt-6 overflow-hidden" title="История начислений бонусов">
      {ledger.isError && <ErrorBox text={errorMessage(ledger.error)} onRetry={() => ledger.refetch()} />}
      {ledger.isPending ? (
        <div className="p-4">
          <Skeleton className="h-24 w-full" />
        </div>
      ) : !ledger.data?.items.length ? (
        <Empty title="Начислений пока нет" text="Бонусы появляются после выполненных реальных заказов приглашённых." />
      ) : (
        <div className="overflow-x-auto">
          <table className="data w-full min-w-[640px]">
            <thead>
              <tr>
                <th>Пользователь</th>
                <th>Операция</th>
                <th className="text-right">Сумма</th>
                <th>Дата</th>
              </tr>
            </thead>
            <tbody>
              {ledger.data.items.map((t) => (
                <tr key={t.id}>
                  <td>
                    <Link className="text-accent" to={`/users/${t.user.id}`}>
                      {t.user.username ? `@${t.user.username}` : t.user.display_name}
                    </Link>
                  </td>
                  <td>
                    {KINDS[t.kind] ?? t.kind}
                    {t.comment && <span className="block text-[12px] text-text-3">{t.comment}</span>}
                  </td>
                  <td className={`text-right tabular ${Number(t.amount) > 0 ? "text-success" : "text-danger"}`}>
                    {Number(t.amount) > 0 ? "+" : ""}
                    {formatMoney(t.amount, currency)}
                  </td>
                  <td className="text-text-2">{formatDate(t.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
