import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareText } from "lucide-react";
import { useRef, useState } from "react";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import type { components } from "../api/schema";
import { Button, Input, Select, Switch } from "../components";
import { CATEGORIES } from "../support/constants";
import { Drawer } from "../ui/Drawer";
import { EmptyState, ErrorState, PageHeader, RichText, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { RichEditor, type RichEditorHandle } from "./kit/RichEditor";

type Reply = components["schemas"]["CannedReplyOut"];

const ANY = { value: "", label: "Any category" };

function ReplyForm({ reply, onClose }: { reply: Reply | null; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const editor = useRef<RichEditorHandle>(null);
  const [title, setTitle] = useState(reply?.title ?? "");
  const [category, setCategory] = useState<string>(reply?.category ?? "");
  const [active, setActive] = useState(reply?.active ?? true);
  const [body, setBody] = useState(reply?.body ?? "");
  const [open, setOpen] = useState(true);
  const dirty = title !== (reply?.title ?? "") || body !== (reply?.body ?? "");

  const save = useSubmit(async () => {
    const payload = { title, body, category: category as never, active };
    if (reply) await unwrap(api.PUT("/api/v1/admin/support/canned-replies/{reply_id}", { params: { path: { reply_id: reply.id } }, body: payload }));
    else await unwrap(api.POST("/api/v1/admin/support/canned-replies", { body: payload }));
    await client.invalidateQueries({ queryKey: ["admin", "support"] });
    toast.show(reply ? "Saved reply updated" : "Saved reply added");
    setOpen(false);
  });
  const { fields } = errorsFrom(save.error);

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) onClose();
      }}
      eyebrow="Support"
      title={reply ? "Edit saved reply" : "New saved reply"}
      subtitle="Admins can insert it into a reply, then change it before sending."
      dirty={dirty}
      footer={
        <>
          <Button variant="secondary" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button loading={save.busy} disabled={title.trim() === "" || body === ""} onClick={() => void save.run()}>
            Save reply
          </Button>
        </>
      }
    >
      <div className="wo-form">
        <Input label="Title" value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} hint="What admins see in the list, such as “Password reset steps”." error={fields.title} required />
        <Select label="Category" value={category} options={[ANY, ...CATEGORIES]} onChange={(e) => setCategory(e.target.value)} hint="Offered first for requests in this category." />
        <div className="wo-field">
          <span className="wo-label" id="reply-body-label">
            Reply
          </span>
          <RichEditor
            ref={editor}
            label="Reply text"
            placeholder="Write the reply"
            initialHtml={reply?.body}
            onChange={(value) => setBody(value)}
          />
          {fields.body ? <p className="wo-attach__problem">{fields.body}</p> : null}
        </div>
        <Switch label="Offer this reply to admins" checked={active} onChange={(e) => setActive(e.target.checked)} />
        <FormError error={save.error} listFields />
      </div>
    </Drawer>
  );
}

/** The saved replies admins can drop into an answer. */
export default function SupportReplies() {
  useDocumentTitle("Saved replies");
  const client = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<Reply | "new" | null>(null);
  const list = useQuery({
    queryKey: ["admin", "support", "canned", "all"],
    queryFn: () => unwrap(api.GET("/api/v1/admin/support/canned-replies", { params: { query: { all: "true" } as never } })),
  });
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/admin/support/canned-replies/{reply_id}", { params: { path: { reply_id: id } } })),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["admin", "support"] });
      toast.show("Saved reply deleted");
    },
    onError: (error) => toast.show(messageOf(error)),
  });
  const rows = list.data ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Support"
        title="Saved replies"
        lead="Answers you give often. Insert one into a reply, then change it before you send."
        actions={<Button onClick={() => setEditing("new")}>New saved reply</Button>}
      />
      {list.isPending ? <SkeletonRows /> : null}
      {list.isError ? <ErrorState error={list.error} onRetry={() => void list.refetch()} /> : null}
      {list.isSuccess && rows.length === 0 ? (
        <EmptyState title="No saved replies yet" icon={<MessageSquareText size={22} strokeWidth={1.5} />}>
          Add the answers you find yourself typing again and again.
        </EmptyState>
      ) : null}
      {rows.length > 0 ? (
        <ul className="wo-canned" aria-label="Saved replies">
          {rows.map((r) => (
            <li key={r.id} className="adm-card wo-canned__item" data-active={r.active}>
              <div className="wo-canned__head">
                <h2 className="adm-card__title">{r.title}</h2>
                <span className="wo-canned__meta">
                  {CATEGORIES.find((c) => c.value === r.category)?.label ?? "Any category"}
                  {r.active ? "" : " · Switched off"}
                </span>
              </div>
              <RichText html={r.body} />
              <div className="wo-canned__actions">
                <Button variant="secondary" size="sm" onClick={() => setEditing(r)}>
                  Edit
                </Button>
                <Button variant="ghost" size="sm" loading={remove.isPending && remove.variables === r.id} onClick={() => remove.mutate(r.id)}>
                  Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {editing ? <ReplyForm key={editing === "new" ? "new" : editing.id} reply={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
    </>
  );
}
