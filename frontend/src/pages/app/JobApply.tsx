import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Badge, Button, Card, Input, Modal, Textarea } from "../../components";
import { humanise, timeAgo } from "../../lib/format";
import { ErrorState, Skeleton } from "../../ui/blocks";
import { FormError, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";

type Mine = components["schemas"]["MyApplication"];
type Applicant = components["schemas"]["ApplicationRow"];

const TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "info"> = {
  submitted: "info",
  reviewing: "warning",
  shortlisted: "success",
  hired: "success",
  rejected: "neutral",
  withdrawn: "neutral",
};

const STATUS_COPY: Record<string, string> = {
  submitted: "Sent. The person hiring has not looked yet.",
  reviewing: "They are reading your application.",
  shortlisted: "You are on the shortlist.",
  hired: "You got the role. Congratulations.",
  rejected: "They decided not to go ahead this time.",
  withdrawn: "You withdrew this application.",
};

function ApplyDialog({ jobId, title, onClose }: { jobId: string; title: string; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const [note, setNote] = useState("");
  const [link, setLink] = useState("");
  const submit = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/jobs/{job_id}/apply", { params: { path: { job_id: jobId } }, body: { note: note.trim(), link: link.trim() } }));
    toast.show("Application sent");
    await client.invalidateQueries({ queryKey: ["jobs", "application", jobId] });
    onClose();
  });
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Apply"
      title={title}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button loading={submit.busy} disabled={!note.trim()} onClick={() => void submit.run()}>Send application</Button>
        </>
      }
    >
      <form className="app-stack" noValidate onSubmit={(e) => { e.preventDefault(); void submit.run(); }}>
        <FormError error={submit.error} listFields />
        <Textarea label="Why you, and why this role" rows={6} hint="A few lines is enough. Say what you have done that fits." value={note} onChange={(e) => setNote(e.target.value)} />
        <Input label="Link to your CV or portfolio (optional)" type="url" placeholder="https://" value={link} onChange={(e) => setLink(e.target.value)} />
      </form>
    </Modal>
  );
}

/** Apply to a job through the community, and follow what happens to the application. */
export function ApplyPanel({ jobId, title }: { jobId: string; title: string }) {
  const client = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const mine = useQuery({
    queryKey: ["jobs", "application", jobId],
    retry: false,
    queryFn: async (): Promise<Mine | null> => {
      const { data, response } = await api.GET("/api/v1/jobs/{job_id}/apply", { params: { path: { job_id: jobId } } });
      if (response.status === 404) return null;
      if (!data) throw new Error("Could not load your application");
      return data;
    },
  });
  const withdraw = useSubmit(async () => {
    if (!mine.data) return;
    await unwrap(api.POST("/api/v1/job-applications/{application_id}/withdraw", { params: { path: { application_id: mine.data.id } } }));
    toast.show("Application withdrawn");
    await client.invalidateQueries({ queryKey: ["jobs", "application", jobId] });
  });
  if (mine.isPending) return <Skeleton height={44} />;
  if (mine.isError) return null;
  const application = mine.data;
  return (
    <>
      {application ? (
        <div className="app-stack" style={{ marginTop: "var(--space-4)" }}>
          <p className="body-sm" style={{ margin: 0 }}>
            <Badge variant={TONE[application.status] ?? "neutral"} dot>{humanise(application.status)}</Badge>{" "}
            <span className="app-muted">applied {timeAgo(application.created_at)}</span>
          </p>
          <p className="body-sm" style={{ margin: 0 }}>{STATUS_COPY[application.status]}</p>
          {application.decision_note ? <p className="body-sm app-muted" style={{ margin: 0 }}>Their note: {application.decision_note}</p> : null}
          <FormError error={withdraw.error} />
          {application.status === "submitted" || application.status === "reviewing" || application.status === "shortlisted" ? (
            <div><Button size="sm" variant="ghost" loading={withdraw.busy} onClick={() => void withdraw.run()}>Withdraw application</Button></div>
          ) : null}
        </div>
      ) : (
        <Button style={{ marginTop: "var(--space-4)", width: "100%" }} size="lg" onClick={() => setOpen(true)}>Apply through WO Community</Button>
      )}
      {open ? <ApplyDialog jobId={jobId} title={title} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

/** The applications to a job, for the member who posted it. */
export function Applicants({ jobId }: { jobId: string }) {
  const client = useQueryClient();
  const toast = useToast();
  const list = useQuery({ queryKey: ["jobs", "applicants", jobId], queryFn: () => unwrap(api.GET("/api/v1/jobs/{job_id}/applications", { params: { path: { job_id: jobId } } })) });
  const [error, setError] = useState<unknown>(null);
  const decide = async (a: Applicant, status: "reviewing" | "shortlisted" | "rejected" | "hired") => {
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/job-applications/{application_id}/decide", { params: { path: { application_id: a.id } }, body: { status, note: "" } }));
      toast.show("Updated. The applicant will see the new status.");
      await client.invalidateQueries({ queryKey: ["jobs", "applicants", jobId] });
    } catch (caught) {
      setError(caught);
    }
  };
  return (
    <Card>
      <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Applications{list.data ? ` (${list.data.length})` : ""}</h2>
      <FormError error={error} />
      {list.isPending ? <Skeleton height={60} /> : list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : list.data.length === 0 ? (
        <p className="body-sm app-muted" style={{ margin: 0 }}>No one has applied through the community yet.</p>
      ) : (
        <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {list.data.map((a) => (
            <li key={a.id}>
              <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                <strong>{a.applicant.name}</strong>
                <Badge variant={TONE[a.status] ?? "neutral"} dot>{humanise(a.status)}</Badge>
              </div>
              <p className="caption app-muted" style={{ margin: "2px 0 var(--space-2)", overflowWrap: "anywhere" }}>{a.applicant.email} · {timeAgo(a.created_at)}</p>
              <p className="body-sm" style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{a.note}</p>
              {a.link ? <p className="body-sm" style={{ margin: "var(--space-2) 0 0", overflowWrap: "anywhere" }}><a href={a.link} target="_blank" rel="noopener noreferrer nofollow">{a.link}</a></p> : null}
              {a.status !== "withdrawn" ? (
                <div className="app-cluster" style={{ marginTop: "var(--space-3)" }}>
                  {a.status !== "shortlisted" && a.status !== "hired" ? <Button size="sm" variant="secondary" onClick={() => void decide(a, "shortlisted")}>Shortlist</Button> : null}
                  {a.status !== "hired" ? <Button size="sm" onClick={() => void decide(a, "hired")}>Mark hired</Button> : null}
                  {a.status !== "rejected" ? <Button size="sm" variant="ghost" onClick={() => void decide(a, "rejected")}>Decline</Button> : null}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
