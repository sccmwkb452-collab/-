import { PrismaClient, type ImageKind, type LeadStatus, type Prisma } from "@prisma/client";
import bcrypt from "bcryptjs";
import { calculateEstimate } from "../lib/pricing/engine";
import type { PricingConfig } from "../lib/pricing/types";

const prisma = new PrismaClient();

const houseTypes = [
  { code: "one-story", name: "Одноэтажный", description: "Всё на одном уровне: удобно для семьи с детьми и старшего поколения", floors: 1, multiplier: 1.08, sortOrder: 1 },
  { code: "two-story", name: "Двухэтажный", description: "Компактное пятно застройки и чёткое зонирование на дневную и ночную зоны", floors: 2, multiplier: 1.0, sortOrder: 2 },
  { code: "mansard", name: "С мансардой", description: "Жилой этаж под кровлей — больше площади при меньшем бюджете", floors: 2, multiplier: 0.96, sortOrder: 3 },
];

const technologies = [
  {
    slug: "gazobeton", name: "Газобетон", pricePerM2: 65000, sortOrder: 1,
    shortDescription: "Тёплый и долговечный каменный дом без лишней нагрузки на фундамент",
    description: "Стены из автоклавного газобетона D500 толщиной 375–400 мм обеспечивают тепловую защиту без дополнительного утепления. Материал не горит, не гниёт и сохраняет геометрию, поэтому дом служит 100 лет и более. Это самая сбалансированная технология по соотношению цены, сроков и эксплуатационных расходов.",
    advantages: ["Не требует дополнительного утепления", "Негорючий материал — класс НГ", "Точная геометрия кладки на клей", "Срок службы более 100 лет"],
    buildTime: "5–7 месяцев", warranty: "10 лет на конструктив",
  },
  {
    slug: "kirpich", name: "Кирпич", pricePerM2: 75000, sortOrder: 2,
    shortDescription: "Классика для тех, кто строит на поколения вперёд",
    description: "Несущие стены из керамического поризованного блока с облицовкой клинкерным кирпичом. Максимальная прочность, звукоизоляция и архитектурная выразительность фасада, который не требует обслуживания десятилетиями.",
    advantages: ["Фасад без обслуживания", "Высокая тепловая инерция", "Отличная звукоизоляция", "Максимальная ликвидность при продаже"],
    buildTime: "7–10 месяцев", warranty: "15 лет на конструктив",
  },
  {
    slug: "karkas", name: "Каркас", pricePerM2: 55000, sortOrder: 3,
    shortDescription: "Быстрое строительство и высокая энергоэффективность",
    description: "Каркас из камерной сушки строганой доски 45×195 мм с утеплением минеральной ватой 200–250 мм и ветро-влагозащитными мембранами. Дом собирается за один сезон и дёшев в отоплении.",
    advantages: ["Строительство за 3–4 месяца", "Лёгкий фундамент", "Низкие расходы на отопление", "Можно строить круглый год"],
    buildTime: "3–4 месяца", warranty: "7 лет на конструктив",
  },
  {
    slug: "brus", name: "Клеёный брус", pricePerM2: 85000, sortOrder: 4,
    shortDescription: "Натуральное дерево без усадки и трещин",
    description: "Стеновой комплект из клеёного бруса северной сосны 200 мм, изготовленный на ЧПУ по проекту. Минимальная усадка позволяет начинать отделку сразу после сборки, а натуральная древесина создаёт особый микроклимат.",
    advantages: ["Минимальная усадка — до 1%", "Не требует внутренней отделки", "Экологичный микроклимат", "Сборка стенового комплекта за 3–4 недели"],
    buildTime: "4–6 месяцев", warranty: "10 лет на конструктив",
  },
];

const packages = [
  { code: "box", name: "Коробка", multiplier: 0.65, sortOrder: 1, description: "Надёжная основа дома: фундамент, стены, перекрытия и кровля", includes: ["Геология и проект КЖ", "Фундамент", "Несущие стены и перегородки", "Перекрытия и лестница", "Кровля с водосточной системой"] },
  { code: "warm", name: "Тёплый контур", multiplier: 0.8, sortOrder: 2, description: "Закрытый и утеплённый дом, готовый к инженерным работам", includes: ["Всё из «Коробки»", "Окна с двухкамерным стеклопакетом", "Входная дверь", "Утепление кровли и фасада", "Фасадная отделка"] },
  { code: "prefinish", name: "Под чистовую", multiplier: 0.92, sortOrder: 3, description: "Инженерия и черновая отделка — остаётся только выбрать чистовые материалы", includes: ["Всё из «Тёплого контура»", "Разводка электрики", "Отопление и водоснабжение", "Канализация и вентиляция", "Стяжка и штукатурка"] },
  { code: "turnkey", name: "Под ключ", multiplier: 1.0, sortOrder: 4, description: "Готовый к жизни дом с чистовой отделкой и сантехникой", includes: ["Всё из «Под чистовую»", "Чистовая отделка стен и пола", "Межкомнатные двери", "Сантехника и освещение", "Уборка и передача ключей"] },
];

const options = [
  { code: "terrace", name: "Терраса", description: "Открытая терраса 20–25 м² из лиственницы", pricingType: "FIXED" as const, price: 350000 },
  { code: "garage", name: "Гараж", description: "Пристроенный гараж на 1 автомобиль с воротами", pricingType: "FIXED" as const, price: 900000 },
  { code: "panoramic-windows", name: "Панорамные окна", description: "Остекление в пол с тёплым алюминиевым профилем", pricingType: "FIXED" as const, price: 250000 },
  { code: "second-light", name: "Второй свет", description: "Гостиная высотой в два этажа", pricingType: "FIXED" as const, price: 280000 },
  { code: "fireplace", name: "Камин", description: "Каминная топка с дымоходом из сэндвич-трубы", pricingType: "FIXED" as const, price: 180000 },
  { code: "carport", name: "Навес", description: "Навес для двух автомобилей на металлокаркасе", pricingType: "FIXED" as const, price: 220000 },
  { code: "underfloor-heating", name: "Тёплый пол", description: "Водяной тёплый пол на первом этаже", pricingType: "PER_M2" as const, price: 1800 },
  { code: "engineering", name: "Инженерные системы", description: "Котельная, водоподготовка, вентиляция с рекуперацией", pricingType: "PER_M2" as const, price: 4500 },
  { code: "sauna", name: "Сауна", description: "Финская сауна в доме с комнатой отдыха", pricingType: "FIXED" as const, price: 450000 },
  { code: "smart-home", name: "Умный дом", description: "Управление светом, климатом и безопасностью", pricingType: "FIXED" as const, price: 320000 },
  { code: "well", name: "Скважина", description: "Скважина на известняк до 60 м с обустройством", pricingType: "FIXED" as const, price: 280000 },
  { code: "septic", name: "Септик", description: "Станция биологической очистки под ключ", pricingType: "FIXED" as const, price: 190000 },
];

const priceSettings = [
  { key: "area_min", label: "Минимальная площадь", description: "Нижняя граница слайдера в калькуляторе", value: 50, unit: "м²", sortOrder: 1 },
  { key: "area_max", label: "Максимальная площадь", description: "Верхняя граница слайдера в калькуляторе", value: 400, unit: "м²", sortOrder: 2 },
  { key: "bedroom_base_count", label: "Спален в базовой цене", description: "Сколько спален входит в цену за м² без надбавки", value: 3, unit: "шт.", sortOrder: 3 },
  { key: "bedroom_surcharge", label: "Надбавка за доп. спальню", description: "Перегородки, двери, электрика для каждой спальни сверх базовых", value: 150000, unit: "₽", sortOrder: 4 },
  { key: "rounding_step", label: "Шаг округления", description: "До какой суммы округлять итоговую стоимость", value: 10000, unit: "₽", sortOrder: 5 },
  { key: "estimate_spread_percent", label: "Диапазон точности", description: "Разброс «от — до» вокруг расчётной стоимости", value: 7, unit: "%", sortOrder: 6 },
];

interface ProjectSeed {
  slug: string;
  title: string;
  subtitle: string;
  description: string;
  area: number;
  bedrooms: number;
  bathrooms: number;
  houseType: string;
  technology: string;
  dimensions: string;
  ceilingHeight: number;
  hasGarage?: boolean;
  hasTerrace?: boolean;
  hasOffice?: boolean;
  hasSecondLight?: boolean;
  hasPanoramicWindows?: boolean;
  features: string[];
  featured?: boolean;
  status?: "DRAFT" | "PUBLISHED" | "HIDDEN";
  plans: number;
}

const projects: ProjectSeed[] = [
  {
    slug: "dom-artem", title: "Дом «Артем»", subtitle: "Современный двухэтажный дом со вторым светом",
    description: "«Артем» — дом для семьи, которая ценит простор и свет. Сердце дома — кухня-гостиная со столовой под вторым светом и панорамным остеклением на террасу. На первом этаже предусмотрен кабинет, который легко превращается в гостевую спальню. Второй этаж — приватная зона: мастер-спальня с гардеробной, две детские и постирочная рядом со спальнями.",
    area: 156, bedrooms: 4, bathrooms: 2, houseType: "two-story", technology: "gazobeton", dimensions: "11,6 × 10,6 м", ceilingHeight: 3.0,
    hasTerrace: true, hasOffice: true, hasSecondLight: true, hasPanoramicWindows: true, featured: true, plans: 2,
    features: ["Кухня-гостиная 34 м² с выходом на террасу", "Столовая со вторым светом", "Мастер-спальня с гардеробной", "Постирочная на втором этаже", "Котельная с отдельным входом"],
  },
  {
    slug: "dom-nordik", title: "Дом «Нордик»", subtitle: "Барнхаус для загородной жизни круглый год",
    description: "Лаконичный барнхаус с высоким потолком в гостиной и большой террасой вдоль фасада. Продуманная планировка на 98 м² вмещает две спальни, просторную кухню-гостиную и кладовую — всё, что нужно для комфортной жизни за городом без лишних квадратных метров.",
    area: 98, bedrooms: 2, bathrooms: 1, houseType: "one-story", technology: "karkas", dimensions: "14,0 × 7,2 м", ceilingHeight: 2.8,
    hasTerrace: true, hasPanoramicWindows: true, plans: 1, featured: true,
    features: ["Потолок до конька в гостиной", "Терраса вдоль всего фасада", "Кладовая и гардероб", "Минимальные эксплуатационные расходы"],
  },
  {
    slug: "dom-lesnoy", title: "Дом «Лесной»", subtitle: "Дом из клеёного бруса с мансардой",
    description: "Тёплый деревянный дом с мансардным этажом и большим витражом в гостиной. Внизу — открытая гостиная с кухней и выходом на крытую террасу, наверху — три спальни и санузел. Идеален для участка в лесу или у воды.",
    area: 132, bedrooms: 3, bathrooms: 2, houseType: "mansard", technology: "brus", dimensions: "9,6 × 8,0 м", ceilingHeight: 2.9,
    hasTerrace: true, hasPanoramicWindows: true, plans: 2, featured: true,
    features: ["Витраж на два уровня", "Крытая терраса 28 м²", "Три спальни на мансарде", "Натуральная древесина внутри"],
  },
  {
    slug: "dom-grafit", title: "Дом «Графит»", subtitle: "Кирпичный дом с гаражом и кабинетом",
    description: "Солидный двухэтажный дом для большой семьи. Встроенный гараж с тамбуром, кабинет и гостевая спальня на первом этаже, гостиная со вторым светом и четыре спальни наверху. Клинкерный фасад не требует ухода десятилетиями.",
    area: 214, bedrooms: 5, bathrooms: 3, houseType: "two-story", technology: "kirpich", dimensions: "15,8 × 11,0 м", ceilingHeight: 3.0,
    hasGarage: true, hasOffice: true, hasSecondLight: true, hasPanoramicWindows: true, plans: 2, featured: true,
    features: ["Встроенный гараж с тамбуром", "Гостиная со вторым светом", "Кабинет на первом этаже", "Три санузла", "Клинкерный фасад"],
  },
  {
    slug: "dom-gorizont", title: "Дом «Горизонт»", subtitle: "Одноэтажный дом с плоской кровлей",
    description: "Протяжённый одноэтажный дом с панорамным остеклением гостиной и крытой террасой. Все помещения на одном уровне: удобно для семьи с маленькими детьми и старшего поколения. Гараж встроен в объём дома.",
    area: 148, bedrooms: 3, bathrooms: 2, houseType: "one-story", technology: "gazobeton", dimensions: "18,4 × 10,6 м", ceilingHeight: 3.0,
    hasGarage: true, hasTerrace: true, hasPanoramicWindows: true, plans: 1,
    features: ["Без лестниц — всё на одном уровне", "Панорамная гостиная 43 м²", "Мастер-спальня с санузлом", "Встроенный гараж"],
  },
  {
    slug: "dom-skandi", title: "Дом «Сканди»", subtitle: "Компактный каркасный дом с мансардой",
    description: "Светлый дом в скандинавском стиле: минимум площади, максимум пользы. Большая кухня-гостиная и спальня внизу, две спальни на мансарде. Каркасная технология позволяет заехать в дом уже через четыре месяца.",
    area: 118, bedrooms: 3, bathrooms: 2, houseType: "mansard", technology: "karkas", dimensions: "8,4 × 8,4 м", ceilingHeight: 2.7,
    hasTerrace: true, plans: 2,
    features: ["Спальня на первом этаже", "Крытая терраса", "Строительство за 4 месяца", "Низкие расходы на отопление"],
  },
  {
    slug: "dom-rezidentsiya", title: "Дом «Резиденция»", subtitle: "Представительский дом с гаражом на 2 авто",
    description: "Большой дом для тех, кто не идёт на компромиссы. Гостиная с двусветным пространством, кухня-столовая с выходом на террасу, кабинет и мастерская. На втором этаже — мастер-блок с гардеробной и собственным санузлом, три спальни и постирочная.",
    area: 286, bedrooms: 5, bathrooms: 4, houseType: "two-story", technology: "kirpich", dimensions: "21,6 × 11,4 м", ceilingHeight: 3.2,
    hasGarage: true, hasTerrace: true, hasOffice: true, hasSecondLight: true, hasPanoramicWindows: true, plans: 2,
    features: ["Гараж на два автомобиля", "Двусветная гостиная", "Мастер-блок с гардеробной", "Кабинет и мастерская", "Четыре санузла"],
  },
  {
    slug: "dom-kubik", title: "Дом «Кубик»", subtitle: "Компактный дом для старта за городом",
    description: "Современный одноэтажный дом площадью 86 м² — рациональный выбор для молодой семьи или дома выходного дня. Две спальни, кухня-гостиная с выходом на террасу и кладовая. Минимальный бюджет без потери качества.",
    area: 86, bedrooms: 2, bathrooms: 1, houseType: "one-story", technology: "gazobeton", dimensions: "9,8 × 8,8 м", ceilingHeight: 2.8,
    hasPanoramicWindows: true, plans: 1,
    features: ["Минимальный бюджет", "Кухня-гостиная с выходом в сад", "Кладовая", "Подходит для узкого участка"],
  },
  {
    slug: "dom-riviera", title: "Дом «Ривьера»", subtitle: "Одноэтажный дом с односкатной кровлей",
    description: "Проект в разработке: одноэтажный дом с односкатной кровлей, большой террасой и двумя санузлами.",
    area: 124, bedrooms: 3, bathrooms: 2, houseType: "one-story", technology: "brus", dimensions: "12,6 × 10,8 м", ceilingHeight: 3.0,
    hasTerrace: true, hasPanoramicWindows: true, plans: 1, status: "DRAFT",
    features: ["Односкатная кровля", "Большая терраса", "Два санузла"],
  },
];

const faqs = [
  { category: "general", question: "Насколько точен расчёт в калькуляторе?", answer: "Калькулятор даёт предварительную стоимость с точностью ±5–10%. Итоговая смета зависит от геологии участка, выбранного проекта, инженерных решений и отделочных материалов. После заявки инженер подготовит подробную смету бесплатно." },
  { category: "general", question: "Можно ли изменить планировку типового проекта?", answer: "Да. Мы бесплатно вносим изменения в планировку: переносим перегородки, меняем размеры окон, добавляем кабинет или гардеробную. Серьёзные изменения несущих конструкций согласуем с конструктором." },
  { category: "general", question: "Цена в договоре фиксированная?", answer: "Да. Стоимость фиксируется в договоре на весь срок строительства и не меняется, если вы не вносите изменения в проект или комплектацию." },
  { category: "construction", question: "Сколько времени занимает строительство?", answer: "Каркасный дом — 3–4 месяца, дом из клеёного бруса — 4–6 месяцев, газобетон — 5–7 месяцев, кирпичный дом — 7–10 месяцев. Сроки прописываются в договоре с графиком этапов." },
  { category: "construction", question: "Как контролировать ход строительства?", answer: "За каждым объектом закреплён технический надзор. Еженедельно вы получаете фото- и видеоотчёт, а оплата производится поэтапно — только после приёмки выполненного этапа." },
  { category: "construction", question: "Строите ли вы зимой?", answer: "Да. Каркасные дома и дома из клеёного бруса можно строить круглый год. Для каменных домов зимой применяем противоморозные добавки и прогрев — это закладывается в смету заранее." },
  { category: "payment", question: "Можно ли построить дом в ипотеку?", answer: "Да, мы аккредитованы в крупных банках и помогаем оформить ипотеку на ИЖС, в том числе семейную и сельскую. Оплата производится через эскроу-счёт." },
  { category: "payment", question: "Какая гарантия на дом?", answer: "Гарантия на конструктив — от 7 до 15 лет в зависимости от технологии, на инженерные системы и отделку — 2 года. Гарантийные обязательства прописаны в договоре." },
  { category: "general", question: "Работаете ли вы с моим участком?", answer: "Мы работаем в Москве, Московской и соседних областях. Перед началом проектирования бесплатно выезжаем на участок, оцениваем подъезды, рельеф и коммуникации." },
];

async function main() {
  const email = process.env.SEED_ADMIN_EMAIL || "admin@forma-house.ru";
  const password = process.env.SEED_ADMIN_PASSWORD || "ChangeMe-2026!";

  await prisma.$transaction([
    prisma.leadEvent.deleteMany(),
    prisma.lead.deleteMany(),
    prisma.calculation.deleteMany(),
    prisma.projectImage.deleteMany(),
    prisma.project.deleteMany(),
    prisma.houseType.deleteMany(),
    prisma.technology.deleteMany(),
    prisma.completionPackage.deleteMany(),
    prisma.option.deleteMany(),
    prisma.priceSetting.deleteMany(),
    prisma.faq.deleteMany(),
    prisma.siteSetting.deleteMany(),
  ]);

  await prisma.admin.upsert({
    where: { email },
    update: {},
    create: { email, name: "Администратор", passwordHash: await bcrypt.hash(password, 12) },
  });

  await prisma.siteSetting.create({
    data: {
      id: 1,
      companyName: "FORMA HOUSE",
      slogan: "Дома, созданные для жизни",
      description: "Мы строим загородные дома с полным сопровождением — от выбора проекта до передачи ключей.",
      phone: "+7 (495) 120-45-67",
      email: "hello@forma-house.ru",
      address: "Москва, Пресненская наб., 12, офис 1804",
      workingHours: "Ежедневно с 9:00 до 21:00",
      telegram: "https://t.me/formahouse",
      whatsapp: "https://wa.me/74951204567",
      vk: "https://vk.com/formahouse",
      primaryColor: "#171717",
      accentColor: "#A47B45",
      footerText: "Демонстрационный сайт строительной компании. Информация на сайте не является публичной офертой.",
      seoTitle: "FORMA HOUSE — строительство частных домов под ключ",
      seoDescription: "Каталог проектов домов, онлайн-конструктор и калькулятор стоимости строительства. Газобетон, кирпич, каркас, клеёный брус. Фиксированная цена в договоре.",
    },
  });

  await prisma.houseType.createMany({ data: houseTypes });
  await prisma.technology.createMany({ data: technologies });
  await prisma.completionPackage.createMany({ data: packages });
  await prisma.option.createMany({ data: options.map((o, i) => ({ ...o, sortOrder: i + 1 })) });
  await prisma.priceSetting.createMany({ data: priceSettings });
  await prisma.faq.createMany({ data: faqs.map((f, i) => ({ ...f, sortOrder: i + 1 })) });

  const config: PricingConfig = {
    houseTypes: houseTypes.map((h) => ({ ...h })),
    technologies: technologies.map((t) => ({ slug: t.slug, name: t.name, shortDescription: t.shortDescription, pricePerM2: t.pricePerM2 })),
    packages: packages.map((p) => ({ ...p })),
    options: options.map((o) => ({ ...o })),
    params: { areaMin: 50, areaMax: 400, bedroomBaseCount: 3, bedroomSurcharge: 150000, roundingStep: 10000, spreadPercent: 7 },
  };

  const htMap = new Map((await prisma.houseType.findMany()).map((h) => [h.code, h.id]));
  const techMap = new Map((await prisma.technology.findMany()).map((t) => [t.slug, t.id]));
  const projectIds = new Map<string, string>();

  for (const [index, p] of projects.entries()) {
    const priceFrom = calculateEstimate(config, {
      houseType: p.houseType, area: p.area, bedrooms: p.bedrooms, technology: p.technology, package: "warm", options: [],
    }).total;
    const base = `/demo/projects/${p.slug}`;
    const images: { url: string; kind: ImageKind; alt: string; sortOrder: number; width: number; height: number }[] = [
      { url: `${base}/cover.webp`, kind: "COVER", alt: `${p.title} — фасад`, sortOrder: 0, width: 1600, height: 1000 },
      { url: `${base}/gallery-1.webp`, kind: "GALLERY", alt: `${p.title} — вечерняя визуализация`, sortOrder: 1, width: 1600, height: 1000 },
      { url: `${base}/gallery-2.webp`, kind: "GALLERY", alt: `${p.title} — вид с участка`, sortOrder: 2, width: 1600, height: 1000 },
      { url: `${base}/gallery-3.webp`, kind: "GALLERY", alt: `${p.title} — фрагмент фасада`, sortOrder: 3, width: 1600, height: 1000 },
      ...Array.from({ length: p.plans }, (_, i) => ({
        url: `${base}/plan-${i + 1}.webp`, kind: "PLAN" as const, alt: `${p.title} — планировка, лист ${i + 1}`, sortOrder: i, width: 1600, height: 1100,
      })),
    ];
    const created = await prisma.project.create({
      data: {
        slug: p.slug, title: p.title, subtitle: p.subtitle, description: p.description,
        area: p.area, bedrooms: p.bedrooms, bathrooms: p.bathrooms,
        houseTypeId: htMap.get(p.houseType) as string,
        technologyId: techMap.get(p.technology) ?? null,
        priceFrom, dimensions: p.dimensions, ceilingHeight: p.ceilingHeight,
        hasGarage: Boolean(p.hasGarage), hasTerrace: Boolean(p.hasTerrace), hasOffice: Boolean(p.hasOffice),
        hasSecondLight: Boolean(p.hasSecondLight), hasPanoramicWindows: Boolean(p.hasPanoramicWindows),
        features: p.features, featured: Boolean(p.featured), status: p.status ?? "PUBLISHED", sortOrder: index + 1,
        seoTitle: `${p.title} — ${p.area} м², проект и стоимость строительства`,
        seoDescription: `${p.subtitle}. ${p.area} м², ${p.bedrooms} спальни, ${p.bathrooms} санузла. Рассчитайте стоимость строительства онлайн.`,
        images: { create: images },
      },
    });
    projectIds.set(p.slug, created.id);
  }

  const now = Date.now();
  const day = 24 * 60 * 60 * 1000;
  const demoLeads: {
    name: string; phone: string; email?: string; telegram?: string; comment?: string; region?: string; budget?: string;
    project?: string; houseType: string; area: number; bedrooms: number; technology: string; pkg: string; options: string[];
    period: string; status: LeadStatus; daysAgo: number; managerComment?: string; source: "CALCULATOR" | "PROJECT" | "CONTACT_FORM";
  }[] = [
    { name: "Демо: Иван", phone: "+79161234567", email: "demo.ivan@example.com", region: "Истринский р-н", budget: "10-15", project: "dom-artem", houseType: "two-story", area: 156, bedrooms: 4, technology: "gazobeton", pkg: "turnkey", options: ["terrace", "second-light", "panoramic-windows"], period: "3m", status: "NEW", daysAgo: 0, source: "CALCULATOR", comment: "Участок 12 соток, есть газ и электричество." },
    { name: "Демо: Мария", phone: "+79031112233", telegram: "@demo_maria", region: "Дмитров", budget: "5-10", project: "dom-skandi", houseType: "mansard", area: 118, bedrooms: 3, technology: "karkas", pkg: "prefinish", options: ["terrace", "underfloor-heating"], period: "3-6m", status: "NEW", daysAgo: 1, source: "CALCULATOR" },
    { name: "Демо: Алексей", phone: "+79265554433", email: "demo.alex@example.com", region: "Новая Москва", budget: "15-25", project: "dom-grafit", houseType: "two-story", area: 214, bedrooms: 5, technology: "kirpich", pkg: "turnkey", options: ["garage", "fireplace", "engineering", "smart-home"], period: "3m", status: "IN_PROGRESS", daysAgo: 2, source: "CALCULATOR", managerComment: "Перезвонить после 18:00, хочет встречу в офисе." },
    { name: "Демо: Ольга", phone: "+79157778899", region: "Звенигород", budget: "10-15", houseType: "one-story", area: 140, bedrooms: 3, technology: "brus", pkg: "warm", options: ["terrace", "sauna"], period: "6-12m", status: "CONTACTED", daysAgo: 3, source: "CALCULATOR" },
    { name: "Демо: Сергей", phone: "+79099990011", email: "demo.sergey@example.com", budget: "gt25", project: "dom-rezidentsiya", houseType: "two-story", area: 286, bedrooms: 5, technology: "kirpich", pkg: "turnkey", options: ["garage", "terrace", "second-light", "engineering", "smart-home", "well", "septic"], period: "3-6m", status: "CALCULATION", daysAgo: 5, source: "CALCULATOR", managerComment: "Готовим подробную смету, выезд на участок согласован." },
    { name: "Демо: Екатерина", phone: "+79214445566", region: "Солнечногорск", budget: "5-10", project: "dom-nordik", houseType: "one-story", area: 98, bedrooms: 2, technology: "karkas", pkg: "turnkey", options: ["terrace", "carport"], period: "3m", status: "CONTRACT", daysAgo: 8, source: "PROJECT", managerComment: "Договор подписан, старт работ в следующем месяце." },
    { name: "Демо: Дмитрий", phone: "+79687776655", houseType: "mansard", area: 132, bedrooms: 3, technology: "brus", pkg: "box", options: [], period: "research", status: "REJECTED", daysAgo: 10, source: "CALCULATOR", managerComment: "Отложил строительство на следующий год." },
    { name: "Демо: Анна", phone: "+79853332211", email: "demo.anna@example.com", region: "Руза", budget: "10-15", project: "dom-gorizont", houseType: "one-story", area: 148, bedrooms: 3, technology: "gazobeton", pkg: "turnkey", options: ["garage", "terrace", "panoramic-windows", "underfloor-heating"], period: "6-12m", status: "COMPLETED", daysAgo: 13, source: "CALCULATOR" },
    { name: "Демо: Павел", phone: "+79112223344", houseType: "one-story", area: 86, bedrooms: 2, technology: "gazobeton", pkg: "prefinish", options: ["terrace"], period: "3-6m", status: "NEW", daysAgo: 0, source: "CALCULATOR" },
  ];

  for (const l of demoLeads) {
    const createdAt = new Date(now - l.daysAgo * day - Math.floor(l.daysAgo * 3.7) * 60 * 60 * 1000);
    const estimate = calculateEstimate(config, {
      houseType: l.houseType, area: l.area, bedrooms: l.bedrooms, technology: l.technology, package: l.pkg, options: l.options,
    });
    const projectId = l.project ? projectIds.get(l.project) ?? null : null;
    const input: Prisma.InputJsonValue = {
      houseType: l.houseType, area: l.area, bedrooms: l.bedrooms, technology: l.technology, package: l.pkg, options: l.options, period: l.period,
    };
    const calc = await prisma.calculation.create({
      data: { createdAt, input, breakdown: estimate, estimatedPrice: estimate.total, projectId },
    });
    const events: Prisma.LeadEventCreateWithoutLeadInput[] = [{ type: "CREATED", message: "Заявка создана", createdAt }];
    if (l.status !== "NEW") {
      events.push({ type: "STATUS_CHANGED", fromStatus: "NEW", toStatus: l.status, createdAt: new Date(createdAt.getTime() + 2 * 60 * 60 * 1000) });
    }
    if (l.managerComment) {
      events.push({ type: "COMMENT", message: l.managerComment, createdAt: new Date(createdAt.getTime() + 3 * 60 * 60 * 1000) });
    }
    await prisma.lead.create({
      data: {
        createdAt, name: l.name, phone: l.phone, email: l.email, telegram: l.telegram, comment: l.comment, region: l.region, budget: l.budget,
        houseType: estimate.labels.houseType, area: l.area, bedrooms: l.bedrooms, technology: estimate.labels.technology,
        package: estimate.labels.package, options: estimate.options.map((o) => o.label), estimatedPrice: estimate.total,
        constructionPeriod: l.period, breakdown: estimate, projectId, calculationId: calc.id,
        status: l.status, source: l.source, managerComment: l.managerComment, consentAt: createdAt,
        events: { create: events },
      },
    });
  }

  const extraCalcs = 38;
  for (let i = 0; i < extraCalcs; i++) {
    const tech = technologies[i % technologies.length];
    const ht = houseTypes[i % houseTypes.length];
    const pkg = packages[(i * 3) % packages.length];
    const area = 80 + ((i * 37) % 200);
    const estimate = calculateEstimate(config, { houseType: ht.code, area, bedrooms: 2 + (i % 4), technology: tech.slug, package: pkg.code, options: i % 2 ? ["terrace"] : [] });
    await prisma.calculation.create({
      data: {
        createdAt: new Date(now - (i % 14) * day - (i % 7) * 60 * 60 * 1000),
        input: { houseType: ht.code, area, bedrooms: 2 + (i % 4), technology: tech.slug, package: pkg.code, options: i % 2 ? ["terrace"] : [], period: "research" },
        breakdown: estimate,
        estimatedPrice: estimate.total,
      },
    });
  }

  process.stdout.write(`Seed завершён. Администратор: ${email}\n`);
}

main()
  .catch((error: unknown) => {
    process.stderr.write(`${String(error)}\n`);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
