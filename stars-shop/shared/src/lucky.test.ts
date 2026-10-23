import { describe, expect, it } from "vitest";
import { formatRoll, luckyRoll, newClientSeed, sha256Hex, verifyLuckyDraw } from "./lucky";

// Same vector as backend/tests/test_lucky.py (checked with openssl).
const SERVER_SEED = "9b74c9897bac770ffc029102a200c5de".repeat(2);
const HASH = "69d38f75ec1802034ab2ace92e9c726c2a83a2376119fd30bdf2392970570aa5";

describe("lucky", () => {
  it("reproduces the server's hash and roll", async () => {
    expect(await sha256Hex(SERVER_SEED)).toBe(HASH);
    expect(await luckyRoll(SERVER_SEED, "c0ffee-lucky-42", "7KQ2M9XD")).toBe(2987);
    expect(formatRoll(2987)).toBe("29.87");
    expect(formatRoll(500)).toBe("5.00");
  });

  it("verifies a revealed draw and catches tampering", async () => {
    const draw = {
      chance: "25",
      chance_bp: 2500,
      prize_value: "169.00",
      server_seed_hash: HASH,
      client_seed: "c0ffee-lucky-42",
      nonce: "7KQ2M9XD",
      server_seed: SERVER_SEED,
      roll: "29.87",
      roll_bp: 2987,
      won: false,
      drawn_at: "2026-10-23T20:00:00Z",
    };
    expect(await verifyLuckyDraw(draw)).toEqual({ hashMatches: true, roll: 2987, rollMatches: true, outcomeMatches: true });
    expect((await verifyLuckyDraw({ ...draw, won: true }))?.outcomeMatches).toBe(false);
    expect((await verifyLuckyDraw({ ...draw, server_seed_hash: "0".repeat(64) }))?.hashMatches).toBe(false);
    expect(await verifyLuckyDraw({ ...draw, server_seed: null })).toBeNull();
  });

  it("generates fresh client seeds", () => {
    const a = newClientSeed();
    expect(a).toMatch(/^[0-9a-f]{24}$/);
    expect(newClientSeed()).not.toBe(a);
  });
});
