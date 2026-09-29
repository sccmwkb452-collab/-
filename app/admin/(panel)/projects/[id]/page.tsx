import { ArrowLeft, ExternalLink } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ImageManager } from "@/components/admin/image-manager";
import { AdminPageHeader } from "@/components/admin/page-header";
import { ProjectForm } from "@/components/admin/project-form";
import { ProjectRowActions } from "@/components/admin/project-row-actions";
import { Button } from "@/components/ui/button";
import { getProjectFormOptions, projectToForm } from "@/lib/data/admin-projects";
import { prisma } from "@/lib/db";

export const metadata: Metadata = { title: "Редактирование проекта" };

export default async function EditProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [project, options] = await Promise.all([
    prisma.project.findUnique({ where: { id }, include: { images: { orderBy: [{ sortOrder: "asc" }, { createdAt: "asc" }] } } }),
    getProjectFormOptions(),
  ]);
  if (!project) notFound();

  return (
    <>
      <Link href="/admin/projects" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />Проекты</Link>
      <div className="mt-4">
        <AdminPageHeader
          title={project.title}
          description={`/projects/${project.slug}`}
          actions={
            <>
              {project.status === "PUBLISHED" && (
                <Button asChild variant="outline"><Link href={`/projects/${project.slug}`} target="_blank"><ExternalLink />На сайте</Link></Button>
              )}
              <ProjectRowActions id={project.id} slug={project.slug} title={project.title} status={project.status} redirectAfterDelete />
            </>
          }
        />
      </div>
      <div className="grid gap-6 xl:grid-cols-[1fr_26rem]">
        <ProjectForm projectId={project.id} defaults={projectToForm(project)} houseTypes={options.houseTypes} technologies={options.technologies} />
        <div className="xl:self-start">
          <ImageManager projectId={project.id} images={project.images.map((i) => ({ id: i.id, url: i.url, alt: i.alt, kind: i.kind }))} />
        </div>
      </div>
    </>
  );
}
