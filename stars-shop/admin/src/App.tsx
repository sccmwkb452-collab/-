import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";
import { Shell } from "./components/Shell";
import { Skeleton } from "./components/ui";
import { can, useAuth } from "./lib/auth";
import { Login } from "./pages/Login";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Orders = lazy(() => import("./pages/Orders"));
const OrderPage = lazy(() => import("./pages/OrderPage"));
const Catalog = lazy(() => import("./pages/Catalog"));
const Users = lazy(() => import("./pages/Users"));
const UserPage = lazy(() => import("./pages/UserPage"));
const Promo = lazy(() => import("./pages/Promo"));
const Referrals = lazy(() => import("./pages/Referrals"));
const Content = lazy(() => import("./pages/Content"));
const Support = lazy(() => import("./pages/Support"));
const TicketPage = lazy(() => import("./pages/TicketPage"));
const Settings = lazy(() => import("./pages/Settings"));
const Audit = lazy(() => import("./pages/Audit"));

function Loading() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-9 w-56" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

export function App() {
  const { state } = useAuth();
  if (state.status === "loading")
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Skeleton className="h-2 w-32" />
      </div>
    );
  if (state.status === "anon") return <Login error={state.error} />;
  const isManager = can(state.admin, "manager");
  return (
    <Shell>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={isManager ? <Dashboard /> : <Navigate to="/orders" replace />} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/orders/:id" element={<OrderPage />} />
          <Route path="/catalog" element={<Catalog />} />
          <Route path="/users" element={<Users />} />
          <Route path="/users/:id" element={<UserPage />} />
          <Route path="/promo" element={<Promo />} />
          <Route path="/referrals" element={<Referrals />} />
          <Route path="/content" element={<Content />} />
          <Route path="/support" element={<Support />} />
          <Route path="/support/:id" element={<TicketPage />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Shell>
  );
}
