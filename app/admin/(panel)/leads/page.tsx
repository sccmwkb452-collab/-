import type { LeadStatus, Prisma } from "@prisma/client";
import { Download, Search } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { LeadStatusBadge } from "@/components/admin/lead-status-badge";
import { AdminPageHeader } from "@/components/admin/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LEAD_STATUS_LABELS, LEAD_STATUS_ORDER } from "@/lib/constants";
import { prisma } from "@/lib/db";
import { cn, formatArea, formatDate, formatPhoneDisplay, formatPrice } from "@/lib/utils";

export const metadata: Metadata = { title: "Заявки" };

const PAGE_SIZE = 20;
const TABS: { value: LeadStatus | "ALL"; label: string }[] = [
  { value: "ALL", label: "Все" },
  ...LEAD_STATUS_ORDER.map((s) => ({ value: s, label: LEAD_STATUS_LABELS[s] })),
];

type Props = { searchParams: Promise<{ status?: string; q?: string; page?: string }> };

export default async function LeadsPage({ searchParams }: Props) {
  const sp = await searchParams;
  const status = LEAD_STATUS_ORDER.includes(sp.status as LeadStatus) ? (sp.status as LeadStatus) : null;
  const q = sp.q?.trim().slice(0, 100) ?? "";
  const page = Math.max(1, Number(sp.page) || 1);

  const where: Prisma.LeadWhereInput = {
    ...(status ? { status } : {}),
    ...(q ? { OR: [{ name: { contains: q, mode: "insensitive" } }, { phone: { contains: q.replace(/[^\d+]/g, "") || q } }, { email: { contains: q, mode: "insensitive" } }] } : {}),
  };

  const [leads, total, counts] = await Promise.all([
    prisma.lead.findMany({ where, orderBy: { createdAt: "desc" }, skip: (page - 1) * PAGE_SIZE, take: PAGE_SIZE, include: { project: { select: { title: true } } } }),
    prisma.lead.count({ where }),
    prisma.lead.groupBy({ by: ["status"], _count: { _all: true } }),
  ]);
  const countMap = new Map(counts.map((c) => [c.status, c._count._all]));
  const all = counts.reduce((s, c) => s + c._count._all, 0);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const href = (patch: Record<string, string | null>) => {
    const p = new URLSearchParams();
    const merged = { status: status ?? null, q: q || null, page: null as string | null, ...patch };
    Object.entries(merged).forEach(([k, v]) => v && p.set(k, v));
    const s = p.toString();
    return s ? `/admin/leads?${s}` : "/admin/leads";
  };
  const exportParams = new URLSearchParams();
  if (status) exportParams.set("status", status);
  if (q) exportParams.set("q", q);

  return (
    <>
      <AdminPageHeader
        title="Заявки"
        description={`Всего заявок: ${all}`}
        actions={
          <Button asChild variant="outline">
            <a href={`/api/admin/leads/export?${exportParams.toString()}`}>
              <Download />
              Экспорт CSV
            </a>
          </Button>
        }
      />

      <div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <nav aria-label="Фильтр по статусу" className="-mx-4 overflow-x-auto px-4">
          <ul className="flex gap-1.5">
            {TABS.map((t) => {
              const active = (t.value === "ALL" && !status) || t.value === status;
              const c = t.value === "ALL" ? all : countMap.get(t.value) ?? 0;
              return (
                <li key={t.value}>
                  <Link
                    href={href({ status: t.value === "ALL" ? null : t.value })}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex h-9 items-center gap-2 rounded-full px-4 text-sm font-medium whitespace-nowrap transition",
                      active ? "bg-primary text-primary-foreground" : "bg-white text-foreground/70 hover:text-foreground",
                    )}
                  >
                    {t.label}
                    <span className={cn("text-xs tabular", active ? "text-white/60" : "text-muted-foreground")}>{c}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <form className="relative w-full xl:w-72" action="/admin/leads">
          {status && <input type="hidden" name="status" value={status} />}
          <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input name="q" defaultValue={q} placeholder="Имя, телефон или email" className="h-10 pl-10" aria-label="Поиск заявок" />
        </form>
      </div>

      <Card className="overflow-hidden">
        {leads.length ? (
          <>
            <Table className="hidden md:table">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Имя</TableHead>
                  <TableHead>Телефон</TableHead>
                  <TableHead>Проект</TableHead>
                  <TableHead>Площадь</TableHead>
                  <TableHead className="text-right">Стоимость</TableHead>
                  <TableHead>Дата</TableHead>
                  <TableHead>Статус</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {leads.map((l) => (
                  <TableRow key={l.id} className="relative">
                    <TableCell className="font-medium">
                      <Link href={`/admin/leads/${l.id}`} className="after:absolute after:inset-0">{l.name}</Link>
                    </TableCell>
                    <TableCell className="tabular">{formatPhoneDisplay(l.phone)}</TableCell>
                    <TableCell className="text-muted-foreground">{l.project?.title ?? (l.houseType ? `Свой: ${l.houseType.toLowerCase()}` : "—")}</TableCell>
                    <TableCell className="tabular">{l.area ? formatArea(l.area) : "—"}</TableCell>
                    <TableCell className="text-right font-medium tabular">{l.estimatedPrice ? formatPrice(l.estimatedPrice) : "—"}</TableCell>
                    <TableCell className="text-muted-foreground tabular">{formatDate(l.createdAt, true)}</TableCell>
                    <TableCell><LeadStatusBadge status={l.status} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <ul className="divide-y divide-border md:hidden">
              {leads.map((l) => (
                <li key={l.id}>
                  <Link href={`/admin/leads/${l.id}`} className="block p-4 active:bg-secondary">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold">{l.name}</p>
                        <p className="text-sm text-muted-foreground tabular">{formatPhoneDisplay(l.phone)}</p>
                      </div>
                      <LeadStatusBadge status={l.status} />
                    </div>
                    <div className="mt-3 flex justify-between text-sm">
                      <span className="text-muted-foreground">{l.project?.title ?? (l.area ? formatArea(l.area) : "—")}</span>
                      <span className="font-medium tabular">{l.estimatedPrice ? formatPrice(l.estimatedPrice) : "—"}</span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{formatDate(l.createdAt, true)}</p>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <div className="px-6 py-16 text-center">
            <p className="font-semibold">Заявок не найдено</p>
            <p className="mt-1 text-sm text-muted-foreground">{q || status ? "Измените фильтр или поисковый запрос." : "Новые заявки с сайта появятся здесь."}</p>
            {(q || status) && (
              <Button asChild variant="outline" size="sm" className="mt-4"><Link href="/admin/leads">Сбросить фильтры</Link></Button>
            )}
          </div>
        )}
      </Card>

      {pages > 1 && (
        <nav aria-label="Страницы" className="mt-6 flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Страница {page} из {pages}</span>
          <div className="flex gap-2">
            {page > 1 ? <Button asChild variant="outline" size="sm"><Link href={href({ page: String(page - 1) })}>Назад</Link></Button> : <Button variant="outline" size="sm" disabled>Назад</Button>}
            {page < pages ? <Button asChild variant="outline" size="sm"><Link href={href({ page: String(page + 1) })}>Вперёд</Link></Button> : <Button variant="outline" size="sm" disabled>Вперёд</Button>}
          </div>
        </nav>
      )}
    </>
  );
}
