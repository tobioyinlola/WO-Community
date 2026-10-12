import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Alert, Badge, Button, Card, Input, Select } from "../../components";
import { formatDate } from "../../lib/format";
import { EmptyState, Loaded, SkeletonRows } from "../../ui/blocks";
import { FormError, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";
import { useWorkspace } from "./Workspace";

const SUBJECTS = [
  { value: "score_summary", label: "Score summary" },
  { value: "plan_summary", label: "Business plan summary" },
  { value: "deck", label: "Pitch deck" },
  { value: "prototype", label: "Prototype" },
];

type Subject = "score_summary" | "plan_summary" | "deck" | "prototype";

export default function SharingTab() {
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const toast = useToast();
  const shares = useQuery({ queryKey: ["toolkit", ventureId, "shares"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/shares", { params: { path: { venture_id: ventureId } } })) });
  const grants = useQuery({ queryKey: ["toolkit", ventureId, "grants"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/grants", { params: { path: { venture_id: ventureId } } })) });
  const decks = useQuery({ queryKey: ["toolkit", ventureId, "decks"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/decks", { params: { path: { venture_id: ventureId } } })) });
  const prototypes = useQuery({ queryKey: ["toolkit", ventureId, "prototypes"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/prototypes", { params: { path: { venture_id: ventureId } } })) });
  const mentors = useQuery({ queryKey: ["mentors", "grantable"], queryFn: () => unwrap(api.GET("/api/v1/mentors", { params: { query: { limit: 50 } } })) });

  const [subject, setSubject] = useState<Subject>("score_summary");
  const [subjectId, setSubjectId] = useState("");
  const [password, setPassword] = useState("");
  const [days, setDays] = useState("30");
  const [created, setCreated] = useState<{ url: string; token: string } | null>(null);
  const [mentorId, setMentorId] = useState("");
  const [canComment, setCanComment] = useState(false);

  const subjectOptions =
    subject === "deck" ? (decks.data ?? []).map((d) => ({ value: d.id, label: d.title || "Pitch deck" }))
    : subject === "prototype" ? (prototypes.data ?? []).map((p) => ({ value: p.id, label: p.title || "Prototype" }))
    : [{ value: ventureId, label: "This venture" }];
  const resolvedId = subject === "deck" || subject === "prototype" ? subjectId : ventureId;

  const create = useSubmit(async () => {
    const made = await unwrap(
      api.POST("/api/v1/toolkit/ventures/{venture_id}/shares", {
        params: { path: { venture_id: ventureId } },
        body: { subject_type: subject, subject_id: resolvedId, expires_in_days: Number(days) || 30, ...(password ? { password } : {}) },
      }),
    );
    setCreated({ url: made.url, token: made.token });
    setPassword("");
    await client.invalidateQueries({ queryKey: ["toolkit", ventureId, "shares"] });
  });
  const revoke = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/toolkit/ventures/{venture_id}/shares/{share_id}", { params: { path: { venture_id: ventureId, share_id: id } } })),
    onSuccess: async () => { toast.show("Link turned off"); await client.invalidateQueries({ queryKey: ["toolkit", ventureId, "shares"] }); },
  });
  const grant = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/grants", { params: { path: { venture_id: ventureId } }, body: { mentor_id: mentorId, can_comment: canComment, expires_in_days: 90 } }));
    setMentorId("");
    toast.show("Access given");
    await client.invalidateQueries({ queryKey: ["toolkit", ventureId, "grants"] });
  });
  const unshare = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/toolkit/ventures/{venture_id}/grants/{grant_id}", { params: { path: { venture_id: ventureId, grant_id: id } } })),
    onSuccess: async () => { toast.show("Access removed"); await client.invalidateQueries({ queryKey: ["toolkit", ventureId, "grants"] }); },
  });

  const link = created ? `${window.location.origin}/share/${created.token}` : "";

  return (
    <div className="app-stack app-stack--lg">
      <Card>
        <h2 className="h3" style={{ margin: "0 0 var(--space-2)" }}>Share a link</h2>
        <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-4)" }}>Anyone with the link can read the one thing you pick, until it expires or you turn it off. Add a password for more privacy.</p>
        <div className="app-stack">
          <FormError error={create.error} />
          {created ? (
            <Alert tone="success" title="Your link is ready">
              <span className="body-sm">Copy it now. For your safety we cannot show it again.</span>
              <div className="app-cluster" style={{ marginTop: "var(--space-2)" }}>
                <code style={{ overflowWrap: "anywhere" }}>{link}</code>
                <Button size="sm" variant="secondary" icon={<Copy size={16} strokeWidth={1.5} aria-hidden="true" />} onClick={() => { void navigator.clipboard?.writeText(link); toast.show("Link copied"); }}>Copy</Button>
              </div>
            </Alert>
          ) : null}
          <div className="app-formgrid">
            <Select label="What to share" options={SUBJECTS} value={subject} onChange={(e) => { setSubject(e.target.value as Subject); setSubjectId(""); }} />
            {subject === "deck" || subject === "prototype" ? (
              <Select label={subject === "deck" ? "Which deck" : "Which prototype"} options={[{ value: "", label: "Choose one" }, ...subjectOptions]} value={subjectId} onChange={(e) => setSubjectId(e.target.value)} />
            ) : null}
            <Input label="Password (optional)" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <Input label="Expires after (days)" type="number" min={1} max={365} value={days} onChange={(e) => setDays(e.target.value)} />
          </div>
          <div><Button loading={create.busy} disabled={!resolvedId} onClick={() => void create.run()}>Create link</Button></div>
        </div>
      </Card>

      <section aria-label="Links you made">
        <h2 className="h3" style={{ margin: "0 0 var(--space-3)" }}>Links you made</h2>
        <Loaded query={shares} skeleton={<SkeletonRows />} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No links yet">When you share something, it shows up here so you can turn it off.</EmptyState>}>
          {(list) => (
            <ul className="app-list">
              {list.map((s) => (
                <li key={s.id}>
                  <div className="app-list__item">
                    <div className="app-list__main">
                      <p className="app-list__title">{SUBJECTS.find((x) => x.value === s.subject_type)?.label ?? s.subject_type}</p>
                      <p className="app-list__meta">
                        Made {formatDate(s.created_at)} &middot; {s.view_count} view{s.view_count === 1 ? "" : "s"}
                        {s.expires_at ? ` · expires ${formatDate(s.expires_at)}` : ""}{s.has_password ? " · password" : ""}
                      </p>
                    </div>
                    {s.revoked_at ? <Badge variant="neutral">Turned off</Badge> : <Button size="sm" variant="ghost" onClick={() => revoke.mutate(s.id)}>Turn off</Button>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Loaded>
      </section>

      <Card>
        <h2 className="h3" style={{ margin: "0 0 var(--space-2)" }}>Let a mentor in</h2>
        <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-4)" }}>A mentor you pick can see this venture in their own account. You can take it back at any time.</p>
        <div className="app-stack">
          <FormError error={grant.error} />
          <div className="app-formgrid">
            <Select label="Mentor" options={[{ value: "", label: "Choose a mentor" }, ...(mentors.data?.results ?? []).map((m) => ({ value: m.id, label: m.name }))]} value={mentorId} onChange={(e) => setMentorId(e.target.value)} />
            <label className="wo-check" style={{ alignSelf: "end", minHeight: 52 }}><input type="checkbox" checked={canComment} onChange={(e) => setCanComment(e.target.checked)} />They can comment</label>
          </div>
          <div><Button variant="secondary" loading={grant.busy} disabled={!mentorId} onClick={() => void grant.run()}>Give access</Button></div>
          {grants.data && grants.data.length > 0 ? (
            <ul className="app-list">
              {grants.data.map((g) => (
                <li key={g.id}>
                  <div className="app-list__item">
                    <div className="app-list__main">
                      <p className="app-list__title">{g.name}</p>
                      <p className="app-list__meta">{g.can_comment ? "Can comment" : "Read only"}{g.expires_at ? ` · until ${formatDate(g.expires_at)}` : ""}</p>
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => unshare.mutate(g.id)}>Remove</Button>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
