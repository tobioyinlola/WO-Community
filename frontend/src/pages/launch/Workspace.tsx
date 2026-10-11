import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Badge, Button } from "../../components";
import { Loaded, PageHeader, SkeletonRows } from "../../ui/blocks";
import { useDeleteVenture } from "./Ventures";
import { Modal } from "../../components";
import { useState } from "react";

export type Venture = components["schemas"]["TkVenture"];
export type Package = components["schemas"]["TkPackage"];

interface WorkspaceContext {
  ventureId: string;
  venture: Venture;
}

export function useWorkspace(): WorkspaceContext {
  return useOutletContext<WorkspaceContext>();
}

export const packageKey = (id: string) => ["toolkit", id, "package"] as const;

const TABS = [
  { to: "", label: "Overview", end: true },
  { to: "profile", label: "Profile" },
  { to: "score", label: "Score" },
  { to: "plan", label: "Business plan" },
  { to: "forecast", label: "Forecast" },
  { to: "decks", label: "Pitch decks" },
  { to: "prototypes", label: "Prototypes" },
  { to: "partner", label: "Partner" },
  { to: "sharing", label: "Sharing" },
];

export default function Workspace() {
  const { ventureId = "" } = useParams();
  const [confirm, setConfirm] = useState(false);
  const remove = useDeleteVenture(ventureId);
  const venture = useQuery({
    queryKey: ["toolkit", ventureId],
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}", { params: { path: { venture_id: ventureId } } })),
  });
  return (
    <Loaded query={venture} skeleton={<SkeletonRows />}>
      {(v) => (
        <>
          <PageHeader
            eyebrow="Launch toolkit"
            title={v.name}
            lead="Private to you. Nothing here is shown to other members unless you share it."
            actions={<Button variant="ghost" onClick={() => setConfirm(true)}>Delete</Button>}
          />
          <nav className="app-tabs-scroll" aria-label="Venture sections">
            <div className="app-tablinks">
              {TABS.map((t) => (
                <NavLink key={t.label} to={t.to} end={t.end} className="app-tablink">
                  {t.label}
                </NavLink>
              ))}
            </div>
          </nav>
          <Outlet context={{ ventureId, venture: v } satisfies WorkspaceContext} />
          {confirm ? (
            <Modal
              open
              onClose={() => setConfirm(false)}
              eyebrow="Launch toolkit"
              title={`Delete ${v.name}?`}
              actions={
                <>
                  <Button variant="ghost" onClick={() => setConfirm(false)}>Keep it</Button>
                  <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>Delete venture</Button>
                </>
              }
            >
              It is hidden at once and erased for good after 14 days. You can restore it until then.
            </Modal>
          ) : null}
        </>
      )}
    </Loaded>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { v: "success" | "warning" | "info" | "danger" | "neutral"; t: string }> = {
    ready: { v: "success", t: "Ready" },
    needs_refresh: { v: "warning", t: "Out of date" },
    generating: { v: "info", t: "Working" },
    failed: { v: "danger", t: "Failed" },
    not_started: { v: "neutral", t: "Not started" },
  };
  const s = map[status] ?? { v: "neutral" as const, t: status };
  return <Badge variant={s.v} dot>{s.t}</Badge>;
}
