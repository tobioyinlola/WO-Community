import * as Dialog from "@radix-ui/react-dialog";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Button, Checkbox, Input, Modal, Select, Textarea } from "../components";
import { formatDate, humanise, timeAgo } from "../lib/format";
import { htmlToText, textToHtml } from "../lib/html";
import { EmptyState, ErrorState, LoadMore, PageHeader, RichText, Skeleton, useDocumentTitle } from "../ui/blocks";
import { FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { ReasonDialog } from "./dialogs";
import { StatusChip, type Tone } from "./kit/TableBits";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Job = components["schemas"]["AdminJob"];
type Tab = "active" | "pending" | "rejected" | "closed";
type Decision = "approve" | "reject" | "unpublish" | "remove" | "reopen" | "delete";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "active", label: "Active" },
  { id: "pending", label: "Pending review" },
  { id: "rejected", label: "Rejected" },
  { id: "closed", label: "Closed or expired" },
];
const TYPES = ["full_time", "part_time", "contract", "internship", "volunteer", "other"];
const TONE: Record<string, Tone> = { published: "success", pending: "warning", rejected: "danger", removed: "danger", closed: "neutral", expired: "neutral" };
const STATUS_LABEL: Record<string, string> = { published: "Live" };
const DONE: Record<Decision, string> = { approve: "Job approved and live", reject: "Job rejected", unpublish: "Job closed", remove: "Job removed", reopen: "Job reopened", delete: "Job deleted" };

/** The form for a new job or an edit of one. Applications are never taken here: the employer gets them. */
function JobForm({ job, onClose, onSaved }: { job?: Job; onClose: () => void; onSaved: () => Promise<void> }) {
  const guard = useStepUp();
  const toast = useToast();
  const [f, setF] = useState({
    title: job?.title ?? "",
    organisation: job?.organisation ?? "",
    type: job?.type ?? "full_time",
    location: job?.location ?? "",
    remote: job?.remote ?? false,
    description: job ? htmlToText(job.description) : "",
    compensation: job?.compensation ?? "",
    apply_url: job?.apply.url ?? "",
    apply_email: job?.apply.email ?? "",
    deadline: job?.deadline ?? "",
  });
  const set = <K extends keyof typeof f>(key: K, value: (typeof f)[K]) => setF((x) => ({ ...x, [key]: value }));
  const submit = useSubmit(async () => {
    const body = {
      title: f.title.trim(),
      organisation: f.organisation.trim(),
      type: f.type as "full_time",
      location: f.location.trim(),
      remote: f.remote,
      description: textToHtml(f.description),
      compensation: f.compensation.trim(),
      apply_url: f.apply_url.trim(),
      apply_email: f.apply_email.trim(),
      deadline: f.deadline || null,
    };
    if (job) {
      const current = await api.GET("/api/v1/admin/jobs/{job_id}", { params: { path: { job_id: job.id } } });
      const etag = current.response.headers.get("ETag") ?? "";
      await guard(() => unwrap(api.PATCH("/api/v1/admin/jobs/{job_id}", { params: { path: { job_id: job.id }, header: { "If-Match": etag } }, body })));
      toast.show("Job updated");
    } else {
      await guard(() => unwrap(api.POST("/api/v1/admin/jobs", { body })));
      toast.show("Job posted and live");
    }
    await onSaved();
    onClose();
  });
  const ready = f.title.trim() && f.organisation.trim() && f.description.trim() && (f.apply_url.trim() || f.apply_email.trim());
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Admin"
      title={job ? "Edit job" : "Post a job"}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button loading={submit.busy} disabled={!ready} onClick={() => void submit.run()}>{job ? "Save changes" : "Post job"}</Button>
        </>
      }
    >
      <div className="app-stack">
        <FormError error={submit.error} listFields />
        {!job ? <p className="body-sm app-muted" style={{ margin: 0 }}>Jobs you post go live at once, with no review.</p> : null}
        <Input label="Job title" value={f.title} maxLength={140} onChange={(e) => set("title", e.target.value)} />
        <Input label="Company or organisation" value={f.organisation} maxLength={120} onChange={(e) => set("organisation", e.target.value)} />
        <Select label="Type" value={f.type} onChange={(e) => set("type", e.target.value)} options={TYPES.map((t) => ({ value: t, label: humanise(t) }))} />
        <Input label="Location" value={f.location} maxLength={120} onChange={(e) => set("location", e.target.value)} />
        <Checkbox label="Remote" checked={f.remote} onChange={(e) => set("remote", e.target.checked)} />
        <Textarea label="Description" rows={6} value={f.description} onChange={(e) => set("description", e.target.value)} />
        <Input label="Pay (optional)" value={f.compensation} maxLength={120} onChange={(e) => set("compensation", e.target.value)} />
        <fieldset className="app-stack" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="wo-label">How to apply</legend>
          <p className="body-sm app-muted" style={{ margin: 0 }}>Applications are handled directly by the employer, not by WO Community. Give a link, an email address, or both.</p>
          <Input label="Application link" type="url" placeholder="https://" value={f.apply_url} onChange={(e) => set("apply_url", e.target.value)} />
          <Input label="Application email" type="email" value={f.apply_email} onChange={(e) => set("apply_email", e.target.value)} />
        </fieldset>
        <Input label="Apply by (optional)" type="date" value={f.deadline} onChange={(e) => set("deadline", e.target.value)} />
      </div>
    </Modal>
  );
}

function Drawer({ job, onClose, onDecide, onEdit }: { job: Job; onClose: () => void; onDecide: (d: Decision) => void; onEdit: () => void }) {
  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="adm-scrim adm-scrim--blur" />
        <Dialog.Content className="adm-sheet" aria-describedby={undefined}>
          <header className="adm-sheet__head">
            <div className="adm-sheet__meta"><span className="adm-sheet__label">Job</span></div>
            <Dialog.Close className="adm-iconbtn adm-iconbtn--ring" aria-label="Close"><X size={18} strokeWidth={1.5} aria-hidden="true" /></Dialog.Close>
          </header>
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
          <div className="adm-sheet__body" tabIndex={0} role="region" aria-label="Job details">
            <div>
              <Dialog.Title className="adm-sheet__title">{job.title}</Dialog.Title>
              <p className="adm-sheet__chips">
                <StatusChip tone={TONE[job.status] ?? "neutral"}>{STATUS_LABEL[job.status] ?? humanise(job.status)}</StatusChip>
                <span className="adm-sheet__age">{humanise(job.type)} · posted {timeAgo(job.created_at)} by {job.origin === "admin" ? "the team" : (job.poster?.name ?? "a member")}</span>
              </p>
            </div>
            <dl className="adm-kv">
              <div className="adm-kv__row"><dt>Company</dt><dd>{job.organisation || job.startup?.name || "Not given"}</dd></div>
              <div className="adm-kv__row"><dt>Where</dt><dd>{[job.location, job.remote ? "Remote" : ""].filter(Boolean).join(" · ") || "Not given"}</dd></div>
              {job.compensation ? <div className="adm-kv__row"><dt>Pay</dt><dd>{job.compensation}</dd></div> : null}
              <div className="adm-kv__row"><dt>Apply by</dt><dd>{job.deadline ? formatDate(job.deadline) : "No deadline"}</dd></div>
              {job.expires_at && job.status === "published" ? <div className="adm-kv__row"><dt>Expires</dt><dd>{formatDate(job.expires_at)}</dd></div> : null}
              <div className="adm-kv__row"><dt>How to apply</dt><dd>
                {job.apply.url ? <div>Link: <a href={job.apply.url} target="_blank" rel="noopener noreferrer">{job.apply.url}</a> <span className="app-faint">(opens {job.apply.host})</span></div> : null}
                {job.apply.email ? <div>Email: {job.apply.email}</div> : null}
              </dd></div>
            </dl>
            <section aria-labelledby="job-desc">
              <h3 className="adm-sheet__h" id="job-desc">Description</h3>
              <RichText html={job.description} />
              {job.requirements ? <><h3 className="adm-sheet__h">Requirements</h3><RichText html={job.requirements} /></> : null}
            </section>
            {job.review_note ? <p className="body-sm">Review note: {job.review_note}</p> : null}
          </div>
          <footer className="adm-sheet__foot">
            <div className="adm-sheet__actions" style={{ flexWrap: "wrap" }}>
              {job.status === "pending" ? (
                <>
                  <Button variant="secondary" onClick={() => onDecide("reject")}>Reject</Button>
                  <Button onClick={() => onDecide("approve")}>Approve</Button>
                </>
              ) : null}
              {job.status === "published" ? <Button variant="secondary" onClick={() => onDecide("unpublish")}>Close</Button> : null}
              {["closed", "expired", "removed"].includes(job.status) ? <Button onClick={() => onDecide("reopen")}>Reopen</Button> : null}
              {["pending", "published"].includes(job.status) ? <Button variant="secondary" onClick={onEdit}>Edit</Button> : null}
              {job.status !== "removed" ? <Button variant="ghost" onClick={() => onDecide("remove")}>Remove</Button> : null}
              <Button variant="ghost" onClick={() => onDecide("delete")}>Delete permanently</Button>
            </div>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function AdminJobs() {
  useDocumentTitle("Jobs");
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.id === params.get("tab"))?.id ?? "pending") as Tab;
  const get = (k: string) => params.get(k) ?? "";
  const set = (k: string, v: string) =>
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (v) next.set(k, v);
      else next.delete(k);
      return next;
    }, { replace: true });
  const [open, setOpen] = useState<Job | null>(null);
  const [acting, setActing] = useState<{ job: Job; decision: Decision } | null>(null);
  const [form, setForm] = useState<{ job?: Job } | null>(params.get("new") ? {} : null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const filters = {
    ...(get("q") ? { q: get("q") } : {}),
    ...(get("company") ? { company: get("company") } : {}),
    ...(get("type") ? { type: get("type") as "full_time" } : {}),
    ...(get("poster_id") ? { poster_id: get("poster_id") } : {}),
    ...(get("from") ? { date_from: get("from") } : {}),
    ...(get("to") ? { date_to: get("to") } : {}),
  };
  const key = JSON.stringify(filters);
  const counts = useQuery({
    queryKey: ["admin", "jobs", "stats", key],
    queryFn: () => unwrap(api.GET("/api/v1/admin/jobs/stats", { params: { query: filters } })),
  });
  const list = useOffsetList<Job>(["admin", "jobs", "list", tab, key], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/jobs", { params: { query: { tab, limit, offset, ...filters } } })),
  );
  const refresh = async () => {
    setSelected(new Set());
    await client.invalidateQueries({ queryKey: ["admin"] });
  };
  const decide = async (job: Job, decision: Decision, reason: string) => {
    await guard(async () => {
      if (decision === "delete") await unwrap(api.DELETE("/api/v1/admin/jobs/{job_id}", { params: { path: { job_id: job.id } } }));
      else await unwrap(api.POST(`/api/v1/admin/jobs/{job_id}/${decision}`, { params: { path: { job_id: job.id } }, body: { reason } }));
    });
    toast.show(DONE[decision]);
    setOpen(null);
    await refresh();
  };
  const bulk = useSubmit(async () => {
    const result = await guard(() => unwrap(api.POST("/api/v1/admin/jobs/bulk-approve", { body: { ids: [...selected] } })));
    toast.show(`${result.approved} approved${result.skipped ? `, ${result.skipped} skipped` : ""}`);
    await refresh();
  });
  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const filtered = Boolean(get("q") || get("company") || get("type") || get("poster_id") || get("from") || get("to"));

  return (
    <>
      <PageHeader
        eyebrow="Jobs"
        title="Jobs"
        lead="Roles are applied for with the employer, never here. Jobs you post go live at once; members' jobs wait for approval."
        actions={<Button onClick={() => setForm({})}>Post a job</Button>}
      />

      <div role="tablist" aria-label="Jobs by state" className="adm-tabs">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`jobs-tab-${t.id}`} aria-selected={tab === t.id} aria-controls="jobs-panel" className="adm-tabs__tab" onClick={() => { set("tab", t.id); setSelected(new Set()); }}>
            {t.label} <span className="adm-tabs__count">{counts.data ? counts.data[t.id] : "…"}</span>
          </button>
        ))}
      </div>

      <form className="adm-filterbar" role="search" aria-label="Filter jobs" onSubmit={(e) => e.preventDefault()}>
        <Input label="Search" placeholder="Title or company" value={get("q")} onChange={(e) => set("q", e.target.value)} />
        <Input label="Company" value={get("company")} onChange={(e) => set("company", e.target.value)} />
        <Select label="Type" value={get("type")} onChange={(e) => set("type", e.target.value)} options={[{ value: "", label: "Any type" }, ...TYPES.map((t) => ({ value: t, label: humanise(t) }))]} />
        <Input label="Posted from" type="date" value={get("from")} onChange={(e) => set("from", e.target.value)} />
        <Input label="Posted to" type="date" value={get("to")} onChange={(e) => set("to", e.target.value)} />
        {get("poster_id") ? <Button variant="ghost" onClick={() => set("poster_id", "")}>Clear poster filter</Button> : null}
      </form>

      <div id="jobs-panel" role="tabpanel" aria-labelledby={`jobs-tab-${tab}`}>
        {tab === "pending" && selected.size > 0 ? (
          <div className="app-cluster" style={{ marginBottom: "var(--space-3)" }}>
            <span className="body-sm" aria-live="polite">{selected.size} selected</span>
            <Button size="sm" loading={bulk.busy} onClick={() => void bulk.run()}>Approve selected</Button>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button>
          </div>
        ) : null}
        {list.query.isError ? (
          <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
        ) : list.query.isPending ? (
          <Skeleton height={200} />
        ) : list.isEmpty ? (
          <EmptyState title={filtered ? "No jobs match these filters" : tab === "pending" ? "Nothing waiting" : "No jobs here"}>
            {filtered ? "Try fewer filters." : tab === "pending" ? "Every submitted job has been reviewed." : "Jobs in this state will be listed here."}
          </EmptyState>
        ) : (
          <div className="adm-tablewrap">
            <table className="adm-table">
              <caption className="wo-visually-hidden">Jobs</caption>
              <thead>
                <tr>
                  {tab === "pending" ? <th scope="col"><span className="wo-visually-hidden">Select</span></th> : null}
                  <th scope="col">Job</th><th scope="col">Company</th><th scope="col">Posted by</th><th scope="col">Status</th><th scope="col">{tab === "active" ? "Expires" : "Posted"}</th>
                </tr>
              </thead>
              <tbody>
                {list.items.map((j) => (
                  <tr key={j.id} className="adm-row--click" onClick={() => setOpen(j)}>
                    {tab === "pending" ? (
                      <td onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" aria-label={`Select ${j.title}`} checked={selected.has(j.id)} onChange={() => toggle(j.id)} />
                      </td>
                    ) : null}
                    <td><button type="button" className="wo-linkbtn" onClick={(e) => { e.stopPropagation(); setOpen(j); }}>{j.title}</button></td>
                    <td>{j.organisation || j.startup?.name || "-"}</td>
                    <td>{j.origin === "admin" ? "The team" : (j.poster?.name ?? "A member")}</td>
                    <td><StatusChip tone={TONE[j.status] ?? "neutral"}>{STATUS_LABEL[j.status] ?? humanise(j.status)}</StatusChip></td>
                    <td>{tab === "active" && j.expires_at ? formatDate(j.expires_at) : timeAgo(j.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
      </div>

      {open ? <Drawer job={open} onClose={() => setOpen(null)} onDecide={(d) => setActing({ job: open, decision: d })} onEdit={() => { setForm({ job: open }); setOpen(null); }} /> : null}
      {acting ? (
        <ReasonDialog
          title={{ approve: "Approve this job?", reject: "Reject this job?", unpublish: "Close this job?", remove: "Remove this job?", reopen: "Reopen this job?", delete: "Delete this job for good?" }[acting.decision]}
          confirmLabel={{ approve: "Approve", reject: "Reject", unpublish: "Close", remove: "Remove", reopen: "Reopen", delete: "Delete permanently" }[acting.decision]}
          tone={acting.decision === "approve" || acting.decision === "reopen" ? "primary" : "danger"}
          required={acting.decision === "reject"}
          intro={acting.decision === "approve" ? "It goes live to members at once and the poster is told." : acting.decision === "reject" ? "The person who posted it is told why, and can fix it and send it back." : acting.decision === "reopen" ? "It goes back on the board for a new term." : acting.decision === "delete" ? "It is erased with its saves and cannot be reopened. Use Remove instead if you may want it back." : "The person who posted it is told."}
          onConfirm={(reason) => decide(acting.job, acting.decision, reason)}
          onClose={() => setActing(null)}
        />
      ) : null}
      {form ? <JobForm job={form.job} onClose={() => { setForm(null); set("new", ""); }} onSaved={refresh} /> : null}
    </>
  );
}
