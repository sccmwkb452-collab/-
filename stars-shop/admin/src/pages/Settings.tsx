import { formatDate } from "@starshop/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleX, Plus, Save, TriangleAlert } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { Badge, Button, Card, ErrorBox, Input, KV, Label, Modal, PageTitle, Select, Skeleton, Tabs, Textarea, Toggle, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { can, useAdmin } from "../lib/auth";
import type { Admin, AdminProduct, Role } from "../lib/types";

interface Integrations {
  app_env: string;
  allow_production: boolean;
  bot: { token_configured: boolean; username: string | null; mode: string; webapp_url: string };
  payments: { id: string; title: string; enabled: boolean; configured: boolean; is_demo: boolean; supports_refunds: boolean }[];
  cryptopay_network: string;
  delivery: { id: string; title: string; configured: boolean; is_demo: boolean; idempotent: boolean; min_stars: number; max_stars: number };
  redis_configured: boolean;
  currency: string;
  timezone: string;
  bootstrap_admin_ids: number[];
}

interface SettingsData {
  shop: { mode: "demo" | "production"; maintenance: boolean; maintenance_message: string; allow_gift_to_others: boolean };
  checkout: { provider_fee_percent: Record<string, string>; fee_fixed: string; min_payable: string };
  referral: { enabled: boolean; reward_kind: "percent" | "fixed"; reward_value: string; min_order_amount: string; max_bonus_spend_percent: string; max_rewards_per_referrer: number | null;
    withdrawal_enabled: boolean; withdrawal_min_stars: number; withdrawal_rate: string | null; withdrawal_auto_approve: boolean };
  lucky: {
    mode: "off" | "demo_only" | "on";
    min_chance_percent: number;
    max_chance_percent: number;
    fee_percent: string;
    daily_limit: number | null;
    min_stake_stars: number;
    prize_product_ids: number[];
  };
  bot_emoji: { enabled: boolean; ids: Record<string, string> };
  notifications: { user_notifications: boolean; admin_new_paid_order: boolean; admin_delivery_problem: boolean; admin_new_ticket: boolean };
}

type TabId = "shop" | "checkout" | "referral" | "lucky" | "emoji" | "notifications" | "admins" | "integrations" | "webhooks";
const EMOJI_KEYS: [string, string][] = [
  ["welcome", "✨ Приветствие"],
  ["shop", "🌐 Открыть магазин"],
  ["stars", "⭐️ Купить Stars"],
  ["premium", "💎 Premium"],
  ["profile", "👤 Профиль"],
  ["orders", "🧾 Мои заказы"],
  ["referrals", "🎁 Рефералы"],
  ["support", "💬 Поддержка"],
];
const ROLE: Record<Role, string> = { owner: "Владелец", manager: "Менеджер", support: "Поддержка" };

function Flag({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {ok ? <CircleCheck className="size-4 text-success" /> : <CircleX className="size-4 text-danger" />}
      {children}
    </span>
  );
}

export default function Settings() {
  const admin = useAdmin();
  const owner = can(admin, "owner");
  const toast = useToast();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") ?? "shop") as TabId;
  const data = useQuery({ queryKey: ["settings"], queryFn: () => api<{ settings: SettingsData; integrations: Integrations }>("/settings") });
  const products = useQuery({ queryKey: ["products"], queryFn: () => api<{ items: AdminProduct[] }>("/products") });
  const [draft, setDraft] = useState<SettingsData | null>(null);
  const [confirmProd, setConfirmProd] = useState(false);
  useEffect(() => {
    if (data.data) setDraft(structuredClone(data.data.settings));
  }, [data.data]);

  const save = useMutation({
    mutationFn: (key: keyof SettingsData) => api(`/settings/${key}`, { method: "PUT", body: draft![key] }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      setConfirmProd(false);
      toast("Настройки сохранены");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (data.isError) return <ErrorBox text={errorMessage(data.error)} onRetry={() => data.refetch()} />;
  if (!draft || !data.data) return <Skeleton className="h-96" />;
  const integ = data.data.integrations;
  const d = draft;
  const setD = <K extends keyof SettingsData>(k: K, patch: Partial<SettingsData[K]>) => setDraft({ ...d, [k]: { ...d[k], ...patch } });
  const saveBtn = (key: keyof SettingsData) =>
    owner ? (
      <Button
        icon={<Save className="size-4" />}
        loading={save.isPending}
        onClick={() => (key === "shop" && d.shop.mode === "production" && data.data.settings.shop.mode !== "production" ? setConfirmProd(true) : save.mutate(key))}
      >
        Сохранить
      </Button>
    ) : (
      <p className="text-[12.5px] text-text-3">Изменять может только владелец.</p>
    );

  const tabs: { id: TabId; label: string }[] = [
    { id: "shop", label: "Магазин" },
    { id: "checkout", label: "Комиссии" },
    { id: "referral", label: "Рефералы" },
    { id: "lucky", label: "Lucky Buy" },
    { id: "emoji", label: "Эмодзи бота" },
    { id: "notifications", label: "Уведомления" },
    ...(owner ? [{ id: "admins" as const, label: "Администраторы" }] : []),
    { id: "integrations", label: "Интеграции" },
    ...(can(admin, "manager") ? [{ id: "webhooks" as const, label: "Webhook-и" }] : []),
  ];

  return (
    <>
      <PageTitle title="Настройки" subtitle="Секреты (токены, ключи) задаются только в .env на сервере и здесь не отображаются." />
      <div className="mb-5">
        <Tabs value={tab} onChange={(v) => setParams({ tab: v }, { replace: true })} items={tabs} />
      </div>

      {tab === "shop" && (
        <Card className="p-5">
          <div className="max-w-[640px] space-y-5">
            <Label label="Режим работы" hint={integ.allow_production ? "PRODUCTION включает реальные платежи и доставку" : "PRODUCTION запрещён на сервере (ALLOW_PRODUCTION=false)"}>
              <Select value={d.shop.mode} onChange={(e) => setD("shop", { mode: e.target.value as "demo" | "production" })} disabled={!owner}>
                <option value="demo">DEMO — тестовые оплата и доставка</option>
                <option value="production" disabled={!integ.allow_production}>
                  PRODUCTION — реальные продажи
                </option>
              </Select>
            </Label>
            <Toggle checked={d.shop.maintenance} onChange={(v) => setD("shop", { maintenance: v })} label="Режим обслуживания" hint="Магазин показывает заглушку, новые заказы не принимаются" />
            <Label label="Сообщение на время обслуживания">
              <Textarea value={d.shop.maintenance_message} onChange={(e) => setD("shop", { maintenance_message: e.target.value })} rows={2} />
            </Label>
            <Toggle checked={d.shop.allow_gift_to_others} onChange={(v) => setD("shop", { allow_gift_to_others: v })} label="Покупка Stars для другого пользователя" />
            {saveBtn("shop")}
          </div>
        </Card>
      )}

      {tab === "checkout" && (
        <Card className="p-5">
          <div className="max-w-[640px] space-y-4">
            <p className="text-[13px] text-text-2">Комиссия добавляется к сумме заказа и показывается покупателю до оплаты.</p>
            {integ.payments.map((p) => (
              <Label key={p.id} label={`Комиссия «${p.title}», %`}>
                <Input
                  inputMode="decimal"
                  value={d.checkout.provider_fee_percent[p.id] ?? "0"}
                  onChange={(e) => setD("checkout", { provider_fee_percent: { ...d.checkout.provider_fee_percent, [p.id]: e.target.value.replace(",", ".") } })}
                />
              </Label>
            ))}
            <div className="grid grid-cols-2 gap-3">
              <Label label={`Фиксированная комиссия, ${integ.currency}`}>
                <Input inputMode="decimal" value={d.checkout.fee_fixed} onChange={(e) => setD("checkout", { fee_fixed: e.target.value.replace(",", ".") })} />
              </Label>
              <Label label={`Минимальная сумма к оплате, ${integ.currency}`} hint="Скидки и бонусы не опускают сумму ниже">
                <Input inputMode="decimal" value={d.checkout.min_payable} onChange={(e) => setD("checkout", { min_payable: e.target.value.replace(",", ".") })} />
              </Label>
            </div>
            {saveBtn("checkout")}
          </div>
        </Card>
      )}

      {tab === "referral" && (
        <Card className="p-5">
          <div className="max-w-[640px] space-y-4">
            <Toggle checked={d.referral.enabled} onChange={(v) => setD("referral", { enabled: v })} label="Реферальная программа включена" />
            <div className="grid grid-cols-2 gap-3">
              <Label label="Тип награды">
                <Select value={d.referral.reward_kind} onChange={(e) => setD("referral", { reward_kind: e.target.value as "percent" | "fixed" })}>
                  <option value="percent">% от первого заказа</option>
                  <option value="fixed">Фиксированная сумма</option>
                </Select>
              </Label>
              <Label label={d.referral.reward_kind === "percent" ? "Размер, %" : `Размер, ${integ.currency}`}>
                <Input inputMode="decimal" value={d.referral.reward_value} onChange={(e) => setD("referral", { reward_value: e.target.value.replace(",", ".") })} />
              </Label>
              <Label label={`Мин. сумма заказа для награды, ${integ.currency}`}>
                <Input inputMode="decimal" value={d.referral.min_order_amount} onChange={(e) => setD("referral", { min_order_amount: e.target.value.replace(",", ".") })} />
              </Label>
              <Label label="Оплата бонусами, % заказа">
                <Input inputMode="decimal" value={d.referral.max_bonus_spend_percent} onChange={(e) => setD("referral", { max_bonus_spend_percent: e.target.value.replace(",", ".") })} />
              </Label>
              <Label label="Лимит наград на одного пригласившего" hint="Пусто — без лимита">
                <Input inputMode="numeric" value={d.referral.max_rewards_per_referrer ?? ""} onChange={(e) => setD("referral", { max_rewards_per_referrer: e.target.value ? Number(e.target.value.replace(/\D/g, "")) : null })} />
              </Label>
            </div>
            <div className="space-y-3 rounded-xl bg-surface-2/60 p-4 ring-1 ring-inset ring-line">
              <div className="text-[14px] font-semibold">Вывод бонусов звёздами</div>
              <Toggle checked={d.referral.withdrawal_enabled} onChange={(v) => setD("referral", { withdrawal_enabled: v })} label="Пользователи могут выводить бонусы в Stars" />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Label label="Минимум к выводу, Stars">
                  <Input inputMode="numeric" value={d.referral.withdrawal_min_stars} onChange={(e) => setD("referral", { withdrawal_min_stars: Number(e.target.value.replace(/\D/g, "")) || 1 })} />
                </Label>
                <Label label={`Курс: бонусов (${integ.currency}) за 1 Star`} hint="Пусто — цена звезды из «Своё количество»">
                  <Input inputMode="decimal" value={d.referral.withdrawal_rate ?? ""} onChange={(e) => setD("referral", { withdrawal_rate: e.target.value.replace(",", ".") || null })} />
                </Label>
              </div>
              <Toggle
                checked={d.referral.withdrawal_auto_approve}
                onChange={(v) => setD("referral", { withdrawal_auto_approve: v })}
                label="Одобрять автоматически"
                hint="Иначе каждую заявку проверяет администратор в разделе «Выводы»"
              />
            </div>
            <p className="text-[12.5px] leading-relaxed text-text-3">
              Защита: награда только за новых пользователей, после оплаченного и выполненного заказа в PRODUCTION; самоприглашения, взаимные приглашения и подарки пригласившему не вознаграждаются; при возврате заказа награда списывается.
            </p>
            {saveBtn("referral")}
          </div>
        </Card>
      )}

      {tab === "emoji" && (
        <Card className="p-5">
          <div className="max-w-[640px] space-y-4">
            <p className="text-[13px] leading-relaxed text-text-2">
              Премиум-эмодзи в сообщениях и на кнопках бота. Telegram показывает их, только если у владельца бота есть Telegram Premium (или у бота
              коллекционный username с Fragment). Если Telegram их не примет, бот автоматически отправит обычные эмодзи.
            </p>
            <p className="text-[13px] leading-relaxed text-text-2">
              Как узнать ID: отправьте боту нужный премиум-эмодзи (вы должны быть администратором) — он ответит его ID.
            </p>
            <Toggle checked={d.bot_emoji.enabled} onChange={(v) => setD("bot_emoji", { enabled: v })} label="Использовать премиум-эмодзи" />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {EMOJI_KEYS.map(([key, label]) => (
                <Label key={key} label={label}>
                  <Input
                    inputMode="numeric"
                    placeholder="ID эмодзи"
                    value={d.bot_emoji.ids[key] ?? ""}
                    onChange={(e) => setD("bot_emoji", { ids: { ...d.bot_emoji.ids, [key]: e.target.value.replace(/\D/g, "") } })}
                  />
                </Label>
              ))}
            </div>
            {saveBtn("bot_emoji")}
          </div>
        </Card>
      )}

      {tab === "lucky" && (
        <Card className="p-5">
          <div className="max-w-[640px] space-y-4">
            <p className="text-[13px] leading-relaxed text-text-2">
              Попытка оплачивается в Telegram Stars. Покупатель выбирает приз — пакет звёзд — и шанс и платит ту же долю звёзд: 15% шанса на пакет 1000 ⭐ стоят 150 ⭐. При выигрыше пакет доставляется как обычная
              покупка, при проигрыше оплата не возвращается. Розыгрыш проверяемый: хэш сида сервера публикуется до оплаты, сам сид — после. Для реальной оплаты звёздами добавьте <code>telegram_stars</code> в
              <code>PAYMENT_PROVIDERS</code>.
            </p>
            <div className="flex gap-3 rounded-2xl bg-warning/10 p-4 text-[13px] leading-relaxed text-text-2 ring-1 ring-inset ring-warning/25">
              <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" />
              <span>
                Это игра на удачу с денежной ставкой. Во многих странах, в том числе в России, такие механики относятся к азартным играм или лотереям и требуют лицензии; Telegram и платёжные провайдеры тоже могут их
                ограничивать. Включайте для реальных продаж только после консультации с юристом.
              </span>
            </div>
            <Label label="Доступность">
              <Select value={d.lucky.mode} onChange={(e) => setD("lucky", { mode: e.target.value as SettingsData["lucky"]["mode"] })} disabled={!owner}>
                <option value="off">Выключен</option>
                <option value="demo_only">Только в DEMO-режиме</option>
                <option value="on">Включён, в том числе в PRODUCTION</option>
              </Select>
            </Label>
            <div className="grid grid-cols-2 gap-3">
              <Label label="Минимальный шанс, %">
                <Input inputMode="numeric" value={d.lucky.min_chance_percent} onChange={(e) => setD("lucky", { min_chance_percent: Number(e.target.value.replace(/\D/g, "")) || 0 })} />
              </Label>
              <Label label="Максимальный шанс, %">
                <Input inputMode="numeric" value={d.lucky.max_chance_percent} onChange={(e) => setD("lucky", { max_chance_percent: Number(e.target.value.replace(/\D/g, "")) || 0 })} />
              </Label>
              <Label label="Сбор Lucky Buy, %" hint="Сверх доли цены; покупатель видит его до оплаты">
                <Input inputMode="decimal" value={d.lucky.fee_percent} onChange={(e) => setD("lucky", { fee_percent: e.target.value.replace(",", ".") })} />
              </Label>
              <Label label="Попыток на человека за сутки" hint="Пусто — без лимита">
                <Input inputMode="numeric" value={d.lucky.daily_limit ?? ""} onChange={(e) => setD("lucky", { daily_limit: e.target.value ? Number(e.target.value.replace(/\D/g, "")) : null })} />
              </Label>
              <Label label="Минимальная цена попытки, ⭐" hint="На главной: «от N ⭐»">
                <Input inputMode="numeric" value={d.lucky.min_stake_stars} onChange={(e) => setD("lucky", { min_stake_stars: Number(e.target.value.replace(/\D/g, "")) || 1 })} />
              </Label>
            </div>
            <Label label="Призы" hint="Пакеты, которые можно выиграть. Ничего не выбрано — все активные пакеты.">
              <div className="flex flex-wrap gap-2">
                {(products.data?.items ?? [])
                  .filter((p) => p.kind === "package" && !p.is_archived)
                  .map((p) => {
                    const on = d.lucky.prize_product_ids.includes(p.id);
                    return (
                      <button
                        key={p.id}
                        type="button"
                        disabled={!owner}
                        onClick={() =>
                          setD("lucky", { prize_product_ids: on ? d.lucky.prize_product_ids.filter((x) => x !== p.id) : [...d.lucky.prize_product_ids, p.id] })
                        }
                        className={`h-9 rounded-xl px-3 text-[13px] font-semibold ring-1 ring-inset transition ${on ? "bg-accent/14 ring-accent" : "bg-surface-2 ring-line"}`}
                      >
                        {p.stars_amount} ⭐
                      </button>
                    );
                  })}
              </div>
            </Label>
            {saveBtn("lucky")}
          </div>
        </Card>
      )}

      {tab === "notifications" && (
        <Card className="p-5">
          <div className="max-w-[640px] space-y-4">
            <Toggle checked={d.notifications.user_notifications} onChange={(v) => setD("notifications", { user_notifications: v })} label="Уведомления покупателям" hint="Создание заказа, оплата, доставка, проблемы, возвраты" />
            <Toggle checked={d.notifications.admin_new_paid_order} onChange={(v) => setD("notifications", { admin_new_paid_order: v })} label="Админам: новый оплаченный заказ" />
            <Toggle checked={d.notifications.admin_delivery_problem} onChange={(v) => setD("notifications", { admin_delivery_problem: v })} label="Админам: проблемы с доставкой и платежами" />
            <Toggle checked={d.notifications.admin_new_ticket} onChange={(v) => setD("notifications", { admin_new_ticket: v })} label="Админам: новые обращения" />
            {saveBtn("notifications")}
          </div>
        </Card>
      )}

      {tab === "admins" && owner && <Admins bootstrapIds={integ.bootstrap_admin_ids} />}

      {tab === "integrations" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Telegram">
            <KV
              items={[
                ["Токен бота", <Flag key="t" ok={integ.bot.token_configured}>{integ.bot.token_configured ? "задан в .env" : "не задан"}</Flag>],
                ["Бот", integ.bot.username ? `@${integ.bot.username}` : "BOT_USERNAME не задан"],
                ["Режим бота", integ.bot.mode],
                ["Mini App URL", integ.bot.webapp_url],
              ]}
            />
          </Card>
          <Card title="Окружение">
            <KV
              items={[
                ["APP_ENV", integ.app_env],
                ["PRODUCTION разрешён", integ.allow_production ? "да" : "нет"],
                ["Валюта", integ.currency],
                ["Часовой пояс", integ.timezone],
                ["Redis", <Flag key="r" ok={integ.redis_configured}>{integ.redis_configured ? "подключён" : "не задан"}</Flag>],
              ]}
            />
          </Card>
          <Card title="Платёжные провайдеры">
            <ul className="divide-y divide-line">
              {integ.payments.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3 px-5 py-3 text-[13.5px]">
                  <span>
                    <span className="font-semibold">{p.title}</span>
                    <span className="block text-[12px] text-text-3">
                      {p.id}
                      {p.id === "cryptopay" && ` · ${integ.cryptopay_network}`} · возвраты: {p.supports_refunds ? "да" : "вручную"}
                    </span>
                  </span>
                  <span className="flex gap-2">
                    {p.is_demo && <Badge tone="warning">DEMO</Badge>}
                    <Badge tone={p.enabled ? "success" : "neutral"}>{p.enabled ? "включён" : "выключен"}</Badge>
                    <Badge tone={p.configured ? "success" : "danger"}>{p.configured ? "настроен" : "нет ключей"}</Badge>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Доставка Stars">
            <KV
              items={[
                ["Способ", `${integ.delivery.title} (${integ.delivery.id})`],
                ["Статус", <Flag key="d" ok={integ.delivery.configured && !integ.delivery.is_demo}>{integ.delivery.is_demo ? "DEMO — Stars не отправляются" : integ.delivery.configured ? "настроен" : "не настроен"}</Flag>],
                ["Защита от повторов", integ.delivery.idempotent ? "да (Idempotency-Key)" : "нет — повтор только после ручной проверки"],
                ["Размер заказа", `${integ.delivery.min_stars} – ${integ.delivery.max_stars} Stars`],
              ]}
            />
          </Card>
        </div>
      )}

      {tab === "webhooks" && <Webhooks />}

      <Modal
        open={confirmProd}
        onClose={() => setConfirmProd(false)}
        title="Включить PRODUCTION?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmProd(false)}>
              Отмена
            </Button>
            <Button variant="danger" loading={save.isPending} onClick={() => save.mutate("shop")}>
              Включить реальные продажи
            </Button>
          </>
        }
      >
        <p className="flex gap-2 text-[13.5px] leading-relaxed text-text-2">
          <TriangleAlert className="mt-0.5 size-5 shrink-0 text-warning" />
          DEMO-оплата станет недоступна, заказы будут оплачиваться через реальных провайдеров и доставляться выбранным способом. Убедитесь, что вы провели тестовую покупку на тестовой сети провайдера.
        </p>
      </Modal>
    </>
  );
}

function Admins({ bootstrapIds }: { bootstrapIds: number[] }) {
  const toast = useToast();
  const qc = useQueryClient();
  const admins = useQuery({ queryKey: ["admins"], queryFn: () => api<{ items: Admin[] }>("/admins") });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ telegram_id: "", display_name: "", role: "support" as Role });
  const add = useMutation({
    mutationFn: () => api("/admins", { method: "POST", body: { telegram_id: Number(form.telegram_id), display_name: form.display_name || null, role: form.role } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admins"] });
      setOpen(false);
      setForm({ telegram_id: "", display_name: "", role: "support" });
      toast("Администратор добавлен. Он может войти командой /admin в боте");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api(`/admins/${id}`, { method: "PATCH", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admins"] }),
    onError: (e) => toast(errorMessage(e), "error"),
  });
  return (
    <Card title="Администраторы" action={<Button size="sm" icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>Добавить</Button>}>
      {admins.isPending ? (
        <Skeleton className="m-4 h-24" />
      ) : (
        <table className="data w-full">
          <thead>
            <tr>
              <th>Администратор</th>
              <th>Telegram ID</th>
              <th>Роль</th>
              <th>Последний вход</th>
              <th>Доступ</th>
            </tr>
          </thead>
          <tbody>
            {admins.data?.items.map((a) => {
              const locked = bootstrapIds.includes(a.telegram_id);
              return (
                <tr key={a.id}>
                  <td className="font-semibold">
                    {a.display_name || (a.username ? `@${a.username}` : "—")} {locked && <Badge tone="info">из .env</Badge>}
                  </td>
                  <td className="tabular">{a.telegram_id}</td>
                  <td>
                    <Select value={a.role} disabled={locked} onChange={(e) => patch.mutate({ id: a.id, body: { role: e.target.value } })} className="h-8 w-auto text-[13px]">
                      {(Object.keys(ROLE) as Role[]).map((r) => (
                        <option key={r} value={r}>
                          {ROLE[r]}
                        </option>
                      ))}
                    </Select>
                  </td>
                  <td className="text-text-2">{a.last_login_at ? formatDate(a.last_login_at) : "—"}</td>
                  <td>{!locked && <Toggle checked={a.is_active} onChange={(v) => patch.mutate({ id: a.id, body: { is_active: v } })} label={a.is_active ? "Активен" : "Отключён"} />}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Новый администратор"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Отмена
            </Button>
            <Button disabled={!/^\d{3,15}$/.test(form.telegram_id)} loading={add.isPending} onClick={() => add.mutate()}>
              Добавить
            </Button>
          </>
        }
      >
        <Label label="Telegram ID" hint="Узнать ID можно в профиле пользователя в админке или у @userinfobot">
          <Input inputMode="numeric" value={form.telegram_id} onChange={(e) => setForm({ ...form, telegram_id: e.target.value.replace(/\D/g, "") })} />
        </Label>
        <Label label="Имя (для журнала)">
          <Input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
        </Label>
        <Label label="Роль" hint="Поддержка: заказы и обращения. Менеджер: + каталог, возвраты, промокоды, контент. Владелец: всё, включая настройки">
          <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
            {(Object.keys(ROLE) as Role[]).map((r) => (
              <option key={r} value={r}>
                {ROLE[r]}
              </option>
            ))}
          </Select>
        </Label>
      </Modal>
    </Card>
  );
}

function Webhooks() {
  const hooks = useQuery({
    queryKey: ["webhooks"],
    queryFn: () => api<{ items: { id: number; provider: string; event_id: string | null; type: string | null; signature_valid: boolean; status: string; error: string | null; remote_ip: string | null; received_at: string }[] }>("/webhook-events"),
    refetchInterval: 30_000,
  });
  return (
    <Card title="Последние webhook-события" className="overflow-hidden">
      {hooks.isPending ? (
        <Skeleton className="m-4 h-24" />
      ) : (
        <div className="overflow-x-auto">
          <table className="data w-full min-w-[760px]">
            <thead>
              <tr>
                <th>Получено</th>
                <th>Провайдер</th>
                <th>Событие</th>
                <th>Подпись</th>
                <th>Статус</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {hooks.data?.items.map((h) => (
                <tr key={h.id}>
                  <td className="whitespace-nowrap text-text-2">{formatDate(h.received_at)}</td>
                  <td>{h.provider}</td>
                  <td className="font-mono text-[12px]">
                    {h.type ?? "—"} {h.event_id && <span className="text-text-3">#{h.event_id.slice(0, 18)}</span>}
                  </td>
                  <td>{h.signature_valid ? <Badge tone="success">верна</Badge> : <Badge tone="danger">неверна</Badge>}</td>
                  <td>
                    <Badge tone={h.status === "processed" ? "success" : h.status === "ignored" ? "neutral" : "danger"}>{h.status}</Badge>
                    {h.error && <div className="mt-1 text-[11.5px] text-danger">{h.error}</div>}
                  </td>
                  <td className="text-text-3">{h.remote_ip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
