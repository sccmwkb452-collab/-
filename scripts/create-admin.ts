/**
 * Создание администратора или сброс пароля существующего.
 *
 *   npm run admin:create -- --email admin@company.ru --password "Strong-Pass-2026" --name "Иван"
 */
import { PrismaClient } from "@prisma/client";
import bcrypt from "bcryptjs";
import { adminCreateSchema } from "../lib/validation/admin";

function arg(name: string) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

async function main() {
  const parsed = adminCreateSchema.safeParse({
    email: arg("email") ?? process.env.ADMIN_EMAIL,
    password: arg("password") ?? process.env.ADMIN_PASSWORD,
    name: arg("name") ?? process.env.ADMIN_NAME ?? "Администратор",
  });
  if (!parsed.success) {
    process.stderr.write(`Ошибка: ${parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}\n`);
    process.stderr.write('Использование: npm run admin:create -- --email a@b.ru --password "Пароль-2026" --name "Имя"\n');
    process.exit(1);
  }
  const prisma = new PrismaClient();
  const passwordHash = await bcrypt.hash(parsed.data.password, 12);
  const admin = await prisma.admin.upsert({
    where: { email: parsed.data.email },
    update: { passwordHash, name: parsed.data.name },
    create: { email: parsed.data.email, name: parsed.data.name, passwordHash },
  });
  await prisma.adminSession.deleteMany({ where: { adminId: admin.id } });
  await prisma.$disconnect();
  process.stdout.write(`Готово: ${admin.email}\n`);
}

main().catch((error: unknown) => {
  process.stderr.write(`${String(error)}\n`);
  process.exit(1);
});
