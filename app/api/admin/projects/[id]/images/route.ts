import type { ImageKind } from "@prisma/client";
import { revalidatePath } from "next/cache";
import { guardAdminApi } from "@/lib/auth/api";
import { prisma } from "@/lib/db";
import { jsonError } from "@/lib/security/request";
import { saveImage, UploadError } from "@/lib/storage";

const KINDS: ImageKind[] = ["COVER", "GALLERY", "PLAN"];
const MAX_FILES = 12;

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { response } = await guardAdminApi(req);
  if (response) return response;
  const { id } = await params;

  const project = await prisma.project.findUnique({ where: { id }, select: { id: true, slug: true, title: true } });
  if (!project) return jsonError("Проект не найден", 404);

  const contentLength = Number(req.headers.get("content-length") ?? 0);
  if (contentLength > MAX_FILES * 10 * 1024 * 1024 + 1024 * 1024) return jsonError("Слишком большой запрос", 413);

  const form = await req.formData().catch(() => null);
  if (!form) return jsonError("Некорректные данные формы", 400);
  const kind = String(form.get("kind") ?? "GALLERY") as ImageKind;
  if (!KINDS.includes(kind)) return jsonError("Неизвестный тип изображения", 400);
  const files = form.getAll("files").filter((f): f is File => f instanceof File);
  if (!files.length) return jsonError("Выберите файлы", 400);
  if (files.length > MAX_FILES) return jsonError(`Не более ${MAX_FILES} файлов за раз`, 400);

  const uploaded: string[] = [];
  const errors: string[] = [];
  const last = await prisma.projectImage.findFirst({ where: { projectId: id, kind }, orderBy: { sortOrder: "desc" }, select: { sortOrder: true } });
  let order = (last?.sortOrder ?? -1) + 1;

  for (const [index, file] of files.entries()) {
    try {
      const stored = await saveImage(file, `projects-${project.slug}`);
      const effectiveKind: ImageKind = kind === "COVER" && index > 0 ? "GALLERY" : kind;
      if (effectiveKind === "COVER") {
        await prisma.projectImage.updateMany({ where: { projectId: id, kind: "COVER" }, data: { kind: "GALLERY" } });
      }
      const image = await prisma.projectImage.create({
        data: {
          projectId: id,
          url: stored.url,
          storageKey: stored.key,
          width: stored.width,
          height: stored.height,
          kind: effectiveKind,
          alt: `${project.title}${effectiveKind === "PLAN" ? " — планировка" : ""}`,
          sortOrder: effectiveKind === "COVER" ? 0 : order++,
        },
      });
      uploaded.push(image.id);
    } catch (error) {
      errors.push(`${file.name.slice(0, 60)}: ${error instanceof UploadError ? error.message : "ошибка загрузки"}`);
      if (!(error instanceof UploadError)) console.error("[upload]", error);
    }
  }

  revalidatePath(`/admin/projects/${id}`);
  revalidatePath(`/projects/${project.slug}`);
  revalidatePath("/projects");
  return Response.json({ ok: uploaded.length > 0, uploaded: uploaded.length, errors, error: uploaded.length ? undefined : errors[0] }, { status: uploaded.length ? 200 : 400 });
}
