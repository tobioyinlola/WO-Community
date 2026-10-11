import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { isStatus } from "./api/errors";
import { AuthProvider } from "./auth/AuthProvider";
import { GuestOnly, RequireAuth } from "./auth/guards";
import { AppLayout } from "./layouts/AppLayout";
import { AuthLayout } from "./layouts/AuthLayout";
import { PublicLayout } from "./layouts/PublicLayout";
import { Design } from "./pages/Design";
import { ForgotPassword, ResetPassword, VerifyEmail } from "./pages/auth/Recovery";
import { Login } from "./pages/auth/Login";
import { Register } from "./pages/auth/Register";
import { Explore } from "./pages/public/Explore";
import { Landing } from "./pages/public/Landing";
import { Legal } from "./pages/public/Legal";
import { NewsItem, NewsList } from "./pages/public/News";
import { Skeleton } from "./ui/blocks";
import { ToastProvider } from "./ui/Toast";

const Home = lazy(() => import("./pages/app/Home"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // A refused or missing request will not succeed on a second try; a dropped connection may.
      retry: (count, error) => !isStatus(error, 400, 401, 403, 404, 409, 412, 422, 429) && count < 2,
    },
  },
});

function Fallback() {
  return (
    <div className="app-stack" role="status" aria-label="Loading">
      <Skeleton width="30%" height={28} />
      <Skeleton />
      <Skeleton width="70%" />
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <Suspense fallback={<Fallback />}>
              <Routes>
                <Route element={<PublicLayout />}>
                  <Route index element={<Landing />} />
                  <Route path="explore" element={<Explore />} />
                  <Route path="news" element={<NewsList />} />
                  <Route path="news/:slug" element={<NewsItem />} />
                  <Route path="legal/:doc" element={<Legal />} />
                  <Route path="design" element={<Design />} />
                </Route>
                <Route element={<GuestOnly />}>
                  <Route element={<AuthLayout />}>
                    <Route path="login" element={<Login />} />
                    <Route path="register" element={<Register />} />
                    <Route path="verify-email" element={<VerifyEmail />} />
                    <Route path="forgot-password" element={<ForgotPassword />} />
                    <Route path="reset-password" element={<ResetPassword />} />
                  </Route>
                </Route>
                <Route element={<RequireAuth />}>
                  <Route path="app" element={<AppLayout />}>
                    <Route index element={<Home />} />
                  </Route>
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
