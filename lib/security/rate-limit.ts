import "server-only";

interface Bucket {
  hits: number[];
}

const buckets = new Map<string, Bucket>();
let lastSweep = Date.now();

/**
 * Скользящее окно в памяти процесса. Для горизонтального масштабирования
 * замените реализацию на Redis с тем же интерфейсом.
 */
export function rateLimit(key: string, limit: number, windowMs: number) {
  const now = Date.now();
  if (now - lastSweep > 60_000) {
    for (const [k, b] of buckets) {
      if (!b.hits.length || now - b.hits[b.hits.length - 1] > windowMs) buckets.delete(k);
    }
    lastSweep = now;
  }
  const bucket = buckets.get(key) ?? { hits: [] };
  bucket.hits = bucket.hits.filter((t) => now - t < windowMs);
  if (bucket.hits.length >= limit) {
    buckets.set(key, bucket);
    const retryAfter = Math.ceil((windowMs - (now - bucket.hits[0])) / 1000);
    return { ok: false as const, retryAfter };
  }
  bucket.hits.push(now);
  buckets.set(key, bucket);
  return { ok: true as const, remaining: limit - bucket.hits.length };
}
