/** Lucky Buy fairness check in the browser — the same algorithm as
 * backend/starshop/services/lucky.py:
 *
 *   roll = first 8 bytes of HMAC-SHA256(key = server_seed, msg = `${client_seed}:${order_number}`),
 *          as a big-endian integer, × 10000 >> 64        → 0…9999 (shown as 0.00–99.99)
 *   win  = roll < chance_bp
 *
 * and sha256(server_seed) must equal the hash published before the payment. */

import type { LuckyDraw } from "./types";

const encoder = new TextEncoder();

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function sha256Hex(text: string): Promise<string> {
  return toHex(new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(text))));
}

export async function luckyRoll(serverSeed: string, clientSeed: string, nonce: string): Promise<number> {
  const key = await crypto.subtle.importKey("raw", encoder.encode(serverSeed), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const digest = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(`${clientSeed}:${nonce}`)));
  let head = 0n;
  for (const byte of digest.subarray(0, 8)) head = (head << 8n) | BigInt(byte);
  return Number((head * 10000n) >> 64n);
}

export interface LuckyCheck {
  hashMatches: boolean;
  roll: number;
  rollMatches: boolean;
  outcomeMatches: boolean;
}

/** null until the draw has happened (the server seed is still secret). */
export async function verifyLuckyDraw(draw: LuckyDraw): Promise<LuckyCheck | null> {
  if (!draw.server_seed || !draw.client_seed || draw.roll_bp === null || draw.won === null) return null;
  const [hash, roll] = await Promise.all([sha256Hex(draw.server_seed), luckyRoll(draw.server_seed, draw.client_seed, draw.nonce)]);
  return {
    hashMatches: hash === draw.server_seed_hash,
    roll,
    rollMatches: roll === draw.roll_bp,
    outcomeMatches: roll < draw.chance_bp === draw.won,
  };
}

/** The customer's seed: random, generated on the device before paying. */
export function newClientSeed(): string {
  return toHex(crypto.getRandomValues(new Uint8Array(12)));
}

/** 2987 -> "29.87" */
export function formatRoll(bp: number): string {
  return `${Math.floor(bp / 100)}.${String(bp % 100).padStart(2, "0")}`;
}
