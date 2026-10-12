import { Construction } from "lucide-react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { EmptyState, PageHeader, useDocumentTitle } from "../ui/blocks";
import { permissionsFor } from "./permissions";
import { flatNav } from "./shell/nav";

/** A page on the console's map that is not built yet, shown honestly rather than hidden. */
export default function Stub() {
  const { pathname } = useLocation();
  const { me } = useAuth();
  const leaf = flatNav(permissionsFor(me?.roles ?? [])).find((p) => p.soon && p.to.split("?")[0] === pathname);
  useDocumentTitle(leaf?.label ?? "Console");
  if (!leaf) return <Navigate to="/admin" replace />;
  return (
    <>
      <PageHeader eyebrow={leaf.group || "Console"} title={leaf.label} lead="This part of the console is planned but not built yet." />
      <EmptyState
        title={`${leaf.label} is on its way`}
        icon={<Construction size={22} strokeWidth={1.5} />}
        action={<Link className="wo-btn wo-btn--primary" to="/admin">Back to the dashboard</Link>}
      >
        Nothing here to manage yet. The rest of the console works as normal.
      </EmptyState>
    </>
  );
}
