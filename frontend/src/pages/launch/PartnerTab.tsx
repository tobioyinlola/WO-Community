import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Alert, Badge, Button, Card, Input, Textarea } from "../../components";
import { formatDate, humanise, timeAgo } from "../../lib/format";
import { EmptyState, Loaded, SkeletonRows } from "../../ui/blocks";
import { FormError, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";
import { JobStatus, useJob } from "./jobs";
import { useWorkspace } from "./Workspace";

type ChangeSet = components["schemas"]["TkChangeSet"];

const show = (v: unknown) => (v === null || v === undefined || v === "" ? "empty" : typeof v === "string" ? v : JSON.stringify(v));

function Changes({ set, onDone }: { set: ChangeSet; onDone: () => void }) {
  const { ventureId } = useWorkspace();
  const toast = useToast();
  const [chosen, setChosen] = useState<string[]>(set.changes.map((c) => c.field));
  const path = { venture_id: ventureId, change_set_id: set.id };
  const apply = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/partner/change-sets/{change_set_id}/apply", { params: { path }, body: { accept: chosen } }));
    toast.show("Changes added to your profile");
    onDone();
  });
  const dismiss = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/partner/change-sets/{change_set_id}/dismiss", { params: { path } }));
    onDone();
  });
  const undo = useSubmit(async () => {
    const result = await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/partner/change-sets/{change_set_id}/undo", { params: { path } }));
    toast.show(result.skipped.length ? `Undone, except ${result.skipped.map((s) => humanise(s).toLowerCase()).join(", ")} which you changed since` : "Changes undone");
    onDone();
  });
  return (
    <Card variant="white">
      <p className="eyebrow" style={{ margin: "0 0 var(--space-2)" }}>
        {set.status === "proposed" ? "Suggested changes to your profile" : set.status === "applied" ? "Added to your profile" : set.status === "undone" ? "Undone" : "Dismissed"}
      </p>
      <FormError error={apply.error ?? dismiss.error ?? undo.error} />
      <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {set.changes.map((c) => (
          <li key={c.field}>
            {set.status === "proposed" ? (
              <label className="wo-check" style={{ alignItems: "flex-start" }}>
                <input type="checkbox" checked={chosen.includes(c.field)} onChange={() => setChosen(chosen.includes(c.field) ? chosen.filter((f) => f !== c.field) : [...chosen, c.field])} />
                <span><strong>{c.label}</strong><br /><span className="body-sm app-muted">Now: {show(c.from_value)}</span><br /><span className="body-sm">New: {show(c.to_value)}</span>{c.reason ? <><br /><span className="caption app-muted">{c.reason}</span></> : null}</span>
              </label>
            ) : (
              <p className="body-sm" style={{ margin: 0 }}><strong>{c.label}:</strong> {show(c.to_value)}</p>
            )}
          </li>
        ))}
      </ul>
      <div className="app-cluster" style={{ marginTop: "var(--space-3)" }}>
        {set.status === "proposed" ? (
          <>
            <Button size="sm" loading={apply.busy} disabled={chosen.length === 0} onClick={() => void apply.run()}>Add selected</Button>
            <Button size="sm" variant="ghost" loading={dismiss.busy} onClick={() => void dismiss.run()}>Not now</Button>
          </>
        ) : set.status === "applied" ? (
          <Button size="sm" variant="secondary" loading={undo.busy} onClick={() => void undo.run()}>Undo</Button>
        ) : null}
      </div>
    </Card>
  );
}

function Thread({ conversationId }: { conversationId: string }) {
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const [text, setText] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const key = ["toolkit", ventureId, "partner", "conversation", conversationId];
  const query = useQuery({ queryKey: key, queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/partner/conversations/{conversation_id}", { params: { path: { venture_id: ventureId, conversation_id: conversationId } } })) });
  const running = useJob(jobId, () => { setJobId(null); void client.invalidateQueries({ queryKey: key }); });
  const send = useSubmit(async () => {
    const body = text.trim();
    const data = await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/partner/conversations/{conversation_id}/messages", { params: { path: { venture_id: ventureId, conversation_id: conversationId } }, body: { text: body } }));
    setText("");
    if (data.job) setJobId(data.job.id);
    await client.invalidateQueries({ queryKey: key });
  });
  const waiting = send.busy || Boolean(jobId && running.running);
  return (
    <Loaded query={query} skeleton={<SkeletonRows />}>
      {(c) => (
        <div className="app-stack">
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }} aria-live="polite" aria-label="Conversation">
            {c.messages.map((m) => (
              <li key={m.id} className="app-stack" style={{ alignItems: m.author === "user" ? "flex-end" : "flex-start", gap: "var(--space-2)" }}>
                <div className="app-proto-card" style={{ maxWidth: "min(100%, 60ch)", background: m.author === "user" ? "var(--bg-sunken)" : "var(--bg-surface)" }}>
                  <p className="caption app-muted" style={{ margin: "0 0 var(--space-1)" }}>{m.author === "user" ? "You" : "Venture partner"} &middot; {timeAgo(m.created_at)}</p>
                  <p className="body" style={{ margin: 0, whiteSpace: "pre-wrap" }}>{m.text}</p>
                  {m.declined ? <p className="caption app-muted" style={{ margin: "var(--space-2) 0 0" }}>{m.declined}</p> : null}
                  {m.next_steps.length > 0 ? <ul style={{ margin: "var(--space-2) 0 0" }}>{m.next_steps.map((s) => <li key={s} className="body-sm">{s}</li>)}</ul> : null}
                </div>
                {m.change_set ? <Changes set={m.change_set} onDone={() => void client.invalidateQueries({ queryKey: ["toolkit", ventureId] })} /> : null}
              </li>
            ))}
          </ul>
          {jobId ? <JobStatus job={running.job} error={running.error} /> : null}
          <FormError error={send.error} />
          <form className="app-stack" onSubmit={(e) => { e.preventDefault(); if (text.trim()) void send.run(); }}>
            <Textarea label="Ask the venture partner" rows={3} value={text} onChange={(e) => setText(e.target.value)} hint="It can help with your plan, pricing, who to talk to and what to do next. It does not give legal, tax or investment advice." />
            <div><Button type="submit" loading={waiting} disabled={!text.trim()}>Send</Button></div>
          </form>
        </div>
      )}
    </Loaded>
  );
}

export default function PartnerTab() {
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const toast = useToast();
  const [current, setCurrent] = useState<string | null>(null);
  const [decision, setDecision] = useState({ text: "", rationale: "" });
  const conversations = useQuery({ queryKey: ["toolkit", ventureId, "partner", "conversations"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/partner/conversations", { params: { path: { venture_id: ventureId } } })) });
  const decisions = useQuery({ queryKey: ["toolkit", ventureId, "partner", "decisions"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/partner/decisions", { params: { path: { venture_id: ventureId } } })) });
  const nudges = useQuery({ queryKey: ["toolkit", ventureId, "partner", "nudges"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/partner/nudges", { params: { path: { venture_id: ventureId } } })) });
  const mentors = useQuery({ queryKey: ["toolkit", ventureId, "partner", "mentors"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/partner/mentors", { params: { path: { venture_id: ventureId } } })) });
  const start = useSubmit(async () => {
    const made = await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/partner/conversations", { params: { path: { venture_id: ventureId } }, body: {} }));
    await client.invalidateQueries({ queryKey: ["toolkit", ventureId, "partner", "conversations"] });
    setCurrent(made.id);
  });
  const log = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/partner/decisions", { params: { path: { venture_id: ventureId } }, body: { text: decision.text.trim(), ...(decision.rationale.trim() ? { rationale: decision.rationale.trim() } : {}) } }));
    setDecision({ text: "", rationale: "" });
    toast.show("Decision noted");
    await client.invalidateQueries({ queryKey: ["toolkit", ventureId, "partner", "decisions"] });
  });
  const dropDecision = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/toolkit/ventures/{venture_id}/partner/decisions/{decision_id}", { params: { path: { venture_id: ventureId, decision_id: id } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["toolkit", ventureId, "partner", "decisions"] }),
  });
  const seen = useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/partner/nudges/{nudge_id}/read", { params: { path: { venture_id: ventureId, nudge_id: id } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["toolkit", ventureId, "partner", "nudges"] }),
  });
  const active = current ?? conversations.data?.[0]?.id ?? null;
  const unread = (nudges.data ?? []).filter((n) => !n.read_at);

  return (
    <div className="app-split">
      <div className="app-stack app-stack--lg">
        <Alert tone="info" title="Your venture partner">It reads your profile, score and forecast, so you do not have to explain everything again. Anything it suggests changing is shown to you first.</Alert>
        <div className="app-cluster">
          {(conversations.data ?? []).slice(0, 5).map((c) => (
            <button key={c.id} type="button" className="app-react" aria-pressed={c.id === active} onClick={() => setCurrent(c.id)}>{c.title || `Chat from ${formatDate(c.updated_at)}`}</button>
          ))}
          <Button size="sm" variant="secondary" loading={start.busy} onClick={() => void start.run()}>New conversation</Button>
        </div>
        <FormError error={start.error} />
        {active ? <Thread key={active} conversationId={active} /> : (
          <EmptyState title="Start a conversation" icon={<MessageSquare size={22} strokeWidth={1.5} />}>Ask what to do next, how to price, or how to test the idea.</EmptyState>
        )}
      </div>
      <aside className="app-stack">
        {unread.length > 0 ? (
          <Card>
            <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>This week</h2>
            <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {unread.map((n) => (
                <li key={n.id}><p className="body-sm" style={{ margin: 0 }}>{n.text}</p><button type="button" className="app-linklike" onClick={() => seen.mutate(n.id)}>Got it</button></li>
              ))}
            </ul>
          </Card>
        ) : null}
        {mentors.data && mentors.data.mentors.length > 0 ? (
          <Card>
            <h2 className="h4" style={{ margin: "0 0 var(--space-2)" }}>Mentors who could help</h2>
            {mentors.data.topics.length > 0 ? <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-3)" }}>For: {mentors.data.topics.join(", ")}</p> : null}
            <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {mentors.data.mentors.slice(0, 4).map((m, i) => (
                <li key={i}>{typeof m.id === "string" ? <Link to={`/app/mentors/${m.id}`}>{String(m.name ?? "Mentor")}</Link> : String(m.name ?? "Mentor")}{typeof m.headline === "string" ? <span className="body-sm app-muted"> &mdash; {m.headline}</span> : null}</li>
              ))}
            </ul>
          </Card>
        ) : null}
        <Card>
          <h2 className="h4" style={{ margin: "0 0 var(--space-2)" }}>Decisions you have made</h2>
          <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-3)" }}>The partner reads these, so it stops suggesting what you already ruled out.</p>
          <FormError error={log.error} />
          <div className="app-stack">
            <Input label="A decision" value={decision.text} onChange={(e) => setDecision({ ...decision, text: e.target.value })} />
            <Input label="Why (optional)" value={decision.rationale} onChange={(e) => setDecision({ ...decision, rationale: e.target.value })} />
            <div><Button size="sm" variant="secondary" loading={log.busy} disabled={!decision.text.trim()} onClick={() => void log.run()}>Note it</Button></div>
            {(decisions.data ?? []).map((d) => (
              <div key={d.id} className="app-cluster" style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
                <span className="body-sm">{d.text}{d.rationale ? <span className="app-muted"> &mdash; {d.rationale}</span> : null} <Badge variant="neutral">{formatDate(d.decided_on)}</Badge></span>
                <Button size="sm" variant="ghost" onClick={() => dropDecision.mutate(d.id)} aria-label={`Remove decision ${d.text}`}>Remove</Button>
              </div>
            ))}
          </div>
        </Card>
      </aside>
    </div>
  );
}
