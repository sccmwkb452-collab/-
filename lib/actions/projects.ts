"use server";

import type { ImageKind } from "@prisma/client";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { assertAdmin } from "@/lib/auth/session";
import { prisma } from "@/lib/db";
import { deleteStoredFile } from "@/lib/storage";
import { projectSchema } from "@/lib/validation/admin";
import { handleActionError, validationError, type ActionResult } from "./result";

const idSchema = z.string().min(1).max(40);

function revalidateProject(slug?: string) {
  revalidatePath("/admin/projects");
  revalidatePath("/projects");
  revalidatePath("/");
  if (slug) revalidatePath(`/projects/${slug}`);
}

function toData(values: z.output<typeof projectSchema>) {
  const { featuresText, ...rest } = values;
  return {
    ...rest,
    features: featuresText
      .split("\n")
      .map((f) => f.trim())
      .filter(Boolean)
      .slice(0, 30),
  };
}

export async function createProjectAction(input: unknown): Promise<ActionResult<{ id: string }>> {
  try {
    await assertAdmin();
    const parsed = projectSchema.safeParse(input);
    if (!parsed.success) return validationError(parsed.error);
    const exists = await prisma.project.findUnique({ where: { slug: parsed.data.slug }, select: { id: true } });
    if (exists) return { ok: false, error: "Такой адрес уже занят", fieldErrors: { slug: ["Такой адрес уже используется"] } };
    const project = await prisma.project.create({ data: toData(parsed.data), select: { id: true, slug: true } });
    revalidateProject(project.slug);
    return { ok: true, message: "Проект создан", data: { id: project.id } };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function updateProjectAction(id: string, input: unknown): Promise<ActionResult> {
  try {
    await assertAdmin();
    const projectId = idSchema.parse(id);
    const parsed = projectSchema.safeParse(input);
    if (!parsed.success) return validationError(parsed.error);
    const conflict = await prisma.project.findFirst({ where: { slug: parsed.data.slug, NOT: { id: projectId } }, select: { id: true } });
    if (conflict) return { ok: false, error: "Такой адрес уже занят", fieldErrors: { slug: ["Такой адрес уже используется"] } };
    const before = await prisma.project.findUnique({ where: { id: projectId }, select: { slug: true } });
    if (!before) return { ok: false, error: "Проект не найден" };
    await prisma.project.update({ where: { id: projectId }, data: toData(parsed.data) });
    revalidateProject(before.slug);
    revalidateProject(parsed.data.slug);
    return { ok: true, message: "Изменения сохранены" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function setProjectStatusAction(id: string, status: "DRAFT" | "PUBLISHED" | "HIDDEN"): Promise<ActionResult> {
  try {
    await assertAdmin();
    const project = await prisma.project.update({
      where: { id: idSchema.parse(id) },
      data: { status: z.enum(["DRAFT", "PUBLISHED", "HIDDEN"]).parse(status) },
      select: { slug: true },
    });
    revalidateProject(project.slug);
    return { ok: true, message: status === "PUBLISHED" ? "Проект опубликован" : status === "HIDDEN" ? "Проект скрыт" : "Проект переведён в черновики" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function deleteProjectAction(id: string): Promise<ActionResult> {
  try {
    await assertAdmin();
    const project = await prisma.project.findUnique({ where: { id: idSchema.parse(id) }, include: { images: true } });
    if (!project) return { ok: false, error: "Проект не найден" };
    await prisma.project.delete({ where: { id: project.id } });
    await Promise.all(project.images.map((img) => deleteStoredFile(img.storageKey)));
    revalidateProject(project.slug);
    return { ok: true, message: "Проект удалён" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function deleteProjectImageAction(imageId: string): Promise<ActionResult> {
  try {
    await assertAdmin();
    const image = await prisma.projectImage.delete({ where: { id: idSchema.parse(imageId) }, include: { project: { select: { id: true, slug: true } } } });
    await deleteStoredFile(image.storageKey);
    revalidateProject(image.project.slug);
    revalidatePath(`/admin/projects/${image.project.id}`);
    return { ok: true, message: "Изображение удалено" };
  } catch (error) {
    return handleActionError(error);
  }
}

export async function updateProjectImageAction(imageId: string, patch: { alt?: string; kind?: ImageKind; move?: -1 | 1 }): Promise<ActionResult> {
  try {
    await assertAdmin();
    const id = idSchema.parse(imageId);
    const image = await prisma.projectImage.findUnique({ where: { id }, include: { project: { select: { id: true, slug: true } } } });
    if (!image) return { ok: false, error: "Изображение не найдено" };

    if (patch.kind === "COVER") {
      await prisma.$transaction([
        prisma.projectImage.updateMany({ where: { projectId: image.projectId, kind: "COVER" }, data: { kind: "GALLERY" } }),
        prisma.projectImage.update({ where: { id }, data: { kind: "COVER", sortOrder: 0 } }),
      ]);
    } else if (patch.kind) {
      await prisma.projectImage.update({ where: { id }, data: { kind: z.enum(["COVER", "GALLERY", "PLAN"]).parse(patch.kind) } });
    }
    if (patch.alt !== undefined) {
      await prisma.projectImage.update({ where: { id }, data: { alt: z.string().trim().max(200).parse(patch.alt) } });
    }
    if (patch.move) {
      const siblings = await prisma.projectImage.findMany({ where: { projectId: image.projectId, kind: image.kind }, orderBy: [{ sortOrder: "asc" }, { createdAt: "asc" }] });
      const index = siblings.findIndex((s) => s.id === id);
      const target = index + patch.move;
      if (target >= 0 && target < siblings.length) {
        const reordered = [...siblings];
        [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
        await prisma.$transaction(reordered.map((s, i) => prisma.projectImage.update({ where: { id: s.id }, data: { sortOrder: i } })));
      }
    }
    revalidateProject(image.project.slug);
    revalidatePath(`/admin/projects/${image.project.id}`);
    return { ok: true };
  } catch (error) {
    return handleActionError(error);
  }
}
