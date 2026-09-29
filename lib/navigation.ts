export const MAIN_NAV = [
  { href: "/projects", label: "Проекты" },
  { href: "/calculator", label: "Калькулятор" },
  { href: "/technology", label: "Технологии" },
  { href: "/build", label: "Как строим" },
  { href: "/about", label: "О компании" },
] as const;

export const FOOTER_NAV = [
  ...MAIN_NAV,
  { href: "/faq", label: "Вопросы и ответы" },
  { href: "/contacts", label: "Контакты" },
] as const;
