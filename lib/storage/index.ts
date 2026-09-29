import "server-only";
import { randomBytes } from "node:crypto";
import sharp from "sharp";
import { localDriver } from "./local";
import { s3Driver } from "./s3";
import type { StorageDriver } from "./types";

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ALLOWED_MIME = new Set(["image/jpeg", "image/png", "image/webp", "image/avif"]);

export function getStorage(): StorageDriver {
  return process.env.STORAGE_DRIVER === "s3" ? s3Driver : localDriver;
}

export class UploadError extends Error {}

/** Проверка сигнатуры файла — MIME из браузера не является доверенным источником. */
function sniffImage(buf: Buffer) {
  if (buf.length < 12) return null;
  if (buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return "image/jpeg";
  if (buf.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return "image/png";
  if (buf.toString("ascii", 0, 4) === "RIFF" && buf.toString("ascii", 8, 12) === "WEBP") return "image/webp";
  if (buf.toString("ascii", 4, 12) === "ftypavif") return "image/avif";
  return null;
}

/**
 * Принимает изображение, проверяет размер и тип, перекодирует в WebP
 * (удаляет EXIF и любые встроенные данные) и сохраняет в хранилище.
 */
export async function saveImage(file: File, folder: string) {
  if (file.size === 0) throw new UploadError("Пустой файл");
  if (file.size > MAX_UPLOAD_BYTES) throw new UploadError("Файл больше 10 МБ");
  if (!ALLOWED_MIME.has(file.type)) throw new UploadError("Допустимы только JPG, PNG, WebP, AVIF");
  const input = Buffer.from(await file.arrayBuffer());
  const sniffed = sniffImage(input);
  if (!sniffed || !ALLOWED_MIME.has(sniffed)) throw new UploadError("Файл не является изображением");

  let output: Buffer;
  let width: number | undefined;
  let height: number | undefined;
  try {
    const result = await sharp(input, { limitInputPixels: 60_000_000 })
      .rotate()
      .resize({ width: 2400, height: 2400, fit: "inside", withoutEnlargement: true })
      .webp({ quality: 82 })
      .toBuffer({ resolveWithObject: true });
    output = result.data;
    width = result.info.width;
    height = result.info.height;
  } catch {
    throw new UploadError("Не удалось обработать изображение");
  }

  const safeFolder = folder.replace(/[^a-z0-9-]/gi, "").slice(0, 60) || "misc";
  const key = `${safeFolder}/${Date.now()}-${randomBytes(6).toString("hex")}.webp`;
  const stored = await getStorage().put(key, output, "image/webp");
  return { ...stored, width, height };
}

export async function deleteStoredFile(key: string | null | undefined) {
  if (!key) return;
  try {
    await getStorage().delete(key);
  } catch (error) {
    console.error("[storage] delete failed", error);
  }
}
