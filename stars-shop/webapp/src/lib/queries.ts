import type { Bootstrap, Me, OrderDetail, OrderSummary, PaymentInfo, Quote, Ticket } from "@starshop/shared";
import { ACTIVE_STATUSES } from "@starshop/shared";
import { QueryClient, keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, canAuthenticate } from "./api";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 3,
      retryDelay: (attempt) => Math.min(800 * 2 ** attempt, 6000),
    },
    mutations: { retry: false },
  },
});

export const keys = {
  bootstrap: ["bootstrap"] as const,
  me: ["me"] as const,
  orders: (filter: string) => ["orders", filter] as const,
  order: (id: string) => ["order", id] as const,
  tickets: ["tickets"] as const,
  ticket: (id: number) => ["ticket", id] as const,
};

export function useBootstrap() {
  return useQuery({ queryKey: keys.bootstrap, queryFn: () => api<Bootstrap>("/bootstrap", { auth: false }), staleTime: 15_000 });
}

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => api<Me>("/me"), staleTime: 60_000, enabled: canAuthenticate });
}

export function useOrders(filter: string, limit: number, enabled = true) {
  return useQuery({
    queryKey: [...keys.orders(filter), limit],
    queryFn: () => api<{ items: OrderSummary[]; total: number }>(`/orders?status=${filter}&limit=${limit}`),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useOrder(id: string) {
  return useQuery({
    queryKey: keys.order(id),
    queryFn: () => api<OrderDetail>(`/orders/${id}`),
    // Live status while something is still happening.
    refetchInterval: (q) => (q.state.data && ACTIVE_STATUSES.includes(q.state.data.status) ? 4000 : false),
  });
}

export function useQuote(
  input: { product_id: number; stars_amount?: number | null; promo_code?: string; use_bonus?: boolean; payment_provider?: string; lucky?: { chance: number } } | null,
) {
  return useQuery({
    queryKey: ["quote", input],
    queryFn: () => api<Quote>("/orders/quote", { method: "POST", body: input }),
    enabled: canAuthenticate && Boolean(input && input.payment_provider),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    retry: 1,
  });
}

export function useTickets() {
  return useQuery({ queryKey: keys.tickets, queryFn: () => api<{ items: Ticket[] }>("/support/tickets"), enabled: canAuthenticate });
}

export function useTicket(id: number) {
  return useQuery({ queryKey: keys.ticket(id), queryFn: () => api<Ticket>(`/support/tickets/${id}`), refetchInterval: 15_000 });
}

export function useInvalidateOrders() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["orders"] });
    qc.invalidateQueries({ queryKey: keys.me });
  };
}

export function useCreatePayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, provider, clientSeed }: { orderId: string; provider?: string; clientSeed?: string }) =>
      api<PaymentInfo>(`/orders/${orderId}/payment`, { method: "POST", body: { provider, client_seed: clientSeed } }),
    onSuccess: (_, v) => qc.invalidateQueries({ queryKey: keys.order(v.orderId) }),
  });
}
