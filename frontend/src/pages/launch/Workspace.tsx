import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Alert, Badge, Button } from "../../components";
import { useToolkitConfig } from "./config";
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

/** The tabs, with the switch that turns each tool on or off. The partner is all AI conversation. */
const TABS: Array<{ to: string; label: string; end?: boolean; feature?: string; needsAi?: boolean }> = [
  { to: "", label: "Overview", end: true },
  { to: "profile", label: "Profile" },
  { to: "score", label: "Score", feature: "score" },
  { to: "plan", label: "Business plan", feature: "plan" },
  { to: "forecast", label: "Forecast", feature: "forecast" },
  { to: "decks", label: "Pitch decks", feature: "decks" },
  { to: "prototypes", label: "Prototypes", feature: "prototypes" },
  { to: "partner", label: "Partner", feature: "partner", needsAi: true },
  { to: "sharing", label: "Sharing" },
];

export default function Workspace() {
  const { ventureId = "" } = useParams();
  const [confirm, setConfirm] = useState(false);
  const remove = useDeleteVenture(ventureId);
  const config = useToolkitConfig();
  const shown = TABS.filter(
    (t) => (!t.feature || config.data?.features[t.feature] !== false) && !(t.needsAi && config.data?.ai_enabled === false),
  );
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
              {shown.map((t) => (
                <NavLink key={t.label} to={t.to} end={t.end} className="app-tablink">
                  {t.label}
                </NavLink>
              ))}
            </div>
          </nav>
          {config.data?.ai_enabled === false ? (
            <Alert tone="info" title="AI writing is off for now">
              Every tool here works without it: your score is worked out from your answers, the business plan lays out each
              section for you to write, and decks, forecasts and prototypes start from templates. Buttons that would ask the
              AI are hidden until it is switched on.
            </Alert>
          ) : null}
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
