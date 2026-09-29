import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { contactFieldsSchema, leadRequestSchema } from "../lib/validation/lead";

const contact = { name: "Иван", phone: "+7 (916) 123-45-67", consent: true };

describe("валидация заявки", () => {
  it("принимает корректные контакты", () => {
    const r = contactFieldsSchema.safeParse({ ...contact, email: "Ivan@Mail.ru", telegram: "ivan_petrov" });
    assert.ok(r.success);
    assert.equal(r.data.email, "ivan@mail.ru");
    assert.equal(r.data.telegram, "@ivan_petrov");
  });

  it("отклоняет неверный телефон и отсутствие согласия", () => {
    assert.equal(contactFieldsSchema.safeParse({ ...contact, phone: "12345" }).success, false);
    assert.equal(contactFieldsSchema.safeParse({ ...contact, phone: "abc-def-ghij" }).success, false);
    assert.equal(contactFieldsSchema.safeParse({ ...contact, consent: false }).success, false);
  });

  it("проверяет параметры калькулятора", () => {
    const ok = leadRequestSchema.safeParse({
      source: "CALCULATOR",
      calculator: { houseType: "two-story", area: 150, bedrooms: 3, technology: "gazobeton", package: "turnkey", options: [], period: "3m" },
      contact,
    });
    assert.ok(ok.success);
    const bad = leadRequestSchema.safeParse({
      source: "CALCULATOR",
      calculator: { houseType: "two-story", area: 5000, bedrooms: 3, technology: "gazobeton", package: "turnkey", options: [], period: "never" },
      contact,
    });
    assert.equal(bad.success, false);
  });
});
