import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import { Skeleton } from "../ui/blocks";

function Splash() {
  return (
    <div style={{ padding: "var(--space-24) var(--page-margin)", maxWidth: 480, margin: "0 auto" }} role="status" aria-label="Loading">
      <div className="app-stack">
        <Skeleton width="60%" height={28} />
        <Skeleton />
        <Skeleton width="80%" />
      </div>
    </div>
  );
}

/** Sends visitors to sign in, and brings them back to where they were headed afterwards. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <Splash />;
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}

/** The sign in and registration screens are for people who are not signed in. */
export function GuestOnly() {
  const { status } = useAuth();
  if (status === "loading") return <Splash />;
  return <Outlet />;
}
