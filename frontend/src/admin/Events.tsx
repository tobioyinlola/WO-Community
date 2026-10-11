import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, downloadFile, unwrap, unwrapTagged } from "../api/client";
import type { components } from "../api/schema";
import { Badge, Button, Card, Checkbox, Input, Modal, Select, Textarea } from "../components";
import { formatDateTime, humanise } from "../lib/format";
import { htmlToText, textToHtml } from "../lib/html";
import { fromLocalInput, toLocalInput, ZONES } from "../lib/zoned";
import { EmptyState, ErrorState, LoadMore, PageHeader, SkeletonCards, SkeletonRows, TableScroll, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { ConfirmDialog, ReasonDialog } from "./dialogs";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Event = components["schemas"]["AdminEvent"];
type Kind = components["schemas"]["EventTypeEnum"];
type Status = "draft" | "published" | "cancelled";

const KINDS: Kind[] = ["meetup", "workshop", "demo_day", "announcement"];
const TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = { published: "success", draft: "neutral", cancelled: "danger" };

interface Draft {
  type: Kind;
  title: string;
  description: string;
  starts_at: string;
  ends_at: string;
  timezone: string;
  location: string;
  link: string;
  capacity: string;
  registration_open: boolean;
  public: boolean;
  organiser_email: string;
  recording_url: string;
  summary: string;
}

const blank: Draft = {
  type: "meetup", title: "", description: "", starts_at: "", ends_at: "", timezone: "Africa/Lagos", location: "", link: "",
  capacity: "", registration_open: true, public: false, organiser_email: "", recording_url: "", summary: "",
};

function Editor({ id, onClose, onSaved }: { id: string | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const guard = useStepUp();
  const existing = useQuery({
    queryKey: ["admin", "event", id],
    enabled: Boolean(id),
    queryFn: () => unwrapTagged(api.GET("/api/v1/admin/events/{event_id}", { params: { path: { event_id: id ?? "" } } })),
  });
  const [draft, setDraft] = useState<Draft | null>(id ? null : blank);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  if (id && existing.data && loadedFor !== existing.data.etag) {
    const e = existing.data.data;
    setLoadedFor(existing.data.etag);
    setDraft({
      type: e.type as Kind, title: e.title, description: htmlToText(e.description), starts_at: toLocalInput(e.starts_at, e.timezone),
      ends_at: toLocalInput(e.ends_at, e.timezone), timezone: e.timezone, location: e.location, link: e.link,
      capacity: e.capacity === null ? "" : String(e.capacity), registration_open: e.registration_open, public: e.public,
      organiser_email: e.organiser_email, recording_url: e.recording_url, summary: e.summary,
    });
  }
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const save = useSubmit(async () => {
    if (!draft) return;
    const body = {
      type: draft.type, title: draft.title.trim(), description: textToHtml(draft.description),
      starts_at: fromLocalInput(draft.starts_at, draft.timezone), ends_at: fromLocalInput(draft.ends_at, draft.timezone),
      timezone: draft.timezone, location: draft.location.trim(), link: draft.link.trim(),
      capacity: draft.capacity.trim() ? Number(draft.capacity) : null, registration_open: draft.registration_open,
      public: draft.public, organiser_email: draft.organiser_email.trim(), recording_url: draft.recording_url.trim(), summary: draft.summary.trim(),
    };
    await guard(() =>
      id
        ? unwrap(api.PATCH("/api/v1/admin/events/{event_id}", { params: { path: { event_id: id }, header: { "If-Match": existing.data?.etag ?? "" } }, body }))
        : unwrap(api.POST("/api/v1/admin/events", { body })),
    );
    toast.show(id ? "Event saved" : "Draft created");
    await onSaved();
    onClose();
  });
  const errors = errorsFrom(save.error).fields;
  const ready = draft && draft.title.trim() && draft.starts_at && draft.ends_at && draft.description.trim();
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Events"
      title={id ? "Edit event" : "New event"}
      actions={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={save.busy} disabled={!ready} onClick={() => void save.run()}>{id ? "Save" : "Save as draft"}</Button></>}
    >
      {id && existing.isPending ? <SkeletonRows /> : id && existing.isError ? <ErrorState error={existing.error} /> : draft ? (
        <div className="app-stack">
          <FormError error={save.error} />
          <div className="app-formgrid">
            <Select label="Kind" options={KINDS.map((k) => ({ value: k, label: humanise(k) }))} value={draft.type} onChange={(e) => set("type", e.target.value as Kind)} error={errors.type} />
            <Select label="Time zone" options={ZONES} value={draft.timezone} onChange={(e) => set("timezone", e.target.value)} error={errors.timezone} />
          </div>
          <Input label="Title" value={draft.title} onChange={(e) => set("title", e.target.value)} error={errors.title} />
          <Textarea label="What it is" rows={5} hint="Leave a blank line between paragraphs." value={draft.description} onChange={(e) => set("description", e.target.value)} error={errors.description} />
          <div className="app-formgrid">
            <Input label="Starts" type="datetime-local" value={draft.starts_at} onChange={(e) => set("starts_at", e.target.value)} error={errors.starts_at} />
            <Input label="Ends" type="datetime-local" value={draft.ends_at} onChange={(e) => set("ends_at", e.target.value)} error={errors.ends_at} />
            <Input label="Where (place or Online)" value={draft.location} onChange={(e) => set("location", e.target.value)} error={errors.location} />
            <Input label="Joining link" value={draft.link} onChange={(e) => set("link", e.target.value)} error={errors.link} />
            <Input label="Places (blank for no limit)" type="number" min={1} value={draft.capacity} onChange={(e) => set("capacity", e.target.value)} error={errors.capacity} />
            <Input label="Organiser email" type="email" value={draft.organiser_email} onChange={(e) => set("organiser_email", e.target.value)} error={errors.organiser_email} />
          </div>
          <Checkbox label="Registration is open" checked={draft.registration_open} onChange={(e) => set("registration_open", e.target.checked)} />
          <Checkbox label="Show on the public site" checked={draft.public} onChange={(e) => set("public", e.target.checked)} />
          <details>
            <summary>After the event</summary>
            <div className="app-stack" style={{ marginTop: "var(--space-3)" }}>
              <Input label="Recording link" value={draft.recording_url} onChange={(e) => set("recording_url", e.target.value)} error={errors.recording_url} />
              <Textarea label="Summary" rows={3} value={draft.summary} onChange={(e) => set("summary", e.target.value)} error={errors.summary} />
            </div>
          </details>
        </div>
      ) : null}
    </Modal>
  );
}

function Attendees({ event, onClose }: { event: Event; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const list = useOffsetList<components["schemas"]["Attendee"]>(["admin", "attendees", event.id], (offset, limit) =>
    guard(() => unwrap(api.GET("/api/v1/admin/events/{event_id}/attendees", { params: { path: { event_id: event.id }, query: { limit, offset } } }))),
  );
  const mark = async (userId: string, present: boolean) => {
    await guard(() => unwrap(api.POST("/api/v1/admin/events/{event_id}/attendees/{user_id}/check-in", { params: { path: { event_id: event.id, user_id: userId } }, body: { present } })));
    await client.invalidateQueries({ queryKey: ["admin", "attendees", event.id] });
  };
  const send = useSubmit(async () => {
    const r = await guard(() => unwrap(api.POST("/api/v1/admin/events/{event_id}/attendees/send", { params: { path: { event_id: event.id } } })));
    toast.show(r.sent_to_organiser ? "List emailed to the organiser" : "List emailed to you, as the event has no organiser email");
  });
  const csv = useSubmit(async () => {
    await guard(() => downloadFile(`/api/v1/admin/events/${event.id}/attendees.csv`, `${event.slug}-attendees.csv`));
  });
  return (
    <Modal open onClose={onClose} eyebrow={event.title} title="Who registered" actions={<Button variant="ghost" onClick={onClose}>Close</Button>}>
      <div className="app-stack">
        <p className="body-sm app-muted" style={{ margin: 0 }}>Names and email addresses are personal data. Opening this list is logged.</p>
        <FormError error={send.error ?? csv.error} />
        <div className="app-cluster">
          <Button size="sm" variant="secondary" loading={csv.busy} onClick={() => void csv.run()}>Download CSV</Button>
          <Button size="sm" variant="secondary" loading={send.busy} onClick={() => void send.run()}>Email the list to the organiser</Button>
        </div>
        {list.query.isPending ? <SkeletonRows /> : list.query.isError ? <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} /> : list.isEmpty ? (
          <EmptyState title="Nobody yet">No one has registered.</EmptyState>
        ) : (
          <>
            <TableScroll label="Attendees">
              <table className="app-table">
                <caption className="wo-visually-hidden">Attendees</caption>
                <thead><tr><th scope="col">Name</th><th scope="col">Registered</th><th scope="col">Present</th></tr></thead>
                <tbody>
                  {list.items.map((a) => (
                    <tr key={a.user_id}>
                      <th scope="row"><span style={{ display: "block" }}>{a.name}</span><span className="caption app-muted">{a.email}</span></th>
                      <td>{formatDateTime(a.registered_at)}</td>
                      <td><Checkbox label={<span className="wo-visually-hidden">{`${a.name} is present`}</span>} checked={Boolean(a.checked_in_at)} onChange={(e) => void mark(a.user_id, e.target.checked)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
            <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
          </>
        )}
      </div>
    </Modal>
  );
}

export default function Events() {
  useDocumentTitle("Events");
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [status, setStatus] = useState<Status | "">("");
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [people, setPeople] = useState<Event | null>(null);
  const [acting, setActing] = useState<{ event: Event; action: "publish" | "unpublish" | "cancel" } | null>(null);

  const list = useOffsetList<Event>(["admin", "events", status], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/events", { params: { query: { limit, offset, ...(status ? { status } : {}) } } })),
  );
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "events"] });
  const run = async (event: Event, action: "publish" | "unpublish" | "cancel", reason: string) => {
    const args = { params: { path: { event_id: event.id } }, body: { reason } };
    await guard(() => {
      if (action === "publish") return unwrap(api.POST("/api/v1/admin/events/{event_id}/publish", args));
      if (action === "unpublish") return unwrap(api.POST("/api/v1/admin/events/{event_id}/unpublish", args));
      return unwrap(api.POST("/api/v1/admin/events/{event_id}/cancel", args));
    });
    toast.show({ publish: "Event published", unpublish: "Event taken back to draft", cancel: "Event cancelled" }[action]);
    await refresh();
  };

  return (
    <>
      <PageHeader eyebrow="Content" title="Events" lead="Meetups, workshops and demo days." actions={<Button onClick={() => setEditing("new")}>New event</Button>} />
      <div style={{ maxWidth: 240, marginBottom: "var(--space-6)" }}>
        <Select label="Show" options={[{ value: "", label: "All" }, ...(["draft", "published", "cancelled"] as Status[]).map((s) => ({ value: s, label: humanise(s) }))]} value={status} onChange={(e) => setStatus(e.target.value as Status | "")} />
      </div>
      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title="No events yet" action={<Button onClick={() => setEditing("new")}>Create the first one</Button>}>Events you create will be listed here.</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((e) => (
              <li key={e.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <div className="app-cluster">
                      <Badge variant={TONE[e.status] ?? "neutral"} dot>{humanise(e.status)}</Badge>
                      <Badge variant="neutral">{humanise(e.type)}</Badge>
                      {e.past ? <Badge variant="neutral">Past</Badge> : null}
                    </div>
                    <span className="caption app-muted">{e.registered_count} registered{e.capacity ? ` of ${e.capacity}` : ""}</span>
                  </div>
                  <h2 className="h4" style={{ margin: "var(--space-3) 0 var(--space-1)" }}>{e.title}</h2>
                  <p className="body-sm app-muted" style={{ margin: 0 }}>{formatDateTime(e.starts_at)}{e.location ? ` · ${e.location}` : ""}</p>
                  <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                    {e.status !== "cancelled" ? <Button size="sm" variant="secondary" onClick={() => setEditing(e.id)}>Edit</Button> : null}
                    {e.status === "draft" ? <Button size="sm" onClick={() => setActing({ event: e, action: "publish" })}>Publish</Button> : null}
                    {e.status === "published" && e.registered_count === 0 ? <Button size="sm" variant="ghost" onClick={() => setActing({ event: e, action: "unpublish" })}>Back to draft</Button> : null}
                    {e.status === "published" && !e.past ? <Button size="sm" variant="ghost" onClick={() => setActing({ event: e, action: "cancel" })}>Cancel event</Button> : null}
                    {e.status !== "draft" ? <Button size="sm" variant="secondary" onClick={() => setPeople(e)}>Attendees</Button> : null}
                  </div>
                </Card>
              </li>
            ))}
          </ul>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
      {editing ? <Editor id={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={refresh} /> : null}
      {people ? <Attendees event={people} onClose={() => setPeople(null)} /> : null}
      {acting && acting.action === "cancel" ? (
        <ReasonDialog title="Cancel this event?" confirmLabel="Cancel the event" tone="danger" intro="Everyone registered is emailed with your reason." onConfirm={(reason) => run(acting.event, "cancel", reason)} onClose={() => setActing(null)} />
      ) : null}
      {acting && acting.action !== "cancel" ? (
        <ConfirmDialog
          title={acting.action === "publish" ? "Publish this event?" : "Take this event back to draft?"}
          body={acting.action === "publish" ? "Members can see it and register. The start time must be in the future." : "It is hidden from members again. Only possible while nobody has registered."}
          confirmLabel={acting.action === "publish" ? "Publish" : "Back to draft"}
          onConfirm={() => run(acting.event, acting.action as "publish" | "unpublish", "")}
          onClose={() => setActing(null)}
        />
      ) : null}
    </>
  );
}
