import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Button, Checkbox, Modal, Select, Textarea, Input } from "../components";
import { humanise } from "../lib/format";
import { textToHtml } from "../lib/html";
import { FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";

type Post = components["schemas"]["AdminPost"];

const CATEGORIES = ["update", "question", "win", "resource", "event", "opportunity"];

/** Local time from the date-time input to the moment the server expects, or null when empty. */
const toIso = (local: string) => (local ? new Date(local).toISOString() : null);
const toLocal = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = new Date(iso);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
};

/** Write a post as the team or as yourself, or change one. Team posts are never held for review. */
export function TeamPostForm({ post, onClose, onSaved }: { post?: Post; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const scheduled = Boolean(post?.scheduled_for);
  const [f, setF] = useState({
    category: post?.category ?? "update",
    text: post ? post.excerpt : "",
    official: post?.official ?? true,
    pin: post?.pinned ?? false,
    pinnedUntil: toLocal(post?.pinned_until),
    comments: post?.comments_enabled ?? true,
    audience: post?.audience_roles.length ? post.audience_roles[0] ?? "" : "",
    when: toLocal(post?.scheduled_for),
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }));
  const submit = useSubmit(async () => {
    const audience_roles = f.audience ? [f.audience] : [];
    if (post) {
      await unwrap(
        api.PATCH("/api/v1/admin/posts/{post_id}", {
          params: { path: { post_id: post.id } },
          body: {
            ...(f.text.trim() && f.text !== post.excerpt ? { body: textToHtml(f.text) } : {}),
            category: f.category as "update",
            official: f.official,
            comments_enabled: f.comments,
            audience_roles,
            pinned_until: f.pin ? toIso(f.pinnedUntil) : null,
            ...(scheduled ? { scheduled_for: toIso(f.when) } : {}),
          },
        }),
      );
      toast.show("Post updated");
    } else {
      await unwrap(
        api.POST("/api/v1/admin/posts", {
          body: {
            category: f.category as "update",
            body: textToHtml(f.text),
            official: f.official,
            pin: f.pin,
            pinned_until: f.pin ? toIso(f.pinnedUntil) : null,
            comments_enabled: f.comments,
            audience_roles,
            scheduled_for: toIso(f.when),
          },
        }),
      );
      toast.show(f.when ? "Post scheduled" : "Post published");
    }
    await onSaved();
    onClose();
  });
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Admin"
      title={post ? "Edit post" : "New post"}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button loading={submit.busy} disabled={!f.text.trim()} onClick={() => void submit.run()}>{post ? "Save" : f.when ? "Schedule" : "Publish"}</Button>
        </>
      }
    >
      <div className="app-stack">
        <FormError error={submit.error} listFields />
        <Select label="Category" value={f.category} onChange={(e) => set("category", e.target.value)} options={CATEGORIES.map((c) => ({ value: c, label: humanise(c) }))} />
        <Textarea label="What do you want to say?" rows={6} value={f.text} onChange={(e) => set("text", e.target.value)} />
        <fieldset className="app-stack" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="wo-label">Options</legend>
          <Checkbox label="Post as the WO Community team" checked={f.official} onChange={(e) => set("official", e.target.checked)} />
          <Checkbox label="Pin to the top of the feed" checked={f.pin} onChange={(e) => set("pin", e.target.checked)} />
          {f.pin ? <Input label="Unpin on (optional)" type="datetime-local" value={f.pinnedUntil} onChange={(e) => set("pinnedUntil", e.target.value)} /> : null}
          <Checkbox label="Allow comments" checked={f.comments} onChange={(e) => set("comments", e.target.checked)} />
          <Select label="Who can see it" value={f.audience} onChange={(e) => set("audience", e.target.value)} options={[{ value: "", label: "All members" }, { value: "mentor", label: "Mentors only" }, { value: "member", label: "Members only" }]} />
          {!post || scheduled ? <Input label="Publish later (optional)" type="datetime-local" hint="Leave empty to publish now." value={f.when} onChange={(e) => set("when", e.target.value)} /> : null}
        </fieldset>
        {post && post.excerpt ? <p className="body-sm app-muted" style={{ margin: 0 }}>Leave the text as it is to keep the original formatting.</p> : null}
      </div>
    </Modal>
  );
}
