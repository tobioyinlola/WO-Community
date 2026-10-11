import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Smartphone } from "lucide-react";
import { useEffect, useState } from "react";
import { api, unwrap } from "../../api/client";
import { ApiError } from "../../api/errors";
import { Alert, Badge, Button, Card, CardText, CardTitle, Input, Select, Textarea } from "../../components";
import { formatDate } from "../../lib/format";
import { EmptyState, Loaded, SkeletonCards, SkeletonRows } from "../../ui/blocks";
import { FormError, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";
import { JobStatus, cancelJob, useJob } from "./jobs";
import { Node, type ProtoNode, type ProtoSpec } from "./preview";
import { useWorkspace } from "./Workspace";

type Op = { op: "replace" | "remove" | "add" | "move"; path: string; value?: unknown };
interface TextSlot { path: string; label: string; value: string }

/** Every short piece of wording on a screen, so a member can change it without touching the structure. */
function textSlots(node: ProtoNode, path: string, out: TextSlot[] = []): TextSlot[] {
  for (const key of ["text", "title", "label", "value"]) {
    const value = node.props[key];
    if (typeof value === "string" && value) out.push({ path: `${path}/props/${key}`, label: `${node.component.replace("_", " ")} ${key}`, value });
  }
  node.children.forEach((c, i) => textSlots(c, `${path}/children/${i}`, out));
  return out;
}

function Editor({ id, onBack }: { id: string; onBack: () => void }) {
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const toast = useToast();
  const base = { venture_id: ventureId, prototype_id: id };
  const proto = useQuery({ queryKey: ["toolkit", ventureId, "prototype", id], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/prototypes/{prototype_id}", { params: { path: base } })) });
  const versions = useQuery({ queryKey: ["toolkit", ventureId, "prototype", id, "versions", proto.data?.version], enabled: Boolean(proto.data), queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/prototypes/{prototype_id}/versions", { params: { path: base } })) });
  const spec = proto.data?.spec as unknown as ProtoSpec | undefined;
  const [screenId, setScreenId] = useState("");
  const [trail, setTrail] = useState<string[]>([]);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [title, setTitle] = useState("");

  useEffect(() => {
    if (!spec) return;
    setScreenId((current) => (spec.screens.some((s) => s.id === current) ? current : spec.start));
    setEdits({});
    setTitle(proto.data?.title ?? "");
  }, [spec, proto.data?.title]);

  const index = spec ? Math.max(0, spec.screens.findIndex((s) => s.id === screenId)) : 0;
  const screen = spec?.screens[index];
  const slots = screen ? textSlots(screen.root, `/screens/${index}/root`) : [];
  const refresh = () => client.invalidateQueries({ queryKey: ["toolkit", ventureId] });
  const apply = useSubmit(async (ops: Op[], label: string) => {
    await unwrap(api.PATCH("/api/v1/toolkit/ventures/{venture_id}/prototypes/{prototype_id}", { params: { path: base }, body: { ops, base_version: proto.data?.version ?? 1, label } }));
    await refresh();
  });
  const rename = useSubmit(async () => {
    await unwrap(api.PUT("/api/v1/toolkit/ventures/{venture_id}/prototypes/{prototype_id}", { params: { path: base }, body: { title: title.trim() } }));
    toast.show("Renamed");
    await refresh();
  });
  const restore = useMutation({
    mutationFn: (v: number) => unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/prototypes/{prototype_id}/versions/{version}/restore", { params: { path: { ...base, version: v } } })),
    onSuccess: async () => { toast.show("Earlier version restored"); await refresh(); },
  });
  const go = (target: string) => { setTrail((t) => [...t, screenId]); setScreenId(target); };
  const back = () => { const previous = trail[trail.length - 1]; if (previous) { setTrail(trail.slice(0, -1)); setScreenId(previous); } };
  const stale = apply.error instanceof ApiError && apply.error.status === 409;
  const dirty = Object.keys(edits).length > 0;

  return (
    <Loaded query={proto} skeleton={<SkeletonRows />}>
      {(p) => (
        <div className="app-stack app-stack--lg">
          <div className="app-cluster" style={{ justifyContent: "space-between" }}>
            <div className="app-cluster"><Button variant="ghost" size="sm" onClick={onBack}>All prototypes</Button><h2 className="h3" style={{ margin: 0 }}>{p.title}</h2><Badge variant="neutral">Version {p.version}</Badge></div>
          </div>
          {spec && screen ? (
            <div className="app-split">
              <div className="app-stack">
                <div className="app-cluster" role="group" aria-label="Screens">
                  {spec.screens.map((s) => (
                    <button key={s.id} type="button" className="app-react" aria-pressed={s.id === screenId} onClick={() => { setTrail([]); setScreenId(s.id); }}>{s.name}</button>
                  ))}
                </div>
                <div className={spec.kind === "mobile" ? "app-proto app-proto--mobile" : "app-proto"} aria-label={`Preview of ${screen.name}`}>
                  <Node node={screen.root} go={go} back={back} />
                </div>
                <p className="caption app-muted" style={{ margin: 0 }}>This is a clickable preview. Buttons that lead to another screen work here.</p>
              </div>
              <aside className="app-stack">
                <Card>
                  <h3 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Words on this screen</h3>
                  {stale ? <Alert tone="warning" title="This changed somewhere else" action={<Button size="sm" variant="secondary" onClick={() => void proto.refetch()}>Reload</Button>}>Reload to see the latest.</Alert> : <FormError error={apply.error} />}
                  <div className="app-stack">
                    {slots.length === 0 ? <p className="body-sm app-muted">There is no editable wording here.</p> : slots.slice(0, 14).map((s) => (
                      <Input key={s.path} label={s.label} value={edits[s.path] ?? s.value} onChange={(e) => setEdits({ ...edits, [s.path]: e.target.value })} />
                    ))}
                    <div><Button loading={apply.busy} disabled={!dirty} onClick={() => void apply.run(Object.entries(edits).map(([path, value]) => ({ op: "replace" as const, path, value })), `Edited ${screen.name}`)}>Save changes</Button></div>
                  </div>
                </Card>
                <Card>
                  <h3 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Name</h3>
                  <div className="app-stack">
                    <FormError error={rename.error} />
                    <Input label="Prototype name" value={title} onChange={(e) => setTitle(e.target.value)} />
                    <div><Button variant="secondary" size="sm" loading={rename.busy} disabled={!title.trim() || title === p.title} onClick={() => void rename.run()}>Rename</Button></div>
                  </div>
                </Card>
                {versions.data && versions.data.length > 0 ? (
                  <Card>
                    <h3 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Earlier versions</h3>
                    <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0, gap: "var(--space-2)" }}>
                      {versions.data.slice(0, 6).map((v) => (
                        <li key={v.version} className="app-cluster" style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
                          <span className="body-sm">{v.label || `Version ${v.version}`} <span className="app-faint">{formatDate(v.created_at)}</span></span>
                          <Button size="sm" variant="ghost" onClick={() => restore.mutate(v.version)}>Restore</Button>
                        </li>
                      ))}
                    </ul>
                  </Card>
                ) : null}
              </aside>
            </div>
          ) : null}
        </div>
      )}
    </Loaded>
  );
}

export default function PrototypesTab() {
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState<string | null>(null);
  const [template, setTemplate] = useState("");
  const [brief, setBrief] = useState("");
  const [kind, setKind] = useState<"web" | "mobile">("mobile");
  const [jobId, setJobId] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["toolkit", ventureId, "prototypes"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/prototypes", { params: { path: { venture_id: ventureId } } })) });
  const templates = useQuery({ queryKey: ["toolkit", "prototype-templates"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/prototype-templates")), staleTime: 3_600_000 });
  const chosen = template || templates.data?.[0]?.slug || "";
  const running = useJob(jobId, (job) => {
    setJobId(null);
    void client.invalidateQueries({ queryKey: ["toolkit", ventureId] });
    if (job.status === "succeeded" && typeof job.result?.id === "string") setOpen(job.result.id);
  });
  const create = useSubmit(async () => {
    const made = await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/prototypes", { params: { path: { venture_id: ventureId } }, body: { template: chosen } }));
    await client.invalidateQueries({ queryKey: ["toolkit", ventureId] });
    setOpen(made.id);
  });
  const draft = useSubmit(async () => {
    const job = await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/prototypes/generate", { params: { path: { venture_id: ventureId } }, body: { kind, ...(brief.trim() ? { brief: brief.trim() } : {}) } }));
    setJobId(job.id);
  });
  const copy = useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/prototypes/{prototype_id}/duplicate", { params: { path: { venture_id: ventureId, prototype_id: id } } })),
    onSuccess: async () => { toast.show("Copied"); await client.invalidateQueries({ queryKey: ["toolkit", ventureId] }); },
  });
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/toolkit/ventures/{venture_id}/prototypes/{prototype_id}", { params: { path: { venture_id: ventureId, prototype_id: id } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["toolkit", ventureId] }),
  });
  if (open) return <Editor id={open} onBack={() => setOpen(null)} />;
  const drafting = draft.busy || Boolean(jobId && running.running);
  return (
    <div className="app-stack app-stack--lg">
      <div className="app-split">
        <Card>
          <h2 className="h3" style={{ margin: "0 0 var(--space-2)" }}>Start from a template</h2>
          <div className="app-stack">
            <FormError error={create.error} />
            <Select label="Template" options={(templates.data ?? []).map((t) => ({ value: t.slug, label: `${t.name} (${t.kind}, ${t.screen_count} screens)` }))} value={chosen} onChange={(e) => setTemplate(e.target.value)} hint={templates.data?.find((t) => t.slug === chosen)?.description} />
            <div><Button loading={create.busy} disabled={!chosen} onClick={() => void create.run()}>Create prototype</Button></div>
          </div>
        </Card>
        <Card>
          <h2 className="h3" style={{ margin: "0 0 var(--space-2)" }}>Draft one from your idea</h2>
          <div className="app-stack">
            <FormError error={draft.error} />
            <Select label="For" options={[{ value: "mobile", label: "A phone app" }, { value: "web", label: "A website" }]} value={kind} onChange={(e) => setKind(e.target.value as "web" | "mobile")} />
            <Textarea label="Anything to stress? (optional)" rows={2} value={brief} onChange={(e) => setBrief(e.target.value)} />
            <div><Button loading={drafting} onClick={() => void draft.run()}>Draft a prototype</Button></div>
            {jobId ? <JobStatus job={running.job} error={running.error} onCancel={() => void cancelJob(jobId)} /> : null}
          </div>
        </Card>
      </div>
      <Loaded query={list} skeleton={<SkeletonCards count={2} />} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No prototypes yet" icon={<Smartphone size={22} strokeWidth={1.5} />}>Make a clickable mock-up to test the idea with real people.</EmptyState>}>
        {(items) => (
          <div className="app-grid">
            {items.map((p) => (
              <Card key={p.id}>
                <div className="app-cluster" style={{ marginBottom: "var(--space-2)" }}><Badge variant="neutral">{p.kind === "mobile" ? "Phone app" : "Website"}</Badge></div>
                <CardTitle>{p.title}</CardTitle>
                <CardText>{p.screen_count} screens &middot; updated {formatDate(p.updated_at)}</CardText>
                <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                  <Button size="sm" variant="secondary" onClick={() => setOpen(p.id)}>Open</Button>
                  <Button size="sm" variant="ghost" onClick={() => copy.mutate(p.id)}>Copy</Button>
                  <Button size="sm" variant="ghost" onClick={() => remove.mutate(p.id)} aria-label={`Delete ${p.title}`}>Delete</Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </Loaded>
    </div>
  );
}
