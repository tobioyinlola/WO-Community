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

type Application = components["schemas"]["AdminMentorApplication"];
type Decision = "approve" | "decline" | "request_info";

const TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "info"> = {
  pending: "warning",
  info_requested: "info",
  approved: "success",
  declined: "danger",
  withdrawn: "neutral",
};

export default function MentorApplications() {
  useDocumentTitle("Mentor applications");
  const [status, setStatus] = useState("pending");
  const [acting, setActing] = useState<{ app: Application; decision: Decision } | null>(null);
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const list = useOffsetList<Application>(["admin", "mentor-applications", status], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/mentor-applications", { params: { query: { status, limit, offset } } })),
  );
  const run = async (app: Application, decision: Decision, reason: string) => {
    await guard(() =>
      unwrap(api.POST("/api/v1/admin/mentor-applications/{application_id}/decision", { params: { path: { application_id: app.id } }, body: { decision, ...(reason ? { reason } : {}) } })),
    );
    toast.show({ approve: "Mentor approved", decline: "Application declined", request_info: "More information requested" }[decision]);
    await client.invalidateQueries({ queryKey: ["admin"] });
  };
  return (
    <>
      <PageHeader eyebrow="People" title="Mentor applications" lead="Members who offered to mentor others." />
      <div style={{ maxWidth: 260, marginBottom: "var(--space-6)" }}>
        <Select label="Show" options={["pending", "info_requested", "approved", "declined", "withdrawn"].map((s) => ({ value: s, label: humanise(s) }))} value={status} onChange={(e) => setStatus(e.target.value)} />
      </div>
      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title="Nothing here">No applications with this status.</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((a) => (
              <li key={a.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <Badge variant={TONE[a.status] ?? "neutral"} dot>{humanise(a.status)}</Badge>
                    <span className="caption app-muted">{timeAgo(a.created_at)}</span>
                  </div>
                  <h2 className="h4" style={{ margin: "var(--space-3) 0 var(--space-1)" }}>{a.applicant.name}</h2>
                  <p className="body-sm app-muted" style={{ margin: 0 }}>
                    {[a.current_role, a.company].filter(Boolean).join(" at ")} · {a.years_experience} years · {a.applicant.email}
                  </p>
                  <p className="body" style={{ margin: "var(--space-3) 0 0" }}>{a.motivation}</p>
                  <dl className="app-stack" style={{ margin: "var(--space-3) 0 0", gap: "var(--space-1)" }}>
                    <div><dt className="caption app-muted">Expertise</dt><dd style={{ margin: 0 }}>{a.expertise.join(", ") || "None given"}</dd></div>
                    <div><dt className="caption app-muted">Time</dt><dd style={{ margin: 0 }}>{a.weekly_hours} hours a week · {a.timezone}</dd></div>
                    {a.linkedin_url ? <div><dt className="caption app-muted">LinkedIn</dt><dd style={{ margin: 0 }}><a href={a.linkedin_url} rel="noopener noreferrer" target="_blank">{a.linkedin_url}</a></dd></div> : null}
                    {a.decision_reason ? <div><dt className="caption app-muted">Decision note</dt><dd style={{ margin: 0 }}>{a.decision_reason}</dd></div> : null}
                  </dl>
                  {a.status === "pending" || a.status === "info_requested" ? (
                    <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                      <Button size="sm" onClick={() => setActing({ app: a, decision: "approve" })}>Approve</Button>
                      <Button size="sm" variant="secondary" onClick={() => setActing({ app: a, decision: "request_info" })}>Ask for more</Button>
                      <Button size="sm" variant="ghost" onClick={() => setActing({ app: a, decision: "decline" })}>Decline</Button>
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
          title={{ approve: `Approve ${acting.app.applicant.name}?`, decline: "Decline this application?", request_info: "Ask for more information?" }[acting.decision]}
          confirmLabel={{ approve: "Approve", decline: "Decline", request_info: "Send request" }[acting.decision]}
          required={acting.decision !== "approve"}
          intro={{ approve: "They become a mentor and can set the times they are free.", decline: "They are told why.", request_info: "Say what you need. They can update and resubmit." }[acting.decision]}
          onConfirm={(reason) => run(acting.app, acting.decision, reason)}
          onClose={() => setActing(null)}
        />
      ) : null}
    </>
  );
}
