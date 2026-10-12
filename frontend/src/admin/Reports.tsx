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

type Report = components["schemas"]["AdminReport"];
type Filter = "open" | "reviewed" | "actioned";

export default function Reports() {
  useDocumentTitle("Reports");
  const [status, setStatus] = useState<Filter>("open");
  const [acting, setActing] = useState<{ report: Report; action: "hide" | "remove" | "review" } | null>(null);
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const list = useOffsetList<Report>(["admin", "reports", status], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/reports", { params: { query: { status, limit, offset } } })),
  );

  const run = async (report: Report, action: "hide" | "remove" | "review", note: string) => {
    await guard(async () => {
      const path = { params: { path: { report_id: report.id } } };
      if (action === "review") await unwrap(api.POST("/api/v1/admin/reports/{report_id}/review", { ...path, body: { note } }));
      else await unwrap(api.POST("/api/v1/admin/reports/{report_id}/action", { ...path, body: { action, note } }));
    });
    toast.show(action === "review" ? "Marked as reviewed" : action === "hide" ? "Content hidden" : "Content removed");
    await client.invalidateQueries({ queryKey: ["admin"] });
  };

  return (
    <>
      <PageHeader eyebrow="Moderation" title="Reports" lead="Posts and comments members have flagged." />
      <div style={{ maxWidth: 240, marginBottom: "var(--space-6)" }}>
        <Select label="Show" options={[{ value: "open", label: "Open" }, { value: "reviewed", label: "Reviewed" }, { value: "actioned", label: "Acted on" }]} value={status} onChange={(e) => setStatus(e.target.value as Filter)} />
      </div>
      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title={status === "open" ? "Nothing to review" : "Nothing here"}>{status === "open" ? "No open reports. Well done." : "No reports with this status."}</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((r) => (
              <li key={r.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <div className="app-cluster">
                      <Badge variant="warning">{humanise(r.reason)}</Badge>
                      <Badge variant="neutral">{humanise(r.target.type)}</Badge>
                      {r.target.state !== "visible" ? <Badge variant="danger">{humanise(r.target.state)}</Badge> : null}
                      {r.open_reports_on_target > 1 ? <span className="caption app-muted">{r.open_reports_on_target} reports on this</span> : null}
                    </div>
                    <span className="caption app-muted">{timeAgo(r.created_at)}</span>
                  </div>
                  <blockquote style={{ margin: "var(--space-3) 0", paddingLeft: "var(--space-4)", borderLeft: "3px solid var(--border-default)" }}>
                    <p className="body" style={{ margin: 0 }}>{r.target.excerpt || "No text."}</p>
                    {r.target.author ? <footer className="caption app-muted">By {r.target.author.name}</footer> : null}
                  </blockquote>
                  <p className="body-sm app-muted" style={{ margin: 0 }}>
                    Reported by {r.reporter.name}{r.details ? `: “${r.details}”` : "."}
                  </p>
                  {r.note ? <p className="body-sm" style={{ margin: "var(--space-2) 0 0" }}>Note: {r.note}</p> : null}
                  {r.status === "open" ? (
                    <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                      <Button size="sm" variant="secondary" onClick={() => setActing({ report: r, action: "hide" })}>Hide the content</Button>
                      <Button size="sm" variant="secondary" onClick={() => setActing({ report: r, action: "remove" })}>Remove it</Button>
                      <Button size="sm" variant="ghost" onClick={() => setActing({ report: r, action: "review" })}>No action needed</Button>
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
          title={{ hide: "Hide this content?", remove: "Remove this content?", review: "Close this report?" }[acting.action]}
          confirmLabel={{ hide: "Hide", remove: "Remove", review: "Close report" }[acting.action]}
          tone={acting.action === "remove" ? "danger" : "primary"}
          required={acting.action !== "review"}
          intro={{ hide: "It is hidden from members but can be shown again.", remove: "It is taken down for good.", review: "The content stays as it is." }[acting.action]}
          onConfirm={(note) => run(acting.report, acting.action, note)}
          onClose={() => setActing(null)}
        />
      ) : null}
    </>
  );
}
