import { revalidatePath } from "next/cache";
import { guardAdminApi } from "@/lib/auth/api";
import { prisma } from "@/lib/db";
import { jsonError } from "@/lib/security/request";
import { saveImage, UploadError } from "@/lib/storage";

export async function POST(req: Request) {
  const { response } = await guardAdminApi(req);
  if (response) return response;
  const form = await req.formData().catch(() => null);
  const file = form?.get("file");
  if (!(file instanceof File)) return jsonError("Выберите файл", 400);
  try {
    const stored = await saveImage(file, "brand");
    await prisma.siteSetting.update({ where: { id: 1 }, data: { logoUrl: stored.url } });
    revalidatePath("/", "layout");
    return Response.json({ ok: true, url: stored.url });
  } catch (error) {
    if (error instanceof UploadError) return jsonError(error.message, 400);
    console.error("[logo]", error);
    return jsonError("Не удалось загрузить логотип", 500);
  }
}
