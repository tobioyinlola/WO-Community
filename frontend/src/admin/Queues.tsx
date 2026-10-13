import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Badge, Button, Card, Select } from "../components";
import { humanise, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, SkeletonCards, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { ReasonDialog } from "./dialogs";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Win = components["schemas"]["AdminWin"];
type WinStatus = "pending" | "approved" | "rejected";

const TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  published: "success",
  approved: "success",
  pending: "warning",
  rejected: "danger",
  removed: "danger",
  closed: "neutral",
  expired: "neutral",
};

export function WinsReview() {
  useDocumentTitle("Wins to review");
  const [status, setStatus] = useState<WinStatus>("pending");
  const [acting, setActing] = useState<{ win: Win; action: "approve" | "reject" } | null>(null);
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const list = useOffsetList<Win>(["admin", "wins", status], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/win-submissions", { params: { query: { status, limit, offset } } })),
  );
  const run = async (win: Win, action: "approve" | "reject", reason: string) => {
    await guard(async () => {
      const args = { params: { path: { win_id: win.id } }, body: { reason } };
      if (action === "approve") await unwrap(api.POST("/api/v1/admin/win-submissions/{win_id}/approve", args));
      else await unwrap(api.POST("/api/v1/admin/win-submissions/{win_id}/reject", args));
    });
    toast.show(action === "approve" ? "Win published" : "Win declined");
    await client.invalidateQueries({ queryKey: ["admin"] });
  };
  return (
    <>
      <PageHeader eyebrow="Moderation" title="Wins" lead="Milestones members want to celebrate with the community." />
      <div style={{ maxWidth: 240, marginBottom: "var(--space-6)" }}>
        <Select label="Show" options={(["pending", "approved", "rejected"] as WinStatus[]).map((s) => ({ value: s, label: humanise(s) }))} value={status} onChange={(e) => setStatus(e.target.value as WinStatus)} />
      </div>
      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title="Nothing here">No wins with this status.</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((w) => (
              <li key={w.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <div className="app-cluster"><Badge variant={TONE[w.status] ?? "neutral"} dot>{humanise(w.status)}</Badge><Badge variant="neutral">{humanise(w.kind)}</Badge></div>
                    <span className="caption app-muted">{timeAgo(w.created_at)}</span>
                  </div>
                  <h2 className="h4" style={{ margin: "var(--space-3) 0 var(--space-1)" }}>{w.title}</h2>
                  {w.details ? <p className="body" style={{ margin: 0 }}>{w.details}</p> : null}
                  {w.evidence_url ? <p className="body-sm" style={{ margin: "var(--space-2) 0 0" }}>Evidence: <a href={w.evidence_url} rel="noopener noreferrer" target="_blank">{w.evidence_url}</a></p> : null}
                  {w.review_note ? <p className="body-sm app-muted">Note: {w.review_note}</p> : null}
                  {w.status === "pending" ? (
                    <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                      <Button size="sm" onClick={() => setActing({ win: w, action: "approve" })}>Publish</Button>
                      <Button size="sm" variant="secondary" onClick={() => setActing({ win: w, action: "reject" })}>Decline</Button>
                    </div>
                  ) : null}
                </Card>
              </li>
            ))}
          </ul>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
      {acting ? (
        <ReasonDialog
          title={acting.action === "approve" ? "Publish this win?" : "Decline this win?"}
          confirmLabel={acting.action === "approve" ? "Publish" : "Decline"}
          required={acting.action === "reject"}
          intro={acting.action === "approve" ? "It appears in the community news." : "The member is told why."}
          onConfirm={(reason) => run(acting.win, acting.action, reason)}
          onClose={() => setActing(null)}
        />
      ) : null}
    </>
  );
}
