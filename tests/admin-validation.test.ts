import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { projectSchema, settingsSchema } from "../lib/validation/admin";

describe("админ-схемы", () => {
  it("принимают собственный результат (клиент валидирует, сервер валидирует повторно)", () => {
    const input = {
      title: "Дом «Тест»", slug: "dom-test", subtitle: "", description: "Описание проекта для проверки",
      area: "120", bedrooms: "3", bathrooms: "2", houseTypeId: "ht1", technologyId: "none", priceFrom: "7000000",
      dimensions: "", ceilingHeight: "", hasGarage: false, hasTerrace: true, hasOffice: false, hasSecondLight: false,
      hasPanoramicWindows: false, featuresText: "Терраса\nКамин", status: "DRAFT", featured: false, sortOrder: "10",
      seoTitle: "", seoDescription: "",
    };
    const first = projectSchema.parse(input);
    assert.equal(first.technologyId, null);
    assert.equal(first.subtitle, null);
    assert.equal(first.ceilingHeight, null);
    assert.deepEqual(projectSchema.parse(first), first);
  });

  it("отклоняет некорректный slug и цвет", () => {
    assert.equal(projectSchema.shape.slug.safeParse("Дом 1").success, false);
    assert.equal(settingsSchema.shape.accentColor.safeParse("red").success, false);
    assert.equal(settingsSchema.shape.telegram.safeParse("javascript:alert(1)").success, false);
  });
});
