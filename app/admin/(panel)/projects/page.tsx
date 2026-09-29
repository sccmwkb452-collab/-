import { ImageOff, Plus } from "lucide-react";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { AdminPageHeader } from "@/components/admin/page-header";
import { ProjectRowActions } from "@/components/admin/project-row-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { prisma } from "@/lib/db";
import { formatArea, formatDate, formatPrice } from "@/lib/utils";

export const metadata: Metadata = { title: "Проекты" };

const STATUS = {
  PUBLISHED: { label: "Опубликован", variant: "success" as const },
  DRAFT: { label: "Черновик", variant: "muted" as const },
  HIDDEN: { label: "Скрыт", variant: "danger" as const },
};

export default async function AdminProjectsPage() {
  const projects = await prisma.project.findMany({
    orderBy: [{ sortOrder: "asc" }, { createdAt: "desc" }],
    include: {
      houseType: { select: { name: true } },
      images: { where: { kind: "COVER" }, take: 1 },
      _count: { select: { leads: true } },
    },
  });

  return (
    <>
      <AdminPageHeader
        title="Проекты"
        description={`Всего: ${projects.length}, опубликовано: ${projects.filter((p) => p.status === "PUBLISHED").length}`}
        actions={
          <Button asChild>
            <Link href="/admin/projects/create"><Plus />Создать проект</Link>
          </Button>
        }
      />
      {projects.length ? (
        <Card className="divide-y divide-border overflow-hidden">
          {projects.map((p) => (
            <div key={p.id} className="flex items-center gap-4 p-3 sm:p-4">
              <Link href={`/admin/projects/${p.id}`} className="relative h-16 w-24 shrink-0 overflow-hidden rounded-lg bg-secondary sm:h-20 sm:w-32">
                {p.images[0] ? (
                  <Image src={p.images[0].url} alt="" fill sizes="128px" className="object-cover" />
                ) : (
                  <span className="flex h-full items-center justify-center text-muted-foreground"><ImageOff className="size-5" /></span>
                )}
              </Link>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Link href={`/admin/projects/${p.id}`} className="font-semibold hover:underline">{p.title}</Link>
                  <Badge variant={STATUS[p.status].variant}>{STATUS[p.status].label}</Badge>
                  {p.featured && <Badge variant="accent">На главной</Badge>}
                </div>
                <p className="mt-1 truncate text-sm text-muted-foreground">
                  {formatArea(p.area)} · {p.houseType.name} · {p.bedrooms} сп. · /projects/{p.slug}
                </p>
              </div>
              <div className="hidden text-right text-sm md:block">
                <p className="font-semibold tabular">от {formatPrice(p.priceFrom)}</p>
                <p className="text-muted-foreground">{p._count.leads} заявок · {formatDate(p.updatedAt)}</p>
              </div>
              <ProjectRowActions id={p.id} slug={p.slug} title={p.title} status={p.status} />
            </div>
          ))}
        </Card>
      ) : (
        <Card className="px-6 py-16 text-center">
          <p className="font-semibold">Проектов пока нет</p>
          <p className="mt-1 text-sm text-muted-foreground">Создайте первый проект — он появится в каталоге после публикации.</p>
          <Button asChild className="mt-5"><Link href="/admin/projects/create"><Plus />Создать проект</Link></Button>
        </Card>
      )}
    </>
  );
}
