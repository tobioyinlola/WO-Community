import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, BookmarkCheck, MapPin } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../auth/AuthProvider";
import { permissionsFor } from "../../admin/permissions";
import { compact, useCursorList } from "../../api/hooks";
import { api, unwrap } from "../../api/client";
import { messageOf } from "../../api/errors";
import type { components } from "../../api/schema";
import { Alert, Badge, Button, Card, Input, Select, Tabs, Textarea } from "../../components";
import { formatDate, humanise, timeAgo } from "../../lib/format";
import { htmlToText, textToHtml } from "../../lib/html";
import { EmptyState, LoadMore, Loaded, PageHeader, RichText, SkeletonRows } from "../../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";

type Job = components["schemas"]["Job"];
type JobType = components["schemas"]["JobTypeEnum"];
const TYPES: JobType[] = ["full_time", "part_time", "contract", "internship", "volunteer", "other"];
const typeOptions = TYPES.map((value) => ({ value, label: humanise(value) }));

function SaveButton({ job }: { job: Job }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: () =>
      job.saved
        ? unwrap(api.DELETE("/api/v1/jobs/{job_id}/save", { params: { path: { job_id: job.id } } }))
        : unwrap(api.POST("/api/v1/jobs/{job_id}/save", { params: { path: { job_id: job.id } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const Icon = job.saved ? BookmarkCheck : Bookmark;
  return (
    <button
      type="button"
      className="app-iconbtn"
      aria-label={job.saved ? "Remove from saved jobs" : "Save this job"}
      aria-pressed={job.saved}
      onClick={(event) => {
        event.preventDefault();
        save.mutate();
      }}
    >
      <Icon size={20} strokeWidth={1.5} />
    </button>
  );
}

function JobRow({ job }: { job: Job }) {
  return (
    <li className="app-list__item" style={{ position: "relative" }}>
      <div className="app-list__main">
        <Link className="app-list__title app-link" style={{ textDecoration: "none" }} to={`/app/jobs/${job.id}`}>
          {job.title}
        </Link>
        <ul className="app-meta">
          <li>{job.organisation || job.startup?.name}</li>
          {job.location ? (
            <li>
              <MapPin size={14} strokeWidth={1.5} aria-hidden="true" />
              {job.location}
            </li>
          ) : null}
          {job.remote ? <li>Remote friendly</li> : null}
          <li>{timeAgo(job.published_at)}</li>
        </ul>
      </div>
      <Badge variant="pro">{humanise(job.type)}</Badge>
      <SaveButton job={job} />
    </li>
  );
}

type View = "board" | "saved" | "mine";

export default function JobsPage() {
  const [view, setView] = useState<View>("board");
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [remote, setRemote] = useState(false);

  const list = useCursorList<Job>(["jobs", view, q, type, remote], (cursor) => {
    const paging = { limit: 15, ...(cursor ? { cursor } : {}) };
    if (view === "saved") return unwrap(api.GET("/api/v1/me/saved-jobs", { params: { query: paging } }));
    if (view === "mine") return unwrap(api.GET("/api/v1/me/jobs", { params: { query: paging } }));
    return unwrap(
      api.GET("/api/v1/jobs", {
        params: {
          query: {
            ...paging,
            ...compact({ q: q.trim(), type: type as JobType, remote: remote ? true : undefined }),
          },
        },
      }),
    );
  });

  const { me } = useAuth();
  const canModerate = permissionsFor(me?.roles ?? []).has("jobs.moderate");
  return (
    <>
      <PageHeader
        eyebrow="Jobs"
        title="Jobs and opportunities"
        lead="Roles posted by members of the community."
        actions={
          <Link className="wo-btn wo-btn--primary" to={canModerate ? "/admin/jobs?new=1" : "/app/jobs/new"}>
            Post a job
          </Link>
        }
      />
      <div className="app-tabs-scroll">
        <Tabs
          label="Which jobs"
          value={view}
          onChange={(id) => setView(id as View)}
          items={[
            { id: "board", label: "All jobs" },
            { id: "saved", label: "Saved" },
            { id: "mine", label: "Posted by me" },
          ]}
        />
      </div>
      {view === "board" ? (
        <div className="app-filterbar" role="search" aria-label="Filter jobs">
          <div className="app-filterbar__grow">
            <Input label="Search" placeholder="Title or company" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Select label="Type" value={type} onChange={(e) => setType(e.target.value)} options={[{ value: "", label: "Any type" }, ...typeOptions]} />
          <label className="wo-check" style={{ alignSelf: "flex-end", minHeight: 52 }}>
            <input type="checkbox" checked={remote} onChange={(e) => setRemote(e.target.checked)} />
            Remote friendly
          </label>
        </div>
      ) : null}
      {list.query.isPending ? <SkeletonRows /> : null}
      {list.query.isError ? <Alert tone="danger" title="We could not load jobs">{messageOf(list.query.error)}</Alert> : null}
      {list.isEmpty ? (
        <EmptyState
          title={view === "saved" ? "No saved jobs" : view === "mine" ? "You have not posted a job" : "No jobs match"}
          action={view === "mine" ? <Link className="wo-btn wo-btn--primary" to="/app/jobs/new">Post a job</Link> : undefined}
        >
          {view === "saved" ? "Tap the bookmark on any job to keep it here." : "Try changing the filters."}
        </EmptyState>
      ) : null}
      {list.items.length > 0 ? (
        <ul className="app-list">
          {list.items.map((job) => (
            <JobRow key={job.id} job={job} />
          ))}
        </ul>
      ) : null}
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
    </>
  );
}

/** How to apply. Applications go to the employer, never to WO Community. */
function ApplyBlock({ job }: { job: Job }) {
  const { url, email, host } = job.apply;
  if (!url && !email) return null;
  return (
    <div className="app-stack" style={{ marginTop: "var(--space-6)" }}>
      {url ? (
        <div className="app-stack" style={{ gap: "var(--space-1)" }}>
          <a className="wo-btn wo-btn--primary wo-btn--lg" style={{ width: "100%" }} href={url} target="_blank" rel="noopener noreferrer">
            Apply on the employer's site
          </a>
          <span className="caption app-muted">Opens {host} in a new tab</span>
        </div>
      ) : null}
      {email ? (
        <div className="app-stack" style={{ gap: "var(--space-1)" }}>
          <a className={url ? "wo-btn wo-btn--secondary wo-btn--lg" : "wo-btn wo-btn--primary wo-btn--lg"} style={{ width: "100%" }} href={`mailto:${email}?subject=${encodeURIComponent(`Application: ${job.title}`)}`}>
            Apply by email
          </a>
          <span className="caption app-muted">Writes to {email}</span>
        </div>
      ) : null}
      <p className="body-sm app-muted" style={{ margin: 0 }}>Applications are handled directly by the employer.</p>
    </div>
  );
}

export function JobDetail() {
  const { id = "" } = useParams();
  const client = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["jobs", "one", id],
    queryFn: () => unwrap(api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: id } } })),
  });
  const close = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/jobs/{job_id}/close", { params: { path: { job_id: id } } })),
    onSuccess: async () => {
      toast.show("Job closed");
      await client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  return (
    <Loaded query={query} skeleton={<SkeletonRows />}>
      {(job) => (
        <>
          <PageHeader
            eyebrow="Jobs"
            title={job.title}
            lead={[job.organisation || job.startup?.name, job.location, job.remote ? "Remote friendly" : ""].filter(Boolean).join(" · ")}
            actions={<SaveButton job={job} />}
          />
          <div className="app-split">
            <Card>
              <div className="app-stack app-stack--lg">
                <div className="app-cluster">
                  <Badge variant="pro">{humanise(job.type)}</Badge>
                  {job.status !== "published" ? <Badge variant="warning" dot>{humanise(job.status)}</Badge> : null}
                </div>
                {job.review_note ? <Alert tone="warning" title="From the reviewer">{job.review_note}</Alert> : null}
                <RichText html={job.description} />
                {job.requirements ? (
                  <>
                    <h2 className="h4" style={{ margin: 0 }}>Requirements</h2>
                    <RichText html={job.requirements} />
                  </>
                ) : null}
              </div>
            </Card>
            <aside className="app-stack">
              <Card>
                <dl className="app-kv">
                  {job.compensation ? (<><dt>Pay</dt><dd>{job.compensation}</dd></>) : null}
                  {job.deadline ? (<><dt>Apply by</dt><dd>{formatDate(job.deadline)}</dd></>) : null}
                  <dt>Posted</dt>
                  <dd>{formatDate(job.published_at ?? job.created_at)}</dd>
                  {job.poster ? (<><dt>By</dt><dd>{job.poster.name}</dd></>) : null}
                </dl>
                {job.status === "published" ? <ApplyBlock job={job} /> : null}
              </Card>
              {job.mine && (job.status === "rejected" || job.status === "pending") ? (
                <Link className="wo-btn wo-btn--secondary" to={`/app/jobs/${job.id}/edit`}>
                  {job.status === "rejected" ? "Edit and send back for review" : "Edit this job"}
                </Link>
              ) : null}
              {job.mine && job.status === "published" ? (
                <Link className="wo-btn wo-btn--ghost" to={`/app/jobs/${job.id}/edit`}>Edit this job</Link>
              ) : null}
              {job.mine && job.status === "published" ? (
                <Button variant="secondary" loading={close.isPending} onClick={() => close.mutate(undefined, { onSuccess: () => navigate("/app/jobs") })}>
                  Close this job
                </Button>
              ) : null}
            </aside>
          </div>
        </>
      )}
    </Loaded>
  );
}

export function NewJob() {
  const { id: editing = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const client = useQueryClient();
  const startups = useQuery({ queryKey: ["me", "startups"], queryFn: () => unwrap(api.GET("/api/v1/me/startups")) });
  const [f, setF] = useState({
    title: "",
    type: "full_time" as JobType,
    organisation: "",
    startup_id: "",
    location: "",
    remote: false,
    description: "",
    requirements: "",
    compensation: "",
    apply_url: "",
    apply_email: "",
    deadline: "",
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((c) => ({ ...c, [k]: v }));
  const [missing, setMissing] = useState("");

  // Editing: start from the job as it stands (a rejected job can be fixed and sent back).
  const existing = useQuery({
    queryKey: ["jobs", "one", editing],
    enabled: Boolean(editing),
    queryFn: () => unwrap(api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: editing } } })),
  });
  const [loaded, setLoaded] = useState("");
  if (existing.data && loaded !== existing.data.id) {
    const j = existing.data;
    setLoaded(j.id);
    setF({
      title: j.title,
      type: j.type as JobType,
      organisation: j.organisation,
      startup_id: j.startup?.id ?? "",
      location: j.location,
      remote: j.remote,
      description: htmlToText(j.description),
      requirements: htmlToText(j.requirements),
      compensation: j.compensation,
      apply_url: j.apply.url,
      apply_email: j.apply.email,
      deadline: j.deadline ?? "",
    });
  }

  // Most members post for their own startup, so start there.
  useEffect(() => {
    const first = startups.data?.[0];
    if (first) setF((c) => (c.startup_id || c.organisation ? c : { ...c, startup_id: first.id }));
  }, [startups.data]);

  const submit = useSubmit(async () => {
    if (!f.startup_id && !f.organisation.trim()) {
      setMissing("Choose your startup or name the organisation that is hiring.");
      return;
    }
    setMissing("");
    const body = {
          title: f.title.trim(),
          type: f.type,
          organisation: f.organisation.trim(),
          startup_id: f.startup_id || null,
          location: f.location.trim(),
          remote: f.remote,
          description: textToHtml(f.description),
          requirements: f.requirements.trim() ? textToHtml(f.requirements) : "",
          compensation: f.compensation.trim(),
          apply_url: f.apply_url.trim(),
          apply_email: f.apply_email.trim(),
          deadline: f.deadline || null,
        };
    const job = editing
      ? await (async () => {
          const current = await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: editing } } });
          const etag = current.response.headers.get("ETag") ?? "";
          return unwrap(api.PATCH("/api/v1/jobs/{job_id}", { params: { path: { job_id: editing }, header: { "If-Match": etag } }, body }));
        })()
      : await unwrap(api.POST("/api/v1/jobs", { body }));
    await client.invalidateQueries({ queryKey: ["jobs"] });
    toast.show(job.status === "pending" ? "Submitted. A moderator will review it before it goes live." : editing ? "Job updated" : "Job posted");
    navigate(`/app/jobs/${job.id}`);
  });
  const errors = errorsFrom(submit.error).fields;
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submit.run();
  };

  return (
    <>
      <PageHeader eyebrow="Jobs" title={editing ? "Edit job" : "Post a job"} lead={editing ? "Changing the title, company, how to apply or description sends a live job back for review." : "Tell people about the role. New posts may be reviewed before they appear."} />
      <form onSubmit={onSubmit} noValidate className="wo-container--narrow app-stack app-stack--lg" style={{ maxWidth: 720 }}>
        <FormError error={submit.error} />
        <Input label="Job title" value={f.title} onChange={(e) => set("title", e.target.value)} error={errors.title} />
        <div className="app-formgrid">
          <Select label="Type" value={f.type} onChange={(e) => set("type", e.target.value as JobType)} options={typeOptions} error={errors.type} />
          <Select
            label="For which startup?"
            value={f.startup_id}
            onChange={(e) => set("startup_id", e.target.value)}
            options={[{ value: "", label: "Not one of mine" }, ...(startups.data ?? []).map((s) => ({ value: s.id, label: s.name ?? "Untitled" }))]}
            error={errors.startup_id}
          />
          <Input label="Organisation" hint="Leave blank to use the startup's name." value={f.organisation} onChange={(e) => set("organisation", e.target.value)} error={errors.organisation ?? (missing || undefined)} />
          <Input label="Location" value={f.location} onChange={(e) => set("location", e.target.value)} error={errors.location} />
        </div>
        <label className="wo-check">
          <input type="checkbox" checked={f.remote} onChange={(e) => set("remote", e.target.checked)} />
          Remote friendly
        </label>
        <Textarea label="Description" rows={6} value={f.description} onChange={(e) => set("description", e.target.value)} error={errors.description} />
        <Textarea label="Requirements (optional)" rows={4} value={f.requirements} onChange={(e) => set("requirements", e.target.value)} error={errors.requirements} />
        <div className="app-formgrid">
          <Input label="Pay (optional)" value={f.compensation} onChange={(e) => set("compensation", e.target.value)} error={errors.compensation} />
          <Input label="Apply by (optional)" type="date" value={f.deadline} onChange={(e) => set("deadline", e.target.value)} error={errors.deadline} />
        </div>
        <fieldset className="app-stack" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="wo-label">How to apply</legend>
          <p className="body-sm app-muted" style={{ margin: 0 }}>
            People apply directly with you, not on WO Community. Give a link, an email address, or both.
          </p>
          <div className="app-formgrid">
            <Input label="Application link" type="url" placeholder="https://" value={f.apply_url} onChange={(e) => set("apply_url", e.target.value)} error={errors.apply_url} />
            <Input label="Application email" type="email" value={f.apply_email} onChange={(e) => set("apply_email", e.target.value)} error={errors.apply_email} />
          </div>
        </fieldset>
        <div className="app-cluster">
          <Button size="lg" type="submit" loading={submit.busy} disabled={startups.isPending || !f.title.trim() || !f.description.trim() || !(f.apply_url.trim() || f.apply_email.trim())}>
            {editing ? "Save job" : "Post job"}
          </Button>
          <Link className="wo-btn wo-btn--ghost" to="/app/jobs">Cancel</Link>
        </div>
      </form>
    </>
  );
}
