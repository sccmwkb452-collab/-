import { describe, expect, it } from "vitest";
import { formatMoney, formatStars, plural } from "./format";

describe("format", () => {
  it("formats money without floating point surprises", () => {
    expect(formatMoney("169.00", "RUB").replace(/\s/g, " ")).toBe("169 ₽");
    expect(formatMoney("1690.50", "RUB").replace(/\s/g, " ")).toBe("1 690,50 ₽");
    expect(formatMoney(null, "RUB")).toBe("—");
  });
  it("formats stars", () => {
    expect(formatStars(5000).replace(/\s/g, " ")).toBe("5 000");
  });
  it("pluralises in Russian", () => {
    expect(plural(1, ["звезда", "звезды", "звёзд"])).toBe("звезда");
    expect(plural(3, ["звезда", "звезды", "звёзд"])).toBe("звезды");
    expect(plural(11, ["звезда", "звезды", "звёзд"])).toBe("звёзд");
    expect(plural(25, ["звезда", "звезды", "звёзд"])).toBe("звёзд");
  });
});
