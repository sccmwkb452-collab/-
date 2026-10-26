import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Вход" };

export default function LoginPage() {
  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden px-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_50%_0%,rgb(59_130_246/0.16),transparent_70%),radial-gradient(40%_40%_at_85%_100%,rgb(56_189_248/0.08),transparent_70%)]"
      />
      <Suspense>
        <LoginForm />
      </Suspense>
    </div>
  );
}
