import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap, unwrapTagged } from "../api/client";
import type { components } from "../api/schema";
import { Alert, Badge, Button, Card, Input, Modal, Select, StatTile } from "../components";
import { useCountries } from "../api/reference";
import { formatDateTime, humanise } from "../lib/format";
import { fromLocalInput } from "../lib/zoned";
import { EmptyState, ErrorState, Loaded, LoadMore, PageHeader, SkeletonCards, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { asBlocks, type Block, BlocksEditor } from "./Blocks";
import { ConfirmDialog } from "./dialogs";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Campaign = components["schemas"]["Campaign"];
type Segment = components["schemas"]["Segment"];
type Template = components["schemas"]["Template"];
type Definition = components["schemas"]["SegmentDefinitionRequest"];
type Tag = components["schemas"]["TagsEnum"];

const TAGS: Tag[] = ["profile_complete", "registered_incomplete", "directory_listed", "founder_active", "founder_dormant", "job_poster", "learner_free", "learner_paid", "course_completed", "mentor_applicant", "mentor_approved", "mentee"];
const TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "info"> = { sent: "success", sending: "info", scheduled: "warning", paused: "warning", cancelled: "danger", draft: "neutral" };
const ZONE = "Africa/Lagos";

// ---- Newsletters --------------------------------------------------------------------------

function CampaignEditor({ id, onClose, onSaved }: { id: string | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const guard = useStepUp();
  const existing = useQuery({
    queryKey: ["admin", "campaign", id],
    enabled: Boolean(id),
    queryFn: () => unwrapTagged(api.GET("/api/v1/admin/campaigns/{campaign_id}", { params: { path: { campaign_id: id ?? "" } } })),
  });
  const segments = useQuery({ queryKey: ["admin", "segments", "all"], queryFn: () => unwrap(api.GET("/api/v1/admin/segments", { params: { query: { limit: 100 } } })) });
  const templates = useQuery({ queryKey: ["admin", "templates"], queryFn: () => unwrap(api.GET("/api/v1/admin/campaign-templates")) });
  const [form, setForm] = useState<{ name: string; subject: string; preheader: string; segment_id: string; blocks: Block[]; template_id: string } | null>(id ? null : { name: "", subject: "", preheader: "", segment_id: "", blocks: [], template_id: "" });
  const [loadedFor, setLoadedFor] = useState("");
  if (id && existing.data && loadedFor !== existing.data.etag) {
    const c = existing.data.data;
    setLoadedFor(existing.data.etag);
    setForm({ name: c.name, subject: c.subject, preheader: c.preheader, segment_id: c.segment_id ?? "", blocks: asBlocks(c.blocks), template_id: "" });
  }
  const save = useSubmit(async () => {
    if (!form) return;
    const body = { name: form.name.trim(), subject: form.subject.trim(), preheader: form.preheader.trim(), segment_id: form.segment_id || null };
    await guard(() =>
      id
        ? unwrap(api.PATCH("/api/v1/admin/campaigns/{campaign_id}", { params: { path: { campaign_id: id }, header: { "If-Match": existing.data?.etag ?? "" } }, body: { ...body, blocks: form.blocks } }))
        : unwrap(api.POST("/api/v1/admin/campaigns", { body: form.template_id ? { ...body, template_id: form.template_id } : { ...body, blocks: form.blocks } })),
    );
    toast.show(id ? "Newsletter saved" : "Draft created");
    await onSaved();
    onClose();
  });
  const errors = errorsFrom(save.error).fields;
  const set = (patch: Partial<NonNullable<typeof form>>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const ready = form && form.name.trim() && form.subject.trim() && (form.template_id || form.blocks.length > 0);
  return (
    <Modal open onClose={onClose} eyebrow="Email" title={id ? "Edit newsletter" : "New newsletter"}
      actions={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={save.busy} disabled={!ready} onClick={() => void save.run()}>{id ? "Save" : "Save as draft"}</Button></>}>
      {id && existing.isPending ? <SkeletonRows /> : id && existing.isError ? <ErrorState error={existing.error} /> : form ? (
        <div className="app-stack">
          <FormError error={save.error} />
          <Input label="Name (only you see this)" value={form.name} onChange={(e) => set({ name: e.target.value })} error={errors.name} />
          <Input label="Subject line" value={form.subject} onChange={(e) => set({ subject: e.target.value })} error={errors.subject} />
          <Input label="Preview text (optional)" value={form.preheader} onChange={(e) => set({ preheader: e.target.value })} error={errors.preheader} />
          <Select label="Who gets it" options={[{ value: "", label: "Every member who has agreed to emails" }, ...(segments.data?.results ?? []).map((s) => ({ value: s.id, label: s.name }))]} value={form.segment_id} onChange={(e) => set({ segment_id: e.target.value })} error={errors.segment_id} />
          {!id && (templates.data?.length ?? 0) > 0 ? (
            <Select label="Start from a template (optional)" options={[{ value: "", label: "Write it myself" }, ...(templates.data ?? []).map((t) => ({ value: t.id, label: t.name }))]} value={form.template_id} onChange={(e) => set({ template_id: e.target.value })} />
          ) : null}
          {!form.template_id ? <BlocksEditor blocks={form.blocks} onChange={(blocks) => set({ blocks })} error={errors.blocks} /> : <p className="body-sm app-muted" style={{ margin: 0 }}>The template's content is used. You can edit it after saving.</p>}
        </div>
      ) : null}
    </Modal>
  );
}

function Report({ campaign, onClose }: { campaign: Campaign; onClose: () => void }) {
  const report = useQuery({ queryKey: ["admin", "campaign", campaign.id, "report"], queryFn: () => unwrap(api.GET("/api/v1/admin/campaigns/{campaign_id}/report", { params: { path: { campaign_id: campaign.id } } })) });
  const pct = (n: number) => `${Math.round(n * 100)}%`;
  return (
    <Modal open onClose={onClose} eyebrow={campaign.name} title="How it did" actions={<Button onClick={onClose}>Close</Button>}>
      <Loaded query={report} skeleton={<SkeletonRows />}>
        {(r) => (
          <div className="app-grid">
            <StatTile label="Recipients" value={String(r.recipients)} />
            <StatTile label="Delivered" value={String(r.delivered)} />
            <StatTile label="Opened" value={`${r.opened} (${pct(r.open_rate)})`} />
            <StatTile label="Clicked" value={`${r.clicked} (${pct(r.click_rate)})`} />
            <StatTile label="Bounced" value={String(r.bounced)} />
            <StatTile label="Unsubscribed" value={String(r.unsubscribed)} />
          </div>
        )}
      </Loaded>
    </Modal>
  );
}

function SchedulePrompt({ campaign, onClose, onDone }: { campaign: Campaign; onClose: () => void; onDone: () => Promise<void> }) {
  const guard = useStepUp();
  const toast = useToast();
  const [when, setWhen] = useState("");
  const save = useSubmit(async () => {
    await guard(() => unwrap(api.POST("/api/v1/admin/campaigns/{campaign_id}/schedule", { params: { path: { campaign_id: campaign.id } }, body: { scheduled_at: fromLocalInput(when, ZONE) } })));
    toast.show("Newsletter scheduled");
    await onDone();
    onClose();
  });
  return (
    <Modal open onClose={onClose} eyebrow="Email" title="Schedule this newsletter"
      actions={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={save.busy} disabled={!when} onClick={() => void save.run()}>Schedule</Button></>}>
      <div className="app-stack">
        <FormError error={save.error} />
        <Input label="Send at (Lagos time)" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
      </div>
    </Modal>
  );
}

type Act = "send" | "unschedule" | "pause" | "resume" | "cancel" | "delete";

/** The line in the send confirmation that says how many people it will reach. */
function AudienceCount({ campaignId }: { campaignId: string }) {
  const size = useQuery({
    queryKey: ["admin", "campaigns", campaignId, "audience"],
    queryFn: () => unwrap(api.GET("/api/v1/admin/campaigns/{campaign_id}/audience", { params: { path: { campaign_id: campaignId } } })),
  });
  if (size.isPending) return <strong role="status">Counting who it will reach…</strong>;
  if (size.isError) return <strong role="status">We could not count the audience.</strong>;
  return <strong role="status">It will go to {size.data.recipients.toLocaleString("en-NG")} {size.data.recipients === 1 ? "person" : "people"}.</strong>;
}

function Newsletters() {
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [scheduling, setScheduling] = useState<Campaign | null>(null);
  const [reporting, setReporting] = useState<Campaign | null>(null);
  const [confirm, setConfirm] = useState<{ campaign: Campaign; action: Act } | null>(null);
  const list = useOffsetList<Campaign>(["admin", "campaigns", status], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/campaigns", { params: { query: { limit, offset, ...(status ? { status: status as "draft" } : {}) } } })),
  );
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "campaigns"] });
  const test = async (c: Campaign) => {
    await guard(() => unwrap(api.POST("/api/v1/admin/campaigns/{campaign_id}/test", { params: { path: { campaign_id: c.id } }, body: {} as never })));
    toast.show("Test sent to your own email");
  };
  const run = async (c: Campaign, action: Act) => {
    const p = { params: { path: { campaign_id: c.id } } };
    const none = { ...p, body: {} as never };
    await guard(() => {
      if (action === "send") return unwrap(api.POST("/api/v1/admin/campaigns/{campaign_id}/send", none));
      if (action === "unschedule") return unwrap(api.POST("/api/v1/admin/campaigns/{campaign_id}/unschedule", none));
      if (action === "pause") return unwrap(api.POST("/api/v1/admin/campaigns/{campaign_id}/pause", none));
      if (action === "resume") return unwrap(api.POST("/api/v1/admin/campaigns/{campaign_id}/resume", none));
      if (action === "cancel") return unwrap(api.POST("/api/v1/admin/campaigns/{campaign_id}/cancel", none));
      return unwrap(api.DELETE("/api/v1/admin/campaigns/{campaign_id}", p));
    });
    toast.show({ send: "Sending has started", unschedule: "Schedule removed", pause: "Sending paused", resume: "Sending resumed", cancel: "Newsletter cancelled", delete: "Draft deleted" }[action]);
    await refresh();
  };
  const COPY: Record<Act, { title: string; body: string; label: string; tone: "primary" | "danger" }> = {
    send: { title: "Send this now?", body: "It goes to everyone in the audience who has not unsubscribed. This cannot be undone once it starts, but you can pause it.", label: "Send now", tone: "primary" },
    unschedule: { title: "Remove the schedule?", body: "It goes back to being a draft.", label: "Remove schedule", tone: "primary" },
    pause: { title: "Pause sending?", body: "No more emails go out until you resume.", label: "Pause", tone: "danger" },
    resume: { title: "Resume sending?", body: "The rest of the audience gets it.", label: "Resume", tone: "primary" },
    cancel: { title: "Cancel this newsletter?", body: "Emails not yet sent will not be sent.", label: "Cancel it", tone: "danger" },
    delete: { title: "Delete this draft?", body: "It is deleted for good.", label: "Delete", tone: "danger" },
  };
  return (
    <>
      <div className="app-cluster" style={{ justifyContent: "space-between", marginBottom: "var(--space-6)", alignItems: "flex-end" }}>
        <div style={{ minWidth: 220 }}><Select label="Show" options={[{ value: "", label: "All" }, ...["draft", "scheduled", "sending", "paused", "sent", "cancelled"].map((s) => ({ value: s, label: humanise(s) }))]} value={status} onChange={(e) => setStatus(e.target.value)} /></div>
        <Button onClick={() => setEditing("new")}>New newsletter</Button>
      </div>
      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} /> : list.isEmpty ? (
        <EmptyState title="No newsletters yet" action={<Button onClick={() => setEditing("new")}>Write the first one</Button>}>Drafts, scheduled and sent newsletters are listed here.</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((c) => (
              <li key={c.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <Badge variant={TONE[c.status] ?? "neutral"} dot>{humanise(c.status)}</Badge>
                    <span className="caption app-muted">{c.status === "scheduled" && c.scheduled_at ? `Goes out ${formatDateTime(c.scheduled_at)}` : c.finished_at ? `Finished ${formatDateTime(c.finished_at)}` : c.recipient_count ? `${c.recipient_count} recipients` : ""}</span>
                  </div>
                  <h2 className="h4" style={{ margin: "var(--space-3) 0 var(--space-1)" }}>{c.name}</h2>
                  <p className="body-sm app-muted" style={{ margin: 0 }}>Subject: {c.subject}</p>
                  <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                    {c.status === "draft" || c.status === "scheduled" ? <Button size="sm" variant="secondary" onClick={() => setEditing(c.id)}>Edit</Button> : null}
                    {c.status === "draft" || c.status === "scheduled" ? <Button size="sm" variant="secondary" onClick={() => void test(c)}>Send me a test</Button> : null}
                    {c.status === "draft" ? <Button size="sm" onClick={() => setConfirm({ campaign: c, action: "send" })}>Send now</Button> : null}
                    {c.status === "draft" ? <Button size="sm" variant="secondary" onClick={() => setScheduling(c)}>Schedule</Button> : null}
                    {c.status === "scheduled" ? <Button size="sm" variant="ghost" onClick={() => setConfirm({ campaign: c, action: "unschedule" })}>Remove schedule</Button> : null}
                    {c.status === "sending" ? <Button size="sm" variant="secondary" onClick={() => setConfirm({ campaign: c, action: "pause" })}>Pause</Button> : null}
                    {c.status === "paused" ? <Button size="sm" onClick={() => setConfirm({ campaign: c, action: "resume" })}>Resume</Button> : null}
                    {c.status === "sending" || c.status === "paused" || c.status === "scheduled" ? <Button size="sm" variant="ghost" onClick={() => setConfirm({ campaign: c, action: "cancel" })}>Cancel</Button> : null}
                    {c.status === "sent" || c.status === "sending" || c.status === "paused" ? <Button size="sm" variant="secondary" onClick={() => setReporting(c)}>Results</Button> : null}
                    {c.status === "draft" ? <Button size="sm" variant="ghost" onClick={() => setConfirm({ campaign: c, action: "delete" })} aria-label={`Delete ${c.name}`}>Delete</Button> : null}
                  </div>
                </Card>
              </li>
            ))}
          </ul>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
      {editing ? <CampaignEditor id={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={refresh} /> : null}
      {scheduling ? <SchedulePrompt campaign={scheduling} onClose={() => setScheduling(null)} onDone={refresh} /> : null}
      {reporting ? <Report campaign={reporting} onClose={() => setReporting(null)} /> : null}
      {confirm ? <ConfirmDialog title={COPY[confirm.action].title} body={<>{COPY[confirm.action].body}{confirm.action === "send" ? <> <AudienceCount campaignId={confirm.campaign.id} /></> : null}</>} confirmLabel={COPY[confirm.action].label} tone={COPY[confirm.action].tone} onConfirm={() => run(confirm.campaign, confirm.action)} onClose={() => setConfirm(null)} /> : null}
    </>
  );
}

// ---- Audiences ----------------------------------------------------------------------------

function SegmentEditor({ segment, onClose, onSaved }: { segment: Segment | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const guard = useStepUp();
  const countries = useCountries();
  const initial = (segment?.definition ?? {}) as Definition;
  const [name, setName] = useState(segment?.name ?? "");
  const [def, setDef] = useState<Definition>(initial);
  const [count, setCount] = useState<{ matching: number; eligible: number } | null>(null);
  const set = (patch: Definition) => {
    setCount(null);
    setDef((d) => {
      const next = { ...d, ...patch } as Record<string, unknown>;
      for (const k of Object.keys(next)) {
        const v = next[k];
        if (v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) delete next[k];
      }
      return next as Definition;
    });
  };
  const preview = useSubmit(async () => setCount(await guard(() => unwrap(api.POST("/api/v1/admin/segments/preview", { body: { definition: def } })))));
  const save = useSubmit(async () => {
    await guard(() =>
      segment
        ? unwrap(api.PATCH("/api/v1/admin/segments/{segment_id}", { params: { path: { segment_id: segment.id } }, body: { name: name.trim(), definition: def } }))
        : unwrap(api.POST("/api/v1/admin/segments", { body: { name: name.trim(), definition: def } })),
    );
    toast.show("Audience saved");
    await onSaved();
    onClose();
  });
  const toggle = <T extends string>(list: T[] | undefined, value: T): T[] => ((list ?? []).includes(value) ? (list ?? []).filter((v) => v !== value) : [...(list ?? []), value]);
  const errors = errorsFrom(save.error).fields;
  return (
    <Modal open onClose={onClose} eyebrow="Email" title={segment ? "Edit audience" : "New audience"}
      actions={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={save.busy} disabled={!name.trim()} onClick={() => void save.run()}>Save</Button></>}>
      <div className="app-stack">
        <FormError error={save.error ?? preview.error} />
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
        <fieldset style={{ border: 0, margin: 0, padding: 0 }}>
          <legend className="wo-label">Countries</legend>
          <div className="app-cluster">
            {(countries.data ?? []).slice(0, 24).map((c) => (
              <button key={c.value} type="button" className="app-react" aria-pressed={(def.country ?? []).includes(c.value)} onClick={() => set({ country: toggle(def.country, c.value) })}>{c.label}</button>
            ))}
          </div>
        </fieldset>
        <fieldset style={{ border: 0, margin: 0, padding: 0 }}>
          <legend className="wo-label">Roles</legend>
          <div className="app-cluster">
            {(["member", "mentor"] as const).map((r) => <button key={r} type="button" className="app-react" aria-pressed={(def.roles ?? []).includes(r)} onClick={() => set({ roles: toggle(def.roles, r) })}>{humanise(r)}</button>)}
          </div>
        </fieldset>
        <fieldset style={{ border: 0, margin: 0, padding: 0 }}>
          <legend className="wo-label">Who they are</legend>
          <div className="app-cluster">
            {TAGS.map((t) => <button key={t} type="button" className="app-react" aria-pressed={(def.tags ?? []).includes(t)} onClick={() => set({ tags: toggle(def.tags, t) })}>{humanise(t)}</button>)}
          </div>
        </fieldset>
        <div className="app-formgrid">
          <Input label="Joined after" type="date" value={def.joined_after ?? ""} onChange={(e) => set({ joined_after: e.target.value })} />
          <Input label="Joined before" type="date" value={def.joined_before ?? ""} onChange={(e) => set({ joined_before: e.target.value })} />
          <Input label="Active after" type="date" value={def.last_active_after ?? ""} onChange={(e) => set({ last_active_after: e.target.value })} />
          <Input label="Active before" type="date" value={def.last_active_before ?? ""} onChange={(e) => set({ last_active_before: e.target.value })} />
          <Input label="Profile at least (%)" type="number" min={0} max={100} value={def.completeness_min ?? ""} onChange={(e) => set({ completeness_min: e.target.value === "" ? undefined : Number(e.target.value) })} />
          <Input label="Profile at most (%)" type="number" min={0} max={100} value={def.completeness_max ?? ""} onChange={(e) => set({ completeness_max: e.target.value === "" ? undefined : Number(e.target.value) })} />
        </div>
        <div className="app-cluster">
          <Button size="sm" variant="secondary" loading={preview.busy} onClick={() => void preview.run()}>How many people is that?</Button>
          {count ? <span className="body-sm" role="status">{count.matching} match, and {count.eligible} of them have agreed to emails.</span> : null}
        </div>
      </div>
    </Modal>
  );
}

function Audiences() {
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [editing, setEditing] = useState<Segment | "new" | null>(null);
  const [removing, setRemoving] = useState<Segment | null>(null);
  const list = useOffsetList<Segment>(["admin", "segments"], (offset, limit) => unwrap(api.GET("/api/v1/admin/segments", { params: { query: { limit, offset } } })));
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "segments"] });
  return (
    <>
      <div className="app-cluster" style={{ justifyContent: "flex-end", marginBottom: "var(--space-6)" }}><Button onClick={() => setEditing("new")}>New audience</Button></div>
      {list.query.isPending ? <SkeletonCards count={2} /> : list.query.isError ? <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} /> : list.isEmpty ? (
        <EmptyState title="No saved audiences" action={<Button onClick={() => setEditing("new")}>Create one</Button>}>Save a group of members to send newsletters to again and again.</EmptyState>
      ) : (
        <>
          <ul className="app-list">
            {list.items.map((s) => (
              <li key={s.id}>
                <div className="app-list__item">
                  <div className="app-list__main"><p className="app-list__title">{s.name}</p><p className="app-list__meta">{Object.keys(s.definition).length} rule{Object.keys(s.definition).length === 1 ? "" : "s"}</p></div>
                  <Button size="sm" variant="secondary" onClick={() => setEditing(s)} aria-label={`Edit ${s.name}`}>Edit</Button>
                  <Button size="sm" variant="ghost" onClick={() => setRemoving(s)} aria-label={`Delete ${s.name}`}>Delete</Button>
                </div>
              </li>
            ))}
          </ul>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
      {editing ? <SegmentEditor segment={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={refresh} /> : null}
      {removing ? (
        <ConfirmDialog title="Delete this audience?" body={`“${removing.name}” is deleted. Newsletters already using it keep their recipients.`} confirmLabel="Delete" tone="danger" onClose={() => setRemoving(null)}
          onConfirm={async () => { await guard(() => unwrap(api.DELETE("/api/v1/admin/segments/{segment_id}", { params: { path: { segment_id: removing.id } } }))); toast.show("Audience deleted"); await refresh(); }} />
      ) : null}
    </>
  );
}

// ---- Templates ----------------------------------------------------------------------------

function TemplateEditor({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const guard = useStepUp();
  const [name, setName] = useState("");
  const [blocks, setBlocks] = useState<Block[]>([]);
  const save = useSubmit(async () => {
    await guard(() => unwrap(api.POST("/api/v1/admin/campaign-templates", { body: { name: name.trim(), blocks } })));
    toast.show("Template saved");
    await onSaved();
    onClose();
  });
  const errors = errorsFrom(save.error).fields;
  return (
    <Modal open onClose={onClose} eyebrow="Email" title="New template"
      actions={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={save.busy} disabled={!name.trim() || blocks.length === 0} onClick={() => void save.run()}>Save</Button></>}>
      <div className="app-stack">
        <FormError error={save.error} />
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
        <BlocksEditor blocks={blocks} onChange={setBlocks} error={errors.blocks} />
      </div>
    </Modal>
  );
}

function Templates() {
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [creating, setCreating] = useState(false);
  const [removing, setRemoving] = useState<Template | null>(null);
  const templates = useQuery({ queryKey: ["admin", "templates"], queryFn: () => unwrap(api.GET("/api/v1/admin/campaign-templates")) });
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "templates"] });
  return (
    <>
      <div className="app-cluster" style={{ justifyContent: "flex-end", marginBottom: "var(--space-6)" }}><Button onClick={() => setCreating(true)}>New template</Button></div>
      <Loaded query={templates} skeleton={<SkeletonCards count={2} />} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No templates yet" action={<Button onClick={() => setCreating(true)}>Create one</Button>}>A template is a layout you can start a newsletter from.</EmptyState>}>
        {(items) => (
          <ul className="app-list">
            {items.map((t) => (
              <li key={t.id}>
                <div className="app-list__item">
                  <div className="app-list__main"><p className="app-list__title">{t.name}</p><p className="app-list__meta">{t.blocks.length} blocks</p></div>
                  <Button size="sm" variant="ghost" onClick={() => setRemoving(t)} aria-label={`Delete ${t.name}`}>Delete</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Loaded>
      {creating ? <TemplateEditor onClose={() => setCreating(false)} onSaved={refresh} /> : null}
      {removing ? (
        <ConfirmDialog title="Delete this template?" body={`“${removing.name}” is deleted. Newsletters made from it are not affected.`} confirmLabel="Delete" tone="danger" onClose={() => setRemoving(null)}
          onConfirm={async () => { await guard(() => unwrap(api.DELETE("/api/v1/admin/campaign-templates/{template_id}", { params: { path: { template_id: removing.id } } }))); toast.show("Template deleted"); await refresh(); }} />
      ) : null}
    </>
  );
}

const TABS = [
  { id: "newsletters", label: "Newsletters" },
  { id: "audiences", label: "Audiences" },
  { id: "templates", label: "Templates" },
] as const;

export default function Email() {
  useDocumentTitle("Email");
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("newsletters");
  return (
    <>
      <PageHeader eyebrow="Content" title="Email" lead="Write to members, choose who gets it, and see how it landed." />
      <Alert tone="info" title="Sending needs a fresh code">Sending, scheduling and resuming a newsletter ask for a code from your authenticator app.</Alert>
      <div role="tablist" aria-label="Email sections" className="app-cluster" style={{ margin: "var(--space-6) 0" }}>
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id} aria-controls={`panel-${t.id}`} className="app-react" onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "newsletters" ? <Newsletters /> : tab === "audiences" ? <Audiences /> : <Templates />}
      </div>
    </>
  );
}
