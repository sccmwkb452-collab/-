import bcrypt from "bcryptjs";

const ROUNDS = 12;

export function hashPassword(password: string) {
  return bcrypt.hash(password, ROUNDS);
}

export function verifyPassword(password: string, hash: string) {
  return bcrypt.compare(password, hash);
}

let dummy: Promise<string> | null = null;

/** Хеш-заглушка: проверка пароля для несуществующего email занимает столько же времени. */
export function getDummyHash() {
  dummy ??= bcrypt.hash(`dummy-${Math.random()}`, ROUNDS);
  return dummy;
}
