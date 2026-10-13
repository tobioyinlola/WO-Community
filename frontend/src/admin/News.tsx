import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap, unwrapTagged } from "../api/client";
import type { components } from "../api/schema";
import { Badge, Button, Card, Checkbox, Input, Modal, Select, Textarea } from "../components";
import { formatDate, formatDateTime, humanise } from "../lib/format";
import { htmlToText, textToHtml } from "../lib/html";
import { fromLocalInput, toLocalInput } from "../lib/zoned";
import { EmptyState, ErrorState, LoadMore, PageHeader, SkeletonCards, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { ConfirmDialog } from "./dialogs";
import { useStepUp } from "./StepUp";
import { TickerView } from "../ui/BannerTicker";
import { useOffsetList } from "./useOffsetList";

type Item = components["schemas"]["AdminItem"];
type Kind = components["schemas"]["EditorialTypeEnum"];
type Status = "draft" | "scheduled" | "published";

const KINDS: Kind[] = ["news", "announcement", "award", "celebration", "partnership", "funding"];
const TONE: Record<string, "success" | "warning" | "neutral"> = { published: "success", scheduled: "warning", draft: "neutral" };
const ZONE = "Africa/Lagos";

interface Draft {
  type: Kind;
  title: string;
  body: string;
  external_url: string;
  comments_enabled: boolean;
  public: boolean;
  banner_starts_at: string;
  banner_ends_at: string;
  show_banner: boolean;
  banner_text: string;
  banner_kind: "announcement" | "news" | "urgent";
  banner_link: string;
}

const blank: Draft = { type: "news", title: "", body: "", external_url: "", comments_enabled: true, public: false, banner_starts_at: "", banner_ends_at: "", show_banner: false, banner_text: "", banner_kind: "announcement", banner_link: "" };
const BANNER_STATE: Record<string, string> = { scheduled: "Banner scheduled", live: "Banner live", expired: "Banner ended" };

function toDraft(item: Item): Draft {
  return {
    type: item.type as Kind,
    title: item.title,
    body: htmlToText(item.body),
    external_url: item.external_url,
    comments_enabled: item.comments_enabled,
    public: item.public,
    banner_starts_at: item.banner_starts_at ? toLocalInput(item.banner_starts_at, ZONE) : "",
    banner_ends_at: item.banner_ends_at ? toLocalInput(item.banner_ends_at, ZONE) : "",
    show_banner: item.show_banner,
    banner_text: item.banner_text,
    banner_kind: item.banner_kind as Draft["banner_kind"],
    banner_link: item.banner_link,
  };
}

function Editor({ id, onClose, onSaved }: { id: string | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const guard = useStepUp();
  // Editing needs the version the story is at now, so it is read first.
  const existing = useQuery({
    queryKey: ["admin", "story", id],
    enabled: Boolean(id),
    queryFn: () => unwrapTagged(api.GET("/api/v1/admin/editorial/{item_id}", { params: { path: { item_id: id ?? "" } } })),
  });
  const [draft, setDraft] = useState<Draft | null>(id ? null : blank);
  const [loadedFor, setLoadedFor] = useState("");
  if (id && existing.data && loadedFor !== existing.data.etag) {
    setLoadedFor(existing.data.etag);
    setDraft(toDraft(existing.data.data));
  }
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const save = useSubmit(async () => {
    if (!draft) return;
    const body = {
      type: draft.type,
      title: draft.title.trim(),
      body: textToHtml(draft.body),
      external_url: draft.external_url.trim(),
      comments_enabled: draft.comments_enabled,
      public: draft.public,
      banner_starts_at: draft.banner_starts_at ? fromLocalInput(draft.banner_starts_at, ZONE) : null,
      banner_ends_at: draft.banner_ends_at ? fromLocalInput(draft.banner_ends_at, ZONE) : null,
      show_banner: draft.show_banner,
      banner_text: draft.banner_text.trim(),
      banner_kind: draft.banner_kind,
      banner_link: draft.banner_link.trim(),
    };
    await guard(() =>
      id
        ? unwrap(api.PATCH("/api/v1/admin/editorial/{item_id}", { params: { path: { item_id: id }, header: { "If-Match": existing.data?.etag ?? "" } }, body }))
        : unwrap(api.POST("/api/v1/admin/editorial", { body })),
    );
    toast.show(id ? "Story saved" : "Draft created");
    await onSaved();
    onClose();
  });
  const errors = errorsFrom(save.error).fields;
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="News"
      title={id ? "Edit story" : "New story"}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button loading={save.busy} disabled={!draft || !draft.title.trim() || !draft.body.trim()} onClick={() => void save.run()}>{id ? "Save" : "Save as draft"}</Button>
        </>
      }
    >
      {id && existing.isPending ? <SkeletonRows /> : id && existing.isError ? <ErrorState error={existing.error} /> : draft ? (
      <div className="app-stack">
        <FormError error={save.error} />
        <Select label="Kind" options={KINDS.map((k) => ({ value: k, label: humanise(k) }))} value={draft.type} onChange={(e) => set("type", e.target.value as Kind)} error={errors.type} />
        <Input label="Title" value={draft.title} onChange={(e) => set("title", e.target.value)} error={errors.title} />
        <Textarea label="Story" rows={8} hint="Leave a blank line between paragraphs." value={draft.body} onChange={(e) => set("body", e.target.value)} error={errors.body} />
        <Input label="Link to read more (optional)" value={draft.external_url} onChange={(e) => set("external_url", e.target.value)} error={errors.external_url} />
        <Checkbox label="Members can comment" checked={draft.comments_enabled} onChange={(e) => set("comments_enabled", e.target.checked)} />
        <Checkbox label="Show on the public site" checked={draft.public} onChange={(e) => set("public", e.target.checked)} />
        <Checkbox label="Show in the dashboard banner" checked={draft.show_banner} onChange={(e) => set("show_banner", e.target.checked)} />
        {draft.show_banner ? (
          <fieldset className="app-stack" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="wo-label">Banner</legend>
            <Input label="Banner text" hint={`${draft.banner_text.length} of 140. Leave empty to use the title.`} maxLength={140} placeholder={draft.title} value={draft.banner_text} onChange={(e) => set("banner_text", e.target.value)} error={errors.banner_text} />
            <Input label="Link (optional)" hint="A page in the app, such as /jobs, or a full https address. Empty opens this story." value={draft.banner_link} onChange={(e) => set("banner_link", e.target.value)} error={errors.banner_link} />
            <Select label="Type" options={[{ value: "announcement", label: "Announcement" }, { value: "news", label: "News" }, { value: "urgent", label: "Urgent" }]} value={draft.banner_kind} onChange={(e) => set("banner_kind", e.target.value as Draft["banner_kind"])} error={errors.banner_kind} />
            <div className="app-formgrid">
              <Input label="Starts (Lagos time)" type="datetime-local" value={draft.banner_starts_at} onChange={(e) => set("banner_starts_at", e.target.value)} error={errors.banner_starts_at} />
              <Input label="Ends (Lagos time)" type="datetime-local" value={draft.banner_ends_at} onChange={(e) => set("banner_ends_at", e.target.value)} error={errors.banner_ends_at} />
            </div>
            <div>
              <p className="wo-label" style={{ margin: "0 0 var(--space-2)" }}>Preview</p>
              <TickerView preview items={[{ id: "preview", kind: draft.banner_kind, text: draft.banner_text.trim() || draft.title || "Your banner text", link: draft.banner_link || "/news" }]} />
            </div>
          </fieldset>
        ) : null}
      </div>
      ) : null}
    </Modal>
  );
}

function Schedule({ item, onClose, onDone }: { item: Item; onClose: () => void; onDone: () => Promise<void> }) {
  const guard = useStepUp();
  const toast = useToast();
  const [when, setWhen] = useState("");
  const save = useSubmit(async () => {
    await guard(() => unwrap(api.POST("/api/v1/admin/editorial/{item_id}/schedule", { params: { path: { item_id: item.id } }, body: { publish_at: fromLocalInput(when, ZONE) } })));
    toast.show("Story scheduled");
    await onDone();
    onClose();
  });
  return (
    <Modal open onClose={onClose} eyebrow="News" title="Schedule this story"
      actions={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={save.busy} disabled={!when} onClick={() => void save.run()}>Schedule</Button></>}>
      <div className="app-stack">
        <FormError error={save.error} />
        <Input label="Publish at (Lagos time)" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
      </div>
    </Modal>
  );
}

export default function News() {
  useDocumentTitle("News");
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [status, setStatus] = useState<Status | "">("");
  const [editing, setEditing] = useState<Item | "new" | null>(null);
  const [scheduling, setScheduling] = useState<Item | null>(null);
  const [confirm, setConfirm] = useState<{ item: Item; action: "publish" | "unpublish" } | null>(null);

  const list = useOffsetList<Item>(["admin", "editorial", status], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/editorial", { params: { query: { limit, offset, ...(status ? { status } : {}) } } })),
  );
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "editorial"] });

  const run = async (item: Item, action: "publish" | "unpublish") => {
    const path = { params: { path: { item_id: item.id } } };
    await guard(() =>
      action === "publish" ? unwrap(api.POST("/api/v1/admin/editorial/{item_id}/publish", path)) : unwrap(api.POST("/api/v1/admin/editorial/{item_id}/unpublish", path)),
    );
    toast.show(action === "publish" ? "Story published" : "Story taken down");
    await refresh();
  };

  const endBanner = async (item: Item) => {
    await guard(() => unwrap(api.POST("/api/v1/admin/editorial/{item_id}/end-banner", { params: { path: { item_id: item.id } } })));
    toast.show("The banner has ended");
    await refresh();
  };

  return (
    <>
      <PageHeader eyebrow="Content" title="News" lead="Stories, announcements and wins shared with the community." actions={<Button onClick={() => setEditing("new")}>New story</Button>} />
      <div style={{ maxWidth: 240, marginBottom: "var(--space-6)" }}>
        <Select label="Show" options={[{ value: "", label: "All" }, ...(["draft", "scheduled", "published"] as Status[]).map((s) => ({ value: s, label: humanise(s) }))]} value={status} onChange={(e) => setStatus(e.target.value as Status | "")} />
      </div>
      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title="No stories yet" action={<Button onClick={() => setEditing("new")}>Write the first one</Button>}>Drafts, scheduled and published stories will be listed here.</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((i) => (
              <li key={i.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <div className="app-cluster">
                      <Badge variant={TONE[i.status] ?? "neutral"} dot>{humanise(i.status)}</Badge>
                      <Badge variant="neutral">{humanise(i.type)}</Badge>
                      {i.public ? <Badge variant="info">Public</Badge> : null}
                      {i.banner_status !== "off" ? <Badge variant={i.banner_status === "live" ? "success" : "neutral"} dot>{BANNER_STATE[i.banner_status]}</Badge> : null}
                    </div>
                    <span className="caption app-muted">
                      {i.status === "published" && i.published_at ? `Published ${formatDate(i.published_at)}` : i.status === "scheduled" && i.publish_at ? `Goes out ${formatDateTime(i.publish_at)}` : `Edited ${formatDate(i.edited_at ?? i.created_at)}`}
                    </span>
                  </div>
                  <h2 className="h4" style={{ margin: "var(--space-3) 0 var(--space-1)" }}>{i.title}</h2>
                  {i.excerpt ? <p className="body-sm app-muted" style={{ margin: 0 }}>{i.excerpt}</p> : null}
                  {i.status === "published" ? <p className="caption app-muted" style={{ margin: "var(--space-2) 0 0" }}>{i.reaction_count} reactions, {i.comment_count} comments</p> : null}
                  <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                    <Button size="sm" variant="secondary" onClick={() => setEditing(i)}>Edit</Button>
                    {i.status !== "published" ? <Button size="sm" onClick={() => setConfirm({ item: i, action: "publish" })}>Publish now</Button> : null}
                    {i.status === "draft" ? <Button size="sm" variant="secondary" onClick={() => setScheduling(i)}>Schedule</Button> : null}
                    {i.banner_status === "live" || i.banner_status === "scheduled" ? <Button size="sm" variant="ghost" onClick={() => void endBanner(i)}>End banner now</Button> : null}
                    {i.status !== "draft" ? <Button size="sm" variant="ghost" onClick={() => setConfirm({ item: i, action: "unpublish" })}>{i.status === "scheduled" ? "Cancel schedule" : "Take down"}</Button> : null}
                  </div>
                </Card>
              </li>
            ))}
          </ul>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
      {editing ? <Editor id={editing === "new" ? null : editing.id} onClose={() => setEditing(null)} onSaved={refresh} /> : null}
      {scheduling ? <Schedule item={scheduling} onClose={() => setScheduling(null)} onDone={refresh} /> : null}
      {confirm ? (
        <ConfirmDialog
          title={confirm.action === "publish" ? "Publish this story?" : confirm.item.status === "scheduled" ? "Cancel the schedule?" : "Take this story down?"}
          body={confirm.action === "publish" ? "Members can read it straight away, and anyone following it is told." : "It goes back to being a draft and is hidden from members."}
          confirmLabel={confirm.action === "publish" ? "Publish" : "Confirm"}
          tone={confirm.action === "publish" ? "primary" : "danger"}
          onConfirm={() => run(confirm.item, confirm.action)}
          onClose={() => setConfirm(null)}
        />
      ) : null}
    </>
  );
}
