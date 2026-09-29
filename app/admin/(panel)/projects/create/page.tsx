import { ArrowLeft, ImagePlus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { AdminPageHeader } from "@/components/admin/page-header";
import { ProjectForm } from "@/components/admin/project-form";
import { Card, CardContent } from "@/components/ui/card";
import { getProjectFormOptions, projectToForm } from "@/lib/data/admin-projects";

export const metadata: Metadata = { title: "Новый проект" };

export default async function CreateProjectPage() {
  const { houseTypes, technologies } = await getProjectFormOptions();
  return (
    <>
      <Link href="/admin/projects" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />Проекты</Link>
      <div className="mt-4">
        <AdminPageHeader title="Новый проект" description="Заполните параметры. Изображения можно загрузить сразу после создания." />
      </div>
      <div className="grid gap-6 xl:grid-cols-[1fr_20rem]">
        <ProjectForm defaults={projectToForm(null, houseTypes[0]?.id)} houseTypes={houseTypes} technologies={technologies} />
        <Card className="self-start">
          <CardContent className="flex gap-3 p-5 sm:p-5">
            <ImagePlus className="size-5 shrink-0 text-accent" />
            <p className="text-sm text-muted-foreground">После сохранения откроется страница проекта, где можно загрузить главное изображение, галерею и планировки.</p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
