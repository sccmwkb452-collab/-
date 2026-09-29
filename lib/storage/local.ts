import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import type { StorageDriver } from "./types";

export function localRoot() {
  return path.resolve(process.cwd(), process.env.STORAGE_LOCAL_DIR || "storage/uploads");
}

/** Безопасное разрешение ключа: запрещает выход за пределы каталога хранилища. */
export function resolveLocalPath(key: string) {
  const root = localRoot();
  const target = path.resolve(root, key);
  if (!target.startsWith(root + path.sep)) throw new Error("Недопустимый путь файла");
  return target;
}

export async function readLocalFile(key: string) {
  return readFile(resolveLocalPath(key));
}

export const localDriver: StorageDriver = {
  async put(key, data) {
    const target = resolveLocalPath(key);
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, data);
    return { key, url: `/media/${key}` };
  },
  async delete(key) {
    await rm(resolveLocalPath(key), { force: true });
  },
};
