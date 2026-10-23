import { useQuery } from "@tanstack/react-query";

/** Public shop config (currency, bot) — same endpoint the Mini App uses. */
export function useShop() {
  const q = useQuery({
    queryKey: ["shop-public"],
    queryFn: async () => {
      const r = await fetch("/api/v1/bootstrap");
      if (!r.ok) throw new Error("bootstrap failed");
      return (await r.json()) as { currency: string; bot_username: string | null; timezone: string };
    },
    staleTime: 5 * 60_000,
  });
  return { currency: q.data?.currency ?? "RUB", botUsername: q.data?.bot_username ?? null, timezone: q.data?.timezone };
}
