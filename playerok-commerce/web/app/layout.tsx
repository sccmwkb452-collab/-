import "@fontsource-variable/inter";
import "./globals.css";

import type { Metadata, Viewport } from "next";
import { Toaster } from "sonner";

export const metadata: Metadata = {
  title: { default: "PlayerOK Commerce", template: "%s · PlayerOK Commerce" },
  description: "Закрытая панель управления магазином на PlayerOK",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#090c12", colorScheme: "dark" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" className="dark">
      <body>
        {children}
        <Toaster
          theme="dark"
          position="bottom-right"
          richColors
          toastOptions={{ style: { background: "#131c30", border: "1px solid rgb(148 163 194 / 0.22)", color: "#e8edf6" } }}
        />
      </body>
    </html>
  );
}
