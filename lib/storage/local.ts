import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import type { StorageDriver } from "./types";

const INVALID_PATH = "Invalid storage path";

export function localRoot() {
  return path.resolve(/* turbopackIgnore: true */ process.cwd(), process.env.STORAGE_LOCAL_DIR || "storage/uploads");
}

/** Безопасное разрешение ключа: запрещает выход за пределы каталога хранилища. */
export function resolveLocalPath(key: string) {
  const root = localRoot();
  const target = path.resolve(/* turbopackIgnore: true */ root, key);
  if (!target.startsWith(root + path.sep)) throw new Error(INVALID_PATH);
  return target;
}

export async function readLocalFile(key: string) {
  return readFile(/* turbopackIgnore: true */ resolveLocalPath(key));
}

export const localDriver: StorageDriver = {
  async put(key, data) {
    const target = resolveLocalPath(key);
    await mkdir(/* turbopackIgnore: true */ path.dirname(target), { recursive: true });
    await writeFile(/* turbopackIgnore: true */ target, data);
    return { key, url: `/media/${key}` };
  },
  async delete(key) {
    await rm(/* turbopackIgnore: true */ resolveLocalPath(key), { force: true });
  },
};
