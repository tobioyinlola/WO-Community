import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Badge, Button, Card, Input, Select } from "../components";
import { formatDate, humanise, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, RichText, SkeletonCards, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { textToHtml } from "../lib/html";
import { ReasonDialog } from "./dialogs";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Job = components["schemas"]["AdminJob"];
type Win = components["schemas"]["AdminWin"];
type JobStatus = "pending" | "published" | "closed" | "expired" | "rejected" | "removed";
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

export function JobsReview() {
  useDocumentTitle("Jobs to review");
  const [status, setStatus] = useState<JobStatus>("pending");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [acting, setActing] = useState<{ job: Job; action: "approve" | "reject" | "remove" } | null>(null);
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const list = useOffsetList<Job>(["admin", "jobs", status, term], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/jobs", { params: { query: { status, limit, offset, ...(term ? { q: term } : {}) } } })),
  );
  const run = async (job: Job, action: "approve" | "reject" | "remove", reason: string) => {
    await guard(async () => {
      const args = { params: { path: { job_id: job.id } }, body: { reason } };
      if (action === "approve") await unwrap(api.POST("/api/v1/admin/jobs/{job_id}/approve", args));
      else if (action === "reject") await unwrap(api.POST("/api/v1/admin/jobs/{job_id}/reject", args));
      else await unwrap(api.POST("/api/v1/admin/jobs/{job_id}/remove", args));
    });
    toast.show({ approve: "Job published", reject: "Job rejected", remove: "Job removed" }[action]);
    await client.invalidateQueries({ queryKey: ["admin"] });
  };
  return (
    <>
      <PageHeader eyebrow="Moderation" title="Jobs" lead="Check roles before they go live to the community." />
      <form className="app-formgrid" style={{ marginBottom: "var(--space-6)", alignItems: "end" }} role="search" onSubmit={(e) => { e.preventDefault(); setTerm(q.trim()); }}>
        <Select label="Show" options={(["pending", "published", "rejected", "closed", "expired", "removed"] as JobStatus[]).map((s) => ({ value: s, label: humanise(s) }))} value={status} onChange={(e) => setStatus(e.target.value as JobStatus)} />
        <Input label="Search" value={q} onChange={(e) => setQ(e.target.value)} />
        <div><Button type="submit" variant="secondary">Search</Button></div>
      </form>
      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title={status === "pending" ? "Nothing waiting" : "No jobs here"}>{status === "pending" ? "Every submitted job has been reviewed." : "No jobs with this status."}</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((j) => (
              <li key={j.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <div className="app-cluster"><Badge variant={TONE[j.status] ?? "neutral"} dot>{humanise(j.status)}</Badge><Badge variant="neutral">{humanise(j.type)}</Badge></div>
                    <span className="caption app-muted">Posted {timeAgo(j.created_at)}</span>
                  </div>
                  <h2 className="h4" style={{ margin: "var(--space-3) 0 var(--space-1)" }}>{j.title}</h2>
                  <p className="body-sm app-muted" style={{ margin: 0 }}>
                    {j.organisation}{j.location ? ` · ${j.location}` : ""}{j.remote ? " · Remote" : ""}{j.poster ? ` · by ${j.poster.name}` : ""}
                  </p>
                  <details style={{ marginTop: "var(--space-3)" }}>
                    <summary>Read the whole listing</summary>
                    <RichText html={textToHtml(j.description)} />
                    {j.requirements ? <><p className="body-strong">Requirements</p><RichText html={textToHtml(j.requirements)} /></> : null}
                    {j.compensation ? <p className="body-sm">Pay: {j.compensation}</p> : null}
                    {j.deadline ? <p className="body-sm">Apply by {formatDate(j.deadline)}</p> : null}
                  </details>
                  {j.review_note ? <p className="body-sm" style={{ margin: "var(--space-2) 0 0" }}>Review note: {j.review_note}</p> : null}
                  <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                    {j.status === "pending" ? (
                      <>
                        <Button size="sm" onClick={() => setActing({ job: j, action: "approve" })}>Publish</Button>
                        <Button size="sm" variant="secondary" onClick={() => setActing({ job: j, action: "reject" })}>Reject</Button>
                      </>
                    ) : null}
                    {j.status === "published" ? <Button size="sm" variant="ghost" onClick={() => setActing({ job: j, action: "remove" })}>Take down</Button> : null}
                  </div>
                </Card>
              </li>
            ))}
          </ul>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
      {acting ? (
        <ReasonDialog
          title={{ approve: "Publish this job?", reject: "Reject this job?", remove: "Take this job down?" }[acting.action]}
          confirmLabel={{ approve: "Publish", reject: "Reject", remove: "Take down" }[acting.action]}
          tone={acting.action === "approve" ? "primary" : "danger"}
          required={acting.action !== "approve"}
          intro={acting.action === "approve" ? "It goes live to members at once." : "The person who posted it is told why."}
          onConfirm={(reason) => run(acting.job, acting.action, reason)}
          onClose={() => setActing(null)}
        />
      ) : null}
    </>
  );
}

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
