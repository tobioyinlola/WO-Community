import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, MessagesSquare, Pencil, Plus, RotateCcw, Smile, Trash2 } from "lucide-react";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import type { components } from "../api/schema";
import { Badge, Button, Card, Input, Modal, Textarea } from "../components";
import { timeAgo } from "../lib/format";
import { EmojiPicker } from "../pages/app/groups/EmojiPicker";
import { EmptyState, Loaded, PageHeader, SkeletonCards, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import "../styles/groups.css";

type Group = components["schemas"]["AdminChatGroup"];
type Message = components["schemas"]["GroupMessage"];
const KEY = ["admin", "groups"];

/** The community's group chats: open new ones, rename or archive them, and take down messages. */
export default function AdminGroups() {
  useDocumentTitle("Groups");
  const client = useQueryClient();
  const toast = useToast();
  const groups = useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/api/v1/admin/groups")) });
  const [editing, setEditing] = useState<Group | "new" | null>(null);
  const [reading, setReading] = useState<Group | null>(null);

  const archive = async (g: Group, archived: boolean) => {
    try {
      await unwrap(api.PATCH("/api/v1/admin/groups/{group_id}", { params: { path: { group_id: g.id } }, body: { archived } }));
      await client.invalidateQueries({ queryKey: KEY });
      toast.show(archived ? `${g.name} archived` : `${g.name} is open again`);
    } catch (e) {
      toast.show(messageOf(e));
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Community"
        title="Groups"
        lead="Chat channels members can join. Archiving a group hides it from members and keeps its messages."
        actions={<Button icon={<Plus size={16} strokeWidth={1.75} aria-hidden="true" />} onClick={() => setEditing("new")}>New group</Button>}
      />
      <Loaded
        query={groups}
        skeleton={<SkeletonCards count={3} />}
        isEmpty={(d) => d.length === 0}
        empty={<EmptyState title="No groups yet" icon={<MessagesSquare size={24} strokeWidth={1.5} />}>Create the first group for members to join.</EmptyState>}
      >
        {(list) => (
          <div className="app-stack">
            {list.map((g) => (
              <Card key={g.id}>
                <div className="adm-group">
                  <span className="wo-group__emoji" aria-hidden="true">{g.emoji || "💬"}</span>
                  <div className="adm-group__body">
                    <p className="adm-group__name">
                      {g.name} {g.archived ? <Badge variant="neutral">Archived</Badge> : null}
                    </p>
                    {g.description ? <p className="body-sm app-muted" style={{ margin: 0 }}>{g.description}</p> : null}
                    <p className="caption app-muted" style={{ margin: "var(--space-1) 0 0" }}>
                      {g.member_count} {g.member_count === 1 ? "member" : "members"} · {g.message_count} {g.message_count === 1 ? "message" : "messages"}
                      {g.last_activity_at ? ` · last active ${timeAgo(g.last_activity_at)}` : ""}
                    </p>
                  </div>
                  <div className="adm-group__actions">
                    <Button variant="ghost" size="sm" icon={<MessagesSquare size={16} strokeWidth={1.75} aria-hidden="true" />} onClick={() => setReading(g)}>Messages</Button>
                    <Button variant="ghost" size="sm" icon={<Pencil size={16} strokeWidth={1.75} aria-hidden="true" />} onClick={() => setEditing(g)}>Edit</Button>
                    {g.archived ? (
                      <Button variant="ghost" size="sm" icon={<RotateCcw size={16} strokeWidth={1.75} aria-hidden="true" />} onClick={() => void archive(g, false)}>Restore</Button>
                    ) : (
                      <Button variant="ghost" size="sm" icon={<Archive size={16} strokeWidth={1.75} aria-hidden="true" />} onClick={() => void archive(g, true)}>Archive</Button>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </Loaded>
      {editing ? <GroupForm group={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
      {reading ? <GroupMessages group={reading} onClose={() => setReading(null)} /> : null}
    </>
  );
}

function GroupForm({ group, onClose }: { group: Group | null; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(group?.name ?? "");
  const [emoji, setEmoji] = useState(group?.emoji ?? "");
  const [description, setDescription] = useState(group?.description ?? "");
  const [picker, setPicker] = useState(false);
  const save = useSubmit(async () => {
    const body = { name: name.trim(), emoji: emoji.trim(), description: description.trim() };
    if (group) {
      await unwrap(api.PATCH("/api/v1/admin/groups/{group_id}", { params: { path: { group_id: group.id } }, body }));
    } else {
      await unwrap(api.POST("/api/v1/admin/groups", { body }));
    }
    await client.invalidateQueries({ queryKey: KEY });
    await client.invalidateQueries({ queryKey: ["groups", "list"] });
    toast.show(group ? "Group saved" : `${body.name} is open for members to join`);
    onClose();
  });
  const errors = errorsFrom(save.error).fields;
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Groups"
      title={group ? `Edit ${group.name}` : "New group"}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button loading={save.busy} disabled={!name.trim()} onClick={() => void save.run()}>{group ? "Save" : "Create group"}</Button>
        </>
      }
    >
      <div className="app-stack">
        <FormError error={save.error} />
        <Input label="Name" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} error={errors.name} placeholder="WO Founders in Tech" />
        <div className="adm-group__emojifield">
          <Input label="Emoji" maxLength={16} value={emoji} onChange={(e) => setEmoji(e.target.value)} error={errors.emoji} hint="Shown beside the group's name." />
          <span className="wo-chat__emojiwrap">
            <button type="button" className="wo-chat__icon" aria-label="Choose an emoji" aria-expanded={picker} onClick={() => setPicker((v) => !v)}>
              <Smile size={22} strokeWidth={1.75} aria-hidden="true" />
            </button>
            {picker ? <EmojiPicker align="end" onPick={setEmoji} onClose={() => setPicker(false)} /> : null}
          </span>
        </div>
        <Textarea label="Description" rows={3} maxLength={300} value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} placeholder="Who the group is for and what it talks about." />
      </div>
    </Modal>
  );
}

function GroupMessages({ group, onClose }: { group: Group; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const key = ["admin", "groups", group.id, "messages"];
  const page = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/v1/admin/groups/{group_id}/messages", { params: { path: { group_id: group.id }, query: { limit: 100 } } })),
  });
  const [removing, setRemoving] = useState<Message | null>(null);
  const remove = async (m: Message) => {
    try {
      await unwrap(api.DELETE("/api/v1/admin/group-messages/{message_id}", { params: { path: { message_id: m.id } } }));
      await client.invalidateQueries({ queryKey: key });
      await client.invalidateQueries({ queryKey: KEY });
      toast.show("Message removed");
    } catch (e) {
      toast.show(messageOf(e));
    }
    setRemoving(null);
  };
  return (
    <Modal open onClose={onClose} eyebrow="Groups" title={`${group.emoji ? `${group.emoji} ` : ""}${group.name}`} actions={<Button variant="ghost" onClick={onClose}>Close</Button>}>
      <Loaded
        query={page}
        isEmpty={(d) => d.results.length === 0}
        empty={<p className="app-muted">No messages yet.</p>}
      >
        {(d) => (
          <ol className="adm-groupmsgs">
            {[...d.results].reverse().map((m) => (
              <li key={m.id} className={m.deleted ? "adm-groupmsgs__gone" : undefined}>
                <div>
                  <p className="caption app-muted" style={{ margin: 0 }}>
                    <strong>{m.author.name}</strong> · {timeAgo(m.created_at)}
                  </p>
                  <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                    {m.deleted ? <em>{m.removed ? "Removed by the team" : "Deleted by the author"}</em> : m.body}
                  </p>
                </div>
                {!m.deleted ? (
                  <Button variant="ghost" size="sm" icon={<Trash2 size={16} strokeWidth={1.75} aria-hidden="true" />} onClick={() => setRemoving(m)}>Remove</Button>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </Loaded>
      {removing ? (
        <Modal
          open
          onClose={() => setRemoving(null)}
          title="Remove this message?"
          actions={
            <>
              <Button variant="ghost" onClick={() => setRemoving(null)}>Keep it</Button>
              <Button variant="danger" onClick={() => void remove(removing)}>Remove</Button>
            </>
          }
        >
          Members will see that the community team removed a message. It stays in the audit record.
        </Modal>
      ) : null}
    </Modal>
  );
}
