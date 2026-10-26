"use client";

import { KeyRound, Plus, ShieldCheck, Unlink, UserX, Users } from "lucide-react";
import * as React from "react";

import { Async, Empty, Notice, PageHeader } from "@/components/app/blocks";
import { ConfirmAction } from "@/components/app/confirm";
import { ToneBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useAction } from "@/lib/actions";
import { api, useApi } from "@/lib/api";
import { ago } from "@/lib/format";
import { useSession, type Me } from "@/lib/session";

type User = Me & { is_active: boolean; created_at: string };
type Role = { code: string; name: string; permissions: string[] };

const ROLE_HINT: Record<string, string> = {
  admin: "всё, кроме управления пользователями",
  operator: "заказы, сообщения, объявления, коды",
  viewer: "только просмотр",
};

function NewUser({ roles, onDone }: { roles: Role[]; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [v, setV] = React.useState({ email: "", display_name: "", password: "", role: "operator" });
  const { busy, run } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="primary">
          <Plus /> Добавить сотрудника
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Новый сотрудник"
        description="Передайте пароль лично, не через общий чат. Сотрудник сможет сменить его в разделе «Безопасность»."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Отмена</Button>
            <Button
              variant="primary"
              disabled={!v.email.includes("@") || !v.display_name.trim() || v.password.length < 10}
              loading={busy === "c"}
              onClick={async () => {
                const r = await run("c", () => api.post("/users", v), "Сотрудник добавлен");
                if (r) {
                  setOpen(false);
                  setV({ email: "", display_name: "", password: "", role: "operator" });
                  onDone();
                }
              }}
            >
              Создать
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="Электронная почта">
            <Input type="email" autoComplete="off" value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} />
          </Field>
          <Field label="Имя">
            <Input value={v.display_name} onChange={(e) => setV({ ...v, display_name: e.target.value })} />
          </Field>
          <Field label="Временный пароль" hint="Не короче 10 символов: строчные, заглавные буквы и цифра">
            <Input type="password" autoComplete="new-password" value={v.password} onChange={(e) => setV({ ...v, password: e.target.value })} />
          </Field>
          <Field label="Роль" hint={ROLE_HINT[v.role]}>
            <NativeSelect value={v.role} onChange={(e) => setV({ ...v, role: e.target.value })}>
              {roles
                .filter((r) => r.code !== "owner")
                .map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.name}
                  </option>
                ))}
            </NativeSelect>
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function UsersPage() {
  const { me, can } = useSession();
  const state = useApi<{ items: User[]; roles: Role[]; permissions: string[] }>(can("users.manage") ? "/users" : null);
  const { busy, run } = useAction();

  async function patch(id: number, body: Record<string, unknown>, success: string) {
    const r = await run(`u${id}`, () => api.patch(`/users/${id}`, body), success);
    if (r) state.reload();
    return r;
  }

  if (me && !can("users.manage")) {
    return (
      <>
        <PageHeader title="Пользователи" />
        <Notice tone="warning">Управлять пользователями может только владелец.</Notice>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Пользователи"
        description="Доступ к панели и боту. Владелец создаётся только командой create-admin на сервере."
        actions={state.data && <NewUser roles={state.data.roles} onDone={state.reload} />}
      />
      <Async state={state} rows={6}>
        {(d) =>
          d.items.length ? (
            <Card>
              <Table>
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH>Сотрудник</TH>
                    <TH>Роль</TH>
                    <TH>Защита</TH>
                    <TH>Последний вход</TH>
                    <TH />
                  </TR>
                </THead>
                <TBody>
                  {d.items.map((u) => {
                    const self = u.id === me?.id;
                    const isOwner = u.role === "owner";
                    return (
                      <TR key={u.id} className={u.is_active ? undefined : "opacity-60"}>
                        <TD>
                          <p className="font-medium">
                            {u.display_name} {self && <span className="text-xs font-normal text-muted-foreground">(вы)</span>}
                          </p>
                          <p className="text-xs text-muted-foreground">{u.email}</p>
                        </TD>
                        <TD>
                          {isOwner || self ? (
                            u.role_name
                          ) : (
                            <NativeSelect
                              value={u.role}
                              className="h-8 w-44 text-[13px]"
                              aria-label={`Роль ${u.display_name}`}
                              onChange={(e) => patch(u.id, { role: e.target.value }, "Роль изменена")}
                            >
                              {d.roles
                                .filter((r) => r.code !== "owner")
                                .map((r) => (
                                  <option key={r.code} value={r.code}>
                                    {r.name}
                                  </option>
                                ))}
                            </NativeSelect>
                          )}
                        </TD>
                        <TD>
                          <div className="flex flex-wrap gap-1.5">
                            {!u.is_active && <ToneBadge tone="danger">Отключён</ToneBadge>}
                            {u.totp_enabled ? (
                              <ToneBadge tone="success">
                                <ShieldCheck /> 2FA
                              </ToneBadge>
                            ) : (
                              <ToneBadge tone="warning">без 2FA</ToneBadge>
                            )}
                            {u.telegram_linked && <ToneBadge tone="info">Telegram</ToneBadge>}
                          </div>
                        </TD>
                        <TD className="whitespace-nowrap text-muted-foreground">{ago(u.last_login_at)}</TD>
                        <TD className="text-right">
                          {!self && !isOwner && (
                            <div className="flex justify-end gap-1">
                              <ConfirmAction
                                label=""
                                icon={<KeyRound />}
                                variant="ghost"
                                size="icon-sm"
                                title={`Новый пароль для ${u.display_name}`}
                                description="Все сессии сотрудника будут завершены."
                                input={{ label: "Новый пароль", type: "password", required: true, hint: "Не короче 10 символов" }}
                                onConfirm={async (password) => run(`p${u.id}`, () => api.post(`/users/${u.id}/reset-password`, { password }), "Пароль изменён")}
                              />
                              {u.telegram_linked && (
                                <ConfirmAction
                                  label=""
                                  icon={<Unlink />}
                                  variant="ghost"
                                  size="icon-sm"
                                  title="Отвязать Telegram?"
                                  description="Сотрудник потеряет доступ к боту, пока не привяжет аккаунт заново."
                                  onConfirm={() => patch(u.id, { unlink_telegram: true }, "Telegram отвязан")}
                                />
                              )}
                              <ConfirmAction
                                label=""
                                icon={<UserX />}
                                variant="ghost"
                                size="icon-sm"
                                title={u.is_active ? `Отключить ${u.display_name}?` : `Включить ${u.display_name}?`}
                                description={u.is_active ? "Все сессии будут завершены, вход станет невозможен. Данные и журнал сохранятся." : undefined}
                                confirmVariant={u.is_active ? "danger" : "primary"}
                                confirmLabel={u.is_active ? "Отключить" : "Включить"}
                                onConfirm={() => patch(u.id, { is_active: !u.is_active }, u.is_active ? "Пользователь отключён" : "Пользователь включён")}
                              />
                            </div>
                          )}
                          {busy === `u${u.id}` && <span className="sr-only">Сохранение…</span>}
                        </TD>
                      </TR>
                    );
                  })}
                </TBody>
              </Table>
            </Card>
          ) : (
            <Empty title="Пользователей нет" icon={Users} />
          )
        }
      </Async>
    </>
  );
}
