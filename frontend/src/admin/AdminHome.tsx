import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { firstAllowed } from "./AdminLayout";
import Overview from "./Overview";
import { permissionsFor } from "./permissions";

/** The console's front door: the overview for those who may see it, otherwise their first section. */
export default function AdminHome() {
  const { me } = useAuth();
  const roles = me?.roles ?? [];
  if (!permissionsFor(roles).has("dashboard.view")) return <Navigate to={firstAllowed(roles)} replace />;
  return <Overview />;
}
