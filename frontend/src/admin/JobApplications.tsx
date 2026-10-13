import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Badge, Button, Card, Input, Select } from "../components";
import { humanise, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, Skeleton, SkeletonCards, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { ReasonDialog } from "./dialogs";
import { useOffsetList } from "./useOffsetList";

type Application = components["schemas"]["ApplicationRow"];
type Decision = "reviewing" | "shortlisted" | "rejected" | "hired";
type Status = "submitted" | "reviewing" | "shortlisted" | "rejected" | "hired" | "withdrawn";

const STATUSES: Status[] = ["submitted", "reviewing", "shortlisted", "hired", "rejected", "withdrawn"];
const TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "info"> = {
  submitted: "info",
  reviewing: "warning",
  shortlisted: "success",
  hired: "success",
  rejected: "danger",
  withdrawn: "neutral",
};
const DONE: Record<Decision, string> = {
  reviewing: "Marked as being reviewed",
  shortlisted: "Added to the shortlist",
  rejected: "Application declined",
  hired: "Marked as hired",
};

export default function JobApplications() {
  useDocumentTitle("Job applications");
  const client = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [acting, setActing] = useState<{ application: Application; status: Decision } | null>(null);

  const stats = useQuery({ queryKey: ["admin", "applications", "stats"], queryFn: () => unwrap(api.GET("/api/v1/admin/job-applications/stats")) });
  const list = useOffsetList<Application>(["admin", "applications", status, term], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/job-applications", { params: { query: { limit, offset, ...(status ? { status: status as Status } : {}), ...(term ? { q: term } : {}) } } })),
  );
  const decide = async (application: Application, next: Decision, note: string) => {
    await unwrap(api.POST("/api/v1/job-applications/{application_id}/decide", { params: { path: { application_id: application.id } }, body: { status: next, note } }));
    toast.show(DONE[next]);
    await client.invalidateQueries({ queryKey: ["admin", "applications"] });
  };

  return (
    <>
      <PageHeader eyebrow="Jobs" title="Applications" lead="Everyone who has applied to a role through the community, and where each application stands." />
      <dl className="adm-statstrip" aria-label="Applications by status">
        {STATUSES.map((s) => (
          <div key={s} className="adm-statstrip__cell">
            <dt>{humanise(s)}</dt>
            <dd>{stats.data ? stats.data[s].toLocaleString("en-NG") : <Skeleton width={30} height={22} />}</dd>
          </div>
        ))}
      </dl>
      <form className="app-formgrid" style={{ margin: "var(--space-6) 0", alignItems: "end" }} role="search" onSubmit={(e) => { e.preventDefault(); setTerm(q.trim()); }}>
        <Input label="Search by job, company or applicant" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select label="Status" options={[{ value: "", label: "All" }, ...STATUSES.map((s) => ({ value: s, label: humanise(s) }))]} value={status} onChange={(e) => setStatus(e.target.value)} />
        <div><Button type="submit" variant="secondary">Search</Button></div>
      </form>

      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title="No applications">{term || status ? "Nothing matches this search." : "When members apply to a role, it shows up here."}</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((a) => (
              <li key={a.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <Badge variant={TONE[a.status] ?? "neutral"} dot>{humanise(a.status)}</Badge>
                    <span className="caption app-muted">Applied {timeAgo(a.created_at)}</span>
                  </div>
                  <h2 className="h4" style={{ margin: "var(--space-3) 0 var(--space-1)" }}>{a.applicant.name}</h2>
                  <p className="body-sm app-muted adm-wrap" style={{ margin: 0 }}>{a.applicant.email}</p>
                  <p className="body-sm" style={{ margin: "var(--space-2) 0 0" }}>
                    For <strong>{a.job_title}</strong>{a.job_organisation ? ` at ${a.job_organisation}` : ""}
                    {a.job_status !== "published" ? <> · <span className="app-muted">job is {a.job_status}</span></> : null}
                  </p>
                  <details style={{ marginTop: "var(--space-3)" }}>
                    <summary>Read the application</summary>
                    <p className="body" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{a.note}</p>
                    {a.link ? <p className="body-sm">CV or portfolio: <a href={a.link} target="_blank" rel="noopener noreferrer nofollow" className="adm-wrap">{a.link}</a></p> : null}
                    {a.decision_note ? <p className="body-sm app-muted">Note: {a.decision_note}</p> : null}
                  </details>
                  {a.status !== "withdrawn" ? (
                    <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                      {a.status !== "reviewing" && a.status !== "hired" ? <Button size="sm" variant="secondary" onClick={() => setActing({ application: a, status: "reviewing" })}>Start review</Button> : null}
                      {a.status !== "shortlisted" && a.status !== "hired" ? <Button size="sm" variant="secondary" onClick={() => setActing({ application: a, status: "shortlisted" })}>Shortlist</Button> : null}
                      {a.status !== "hired" ? <Button size="sm" onClick={() => setActing({ application: a, status: "hired" })}>Mark hired</Button> : null}
                      {a.status !== "rejected" ? <Button size="sm" variant="ghost" onClick={() => setActing({ application: a, status: "rejected" })}>Decline</Button> : null}
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
          title={{ reviewing: "Start reviewing this application?", shortlisted: "Shortlist this applicant?", hired: "Mark this applicant as hired?", rejected: "Decline this application?" }[acting.status]}
          confirmLabel={{ reviewing: "Start review", shortlisted: "Shortlist", hired: "Mark hired", rejected: "Decline" }[acting.status]}
          tone={acting.status === "rejected" ? "danger" : "primary"}
          required={false}
          intro={`${acting.application.applicant.name} applied for ${acting.application.job_title}.`}
          onConfirm={(note) => decide(acting.application, acting.status, note)}
          onClose={() => setActing(null)}
        />
      ) : null}
    </>
  );
}
