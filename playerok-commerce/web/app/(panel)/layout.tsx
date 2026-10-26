import { Shell } from "@/components/app/shell";
import { SessionProvider } from "@/lib/session";

export default function PanelLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <Shell>{children}</Shell>
    </SessionProvider>
  );
}
