import { readLocalFile } from "@/lib/storage/local";

/** Раздача файлов локального хранилища. Используется, когда STORAGE_DRIVER=local. */
export async function GET(_req: Request, { params }: { params: Promise<{ key: string[] }> }) {
  const { key } = await params;
  const path = key.join("/");
  if (!/^[a-z0-9-]+\/[a-z0-9-]+\.webp$/i.test(path)) return new Response("Not found", { status: 404 });
  try {
    const data = await readLocalFile(path);
    return new Response(new Uint8Array(data), {
      headers: {
        "Content-Type": "image/webp",
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
