import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Badge, Button, Card, Input, Select } from "../components";
import { formatDateTime, humanise, plural, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, SkeletonCards, TableScroll, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { ReasonDialog } from "./dialogs";
import { useOffsetList } from "./useOffsetList";

type Session = components["schemas"]["AdminMentoringSession"];
type Match = components["schemas"]["AdminMatch"];
type SessionStatus = components["schemas"]["MentoringSessionStatusEnum"];

const STATUSES: SessionStatus[] = ["requested", "confirmed", "completed", "declined", "cancelled", "expired", "no_show"];
const TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "info"> = {
  requested: "warning",
  confirmed: "info",
  completed: "success",
  declined: "neutral",
  cancelled: "danger",
  expired: "neutral",
  no_show: "danger",
  active: "info",
  idle: "neutral",
};

export function MentoringSessions() {
  useDocumentTitle("Mentoring sessions");
  const client = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [cancelling, setCancelling] = useState<Session | null>(null);
  const list = useOffsetList<Session>(["admin", "sessions", status], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/sessions", { params: { query: { limit, offset, ...(status ? { status: status as SessionStatus } : {}) } } })),
  );
  const cancel = async (session: Session, reason: string) => {
    await unwrap(api.POST("/api/v1/admin/sessions/{session_id}/cancel", { params: { path: { session_id: session.id } }, body: { reason } }));
    toast.show("Session cancelled. Both people have been told.");
    await client.invalidateQueries({ queryKey: ["admin", "sessions"] });
    await client.invalidateQueries({ queryKey: ["admin", "matches"] });
  };
  return (
    <>
      <PageHeader eyebrow="Mentorship" title="Sessions" lead="Every mentoring session, from the first request to the feedback afterwards. Step in when something goes wrong." />
      <div style={{ maxWidth: 260, marginBottom: "var(--space-6)" }}>
        <Select label="Show" options={[{ value: "", label: "All sessions" }, ...STATUSES.map((s) => ({ value: s, label: humanise(s) }))]} value={status} onChange={(e) => setStatus(e.target.value)} />
      </div>
      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title="No sessions">{status ? "No sessions with this status." : "Nobody has asked a mentor for a session yet."}</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((s) => (
              <li key={s.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <div className="app-cluster">
                      <Badge variant={TONE[s.status] ?? "neutral"} dot>{humanise(s.status)}</Badge>
                      {s.late_cancel ? <Badge variant="warning">Late cancellation</Badge> : null}
                    </div>
                    <span className="caption app-muted">Asked {timeAgo(s.created_at)}</span>
                  </div>
                  <h2 className="h4" style={{ margin: "var(--space-3) 0 var(--space-1)" }}>{s.topic}</h2>
                  <p className="body-sm" style={{ margin: 0 }}>
                    <strong>{s.mentor.name}</strong> <span className="app-muted">(mentor)</span> with <strong>{s.mentee.name}</strong>
                  </p>
                  <p className="body-sm app-muted adm-wrap" style={{ margin: "2px 0 0" }}>{s.mentor_email} · {s.mentee_email}</p>
                  <p className="body-sm" style={{ margin: "var(--space-2) 0 0" }}>
                    {formatDateTime(s.starts_at)} · {s.length_minutes} minutes
                    {s.meeting.url ? <> · <a href={s.meeting.url} target="_blank" rel="noopener noreferrer nofollow">Meeting link</a></> : null}
                  </p>
                  {s.reason ? <p className="body-sm app-muted" style={{ margin: "var(--space-2) 0 0" }}>Reason: {s.reason}</p> : null}
                  {s.feedback.from_mentee || s.feedback.from_mentor ? (
                    <details style={{ marginTop: "var(--space-3)" }}>
                      <summary>Feedback</summary>
                      {s.feedback.from_mentee ? <p className="body-sm">Mentee: {s.feedback.from_mentee.stars ? `${s.feedback.from_mentee.stars} of 5. ` : ""}{s.feedback.from_mentee.comment || "No comment."}</p> : null}
                      {s.feedback.from_mentor ? <p className="body-sm">Mentor: {s.feedback.from_mentor.outcome ? `${humanise(s.feedback.from_mentor.outcome)}. ` : ""}{s.feedback.from_mentor.comment || "No comment."}</p> : null}
                    </details>
                  ) : null}
                  {s.status === "requested" || s.status === "confirmed" ? (
                    <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                      <Button size="sm" variant="secondary" onClick={() => setCancelling(s)}>Cancel this session</Button>
                    </div>
                  ) : null}
                </Card>
              </li>
            ))}
          </ul>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
      {cancelling ? (
        <ReasonDialog
          title="Cancel this session?"
          confirmLabel="Cancel session"
          tone="danger"
          intro={`${cancelling.mentor.name} and ${cancelling.mentee.name} are both told, with your reason.`}
          onConfirm={(reason) => cancel(cancelling, reason)}
          onClose={() => setCancelling(null)}
        />
      ) : null}
    </>
  );
}

export function MentoringMatches() {
  useDocumentTitle("Mentoring matches");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [state, setState] = useState("");
  const list = useOffsetList<Match>(["admin", "matches", term, state], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/matches", { params: { query: { limit, offset, ...(term ? { q: term } : {}), ...(state ? { state: state as "active" | "completed" | "idle" } : {}) } } })),
  );
  return (
    <>
      <PageHeader eyebrow="Mentorship" title="Matches" lead="Which mentors are working with which founders, and which pairs have gone quiet." />
      <form className="app-formgrid" style={{ marginBottom: "var(--space-6)", alignItems: "end" }} role="search" onSubmit={(e) => { e.preventDefault(); setTerm(q.trim()); }}>
        <Input label="Search by name or email" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select label="State" options={[{ value: "", label: "All pairs" }, { value: "active", label: "Working together now" }, { value: "completed", label: "Finished" }, { value: "idle", label: "No session held" }]} value={state} onChange={(e) => setState(e.target.value)} />
        <div><Button type="submit" variant="secondary">Search</Button></div>
      </form>
      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title="No matches yet">{term || state ? "Nothing matches this search." : "A match appears once a founder asks a mentor for a session."}</EmptyState>
      ) : (
        <>
          <TableScroll label="Mentor and founder pairs">
            <table className="app-table">
              <caption className="wo-visually-hidden">Mentor and founder pairs</caption>
              <thead>
                <tr><th scope="col">Mentor</th><th scope="col">Founder</th><th scope="col">Sessions</th><th scope="col">State</th><th scope="col">Next session</th><th scope="col">Last activity</th></tr>
              </thead>
              <tbody>
                {list.items.map((m) => (
                  <tr key={`${m.mentor.id}-${m.mentee.id}`}>
                    <th scope="row"><span className="adm-who__name">{m.mentor.name}</span><br /><span className="caption app-muted adm-wrap">{m.mentor.email}</span></th>
                    <td><span className="adm-who__name">{m.mentee.name}</span><br /><span className="caption app-muted adm-wrap">{m.mentee.email}</span></td>
                    <td>{plural(m.sessions, "session")}, {m.completed} held{m.waiting ? `, ${m.waiting} waiting` : ""}</td>
                    <td><Badge variant={TONE[m.state] ?? "neutral"} dot>{m.state === "active" ? "Active" : m.state === "completed" ? "Finished" : "Quiet"}</Badge></td>
                    <td>{m.next_at ? formatDateTime(m.next_at) : "None booked"}</td>
                    <td>{timeAgo(m.last_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
    </>
  );
}
