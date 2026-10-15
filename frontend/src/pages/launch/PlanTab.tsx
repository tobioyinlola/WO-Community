import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { ApiError, messageOf } from "../../api/errors";
import { Alert, Badge, Button, Card, Input, Select, Textarea } from "../../components";
import { formatDate } from "../../lib/format";
import { EmptyState, Loaded, SkeletonRows, TableScroll } from "../../ui/blocks";
import { FormError, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";
import { useAiEnabled } from "./config";
import { JobStatus, cancelJob, useExport, useJob } from "./jobs";
import { packageKey, useWorkspace } from "./Workspace";

type Block =
  | { type: "paragraph"; text: string; cites?: number[] }
  | { type: "heading"; text: string }
  | { type: "bullets"; items: string[]; cites?: number[] }
  | { type: "table"; columns: string[]; rows: string[][]; cites?: number[] };
interface Content { blocks: Block[] }

const ASSISTS = [
  { value: "shorten", label: "Make it shorter" },
  { value: "expand", label: "Say more" },
  { value: "simplify", label: "Use simpler words" },
  { value: "rewrite_for_investors", label: "Rewrite for investors" },
  { value: "add_data", label: "Add supporting data" },
  { value: "localise", label: "Fit a country" },
] as const;
type Assist = (typeof ASSISTS)[number]["value"];

const blocksOf = (content: unknown): Block[] => {
  const raw = (content as Content | undefined)?.blocks;
  return Array.isArray(raw) ? raw : [];
};

/** A block the member can read, as it will look in the document. */
function BlockView({ block }: { block: Block }) {
  if (block.type === "heading") return <h4 className="h4" style={{ margin: 0 }}>{block.text}</h4>;
  if (block.type === "paragraph") return <p className="body" style={{ margin: 0 }}>{block.text}</p>;
  if (block.type === "bullets") return <ul style={{ margin: 0 }}>{block.items.map((t, i) => <li key={i}>{t}</li>)}</ul>;
  return (
    <TableScroll label="Table">
      <table className="app-table">
        <thead><tr>{block.columns.map((c, i) => <th key={i} scope="col">{c}</th>)}</tr></thead>
        <tbody>{block.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
      </table>
    </TableScroll>
  );
}

function Editor({ number, onClose }: { number: number; onClose: () => void }) {
  const ai = useAiEnabled();
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const toast = useToast();
  const query = useQuery({
    queryKey: ["toolkit", ventureId, "plan", "section", number],
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/plan/sections/{number}", { params: { path: { venture_id: ventureId, number } } })),
  });
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [version, setVersion] = useState(0);
  const [assist, setAssist] = useState<Assist>("simplify");
  const [country, setCountry] = useState("");
  const [proposal, setProposal] = useState<Awaited<ReturnType<typeof ask>> | null>(null);

  useEffect(() => {
    if (!query.data) return;
    setBlocks(blocksOf(query.data.content));
    setVersion(query.data.version);
    setProposal(null);
  }, [query.data]);

  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["toolkit", ventureId, "plan"] });
    await client.invalidateQueries({ queryKey: packageKey(ventureId) });
  };
  const save = useSubmit(async () => {
    await unwrap(api.PATCH("/api/v1/toolkit/ventures/{venture_id}/plan/sections/{number}", { params: { path: { venture_id: ventureId, number } }, body: { content: { blocks }, base_version: version } }));
    toast.show("Section saved");
    await refresh();
  });
  const ask = async () => unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/plan/sections/{number}/assist", { params: { path: { venture_id: ventureId, number } }, body: { action: assist, ...(assist === "localise" && country ? { country } : {}) } }));
  const propose = useSubmit(async () => setProposal(await ask()));
  const accept = useSubmit(async () => {
    if (!proposal) return;
    await unwrap(api.PATCH("/api/v1/toolkit/ventures/{venture_id}/plan/sections/{number}", { params: { path: { venture_id: ventureId, number } }, body: { content: proposal.content, citations: proposal.citations as unknown as Record<string, unknown>[], base_version: version } }));
    toast.show("Suggestion used");
    await refresh();
  });
  const changed = JSON.stringify(blocks) !== JSON.stringify(blocksOf(query.data?.content));
  const stale = save.error instanceof ApiError && save.error.status === 409;
  const update = (i: number, next: Block) => setBlocks((b) => b.map((x, j) => (j === i ? next : x)));

  return (
    <Card>
      <Loaded query={query} skeleton={<SkeletonRows />}>
        {(section) => (
          <div className="app-stack">
            <div className="app-cluster" style={{ justifyContent: "space-between" }}>
              <div>
                <p className="eyebrow" style={{ margin: 0 }}>{section.chapter}</p>
                <h2 className="h3" style={{ margin: 0 }}>{section.number}. {section.title}</h2>
              </div>
              <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
            </div>
            {section.guidance ? <p className="body-sm app-muted" style={{ margin: 0 }}>{section.guidance}</p> : null}
            {section.stale ? <Alert tone="warning" title="This was written before you changed your answers">Refresh the plan or review it by hand.</Alert> : null}
            {stale ? <Alert tone="warning" title="This changed somewhere else" action={<Button size="sm" variant="secondary" onClick={() => void query.refetch()}>Reload</Button>}>Reload to see the latest.</Alert> : <FormError error={save.error} />}
            {section.status === "needs_input" ? (
              ai ? (
                <Alert tone="info" title="We need more from you here">Add what you know below, or complete the profile so this can be written.</Alert>
              ) : (
                <Alert tone="info" title="Yours to write">Add paragraphs or a list below, covering what the note above describes, then save.</Alert>
              )
            ) : null}
            {blocks.map((b, i) => (
              <div key={i} className="app-stack" style={{ gap: "var(--space-2)" }}>
                {b.type === "heading" ? (
                  <Input label="Heading" value={b.text} onChange={(e) => update(i, { ...b, text: e.target.value })} />
                ) : b.type === "paragraph" ? (
                  <Textarea label="Paragraph" rows={4} value={b.text} onChange={(e) => update(i, { ...b, text: e.target.value })} />
                ) : b.type === "bullets" ? (
                  <Textarea label="List, one item per line" rows={Math.max(3, b.items.length + 1)} value={b.items.join("\n")} onChange={(e) => update(i, { ...b, items: e.target.value.split("\n").filter((x) => x.trim()) })} />
                ) : (
                  <BlockView block={b} />
                )}
                {"cites" in b && b.cites && b.cites.length > 0 ? <p className="caption app-faint" style={{ margin: 0 }}>Sources {b.cites.map((n) => `[${n}]`).join(" ")}</p> : null}
                <div><button type="button" className="app-linklike" onClick={() => setBlocks(blocks.filter((_, j) => j !== i))}>Remove this {b.type === "bullets" ? "list" : b.type}</button></div>
              </div>
            ))}
            <div className="app-cluster">
              <Button variant="secondary" size="sm" onClick={() => setBlocks([...blocks, { type: "paragraph", text: "" }])}>Add a paragraph</Button>
              <Button variant="secondary" size="sm" onClick={() => setBlocks([...blocks, { type: "bullets", items: [] }])}>Add a list</Button>
            </div>
            {section.citations.length > 0 ? (
              <details>
                <summary>Sources ({section.citations.length})</summary>
                <ol>{section.citations.map((c) => <li key={c.number} value={c.number} className="body-sm">{c.source_name}{c.date ? `, ${c.date}` : ""}{c.claim_text ? ` — ${c.claim_text}` : ""}</li>)}</ol>
              </details>
            ) : null}
            <div><Button loading={save.busy} disabled={!changed} onClick={() => void save.run()}>Save this section</Button></div>

            {ai ? (<>
            <hr className="app-rule" />
            <h3 className="h4" style={{ margin: 0 }}>Ask for help with this section</h3>
            <p className="body-sm app-muted" style={{ margin: 0 }}>We show a suggestion first. Nothing changes until you use it, and any figure we cannot back up is taken out.</p>
            <FormError error={propose.error ?? accept.error} />
            <div className="app-formgrid">
              <Select label="What would help?" options={ASSISTS.map((a) => ({ value: a.value, label: a.label }))} value={assist} onChange={(e) => setAssist(e.target.value as Assist)} />
              {assist === "localise" ? <Input label="Country code" placeholder="NG" maxLength={2} value={country} onChange={(e) => setCountry(e.target.value.toUpperCase())} /> : null}
            </div>
            <div><Button variant="secondary" size="sm" loading={propose.busy} onClick={() => void propose.run()}>Suggest</Button></div>
            </>) : null}
            {proposal ? (
              <Card variant="white">
                <p className="eyebrow" style={{ margin: "0 0 var(--space-3)" }}>Suggestion</p>
                <div className="app-stack">{blocksOf(proposal.content).map((b, i) => <BlockView key={i} block={b} />)}</div>
                {proposal.removed_figures.length > 0 ? <p className="caption app-muted" style={{ margin: "var(--space-3) 0 0" }}>Left out because we could not back them up: {proposal.removed_figures.join(", ")}.</p> : null}
                <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                  <Button size="sm" loading={accept.busy} onClick={() => void accept.run()}>Use this</Button>
                  <Button size="sm" variant="ghost" onClick={() => setProposal(null)}>Discard</Button>
                </div>
              </Card>
            ) : null}
          </div>
        )}
      </Loaded>
    </Card>
  );
}

export default function PlanTab() {
  const ai = useAiEnabled();
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState<number | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const plan = useQuery({
    queryKey: ["toolkit", ventureId, "plan"],
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/plan", { params: { path: { venture_id: ventureId } } }));
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
  const readiness = useQuery({
    queryKey: ["toolkit", ventureId, "plan", "readiness"],
    enabled: Boolean(plan.data),
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/plan/readiness", { params: { path: { venture_id: ventureId } } })),
  });
  const versions = useQuery({
    queryKey: ["toolkit", ventureId, "plan", "versions"],
    enabled: Boolean(plan.data),
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/plan/versions", { params: { path: { venture_id: ventureId } } })),
  });
  const running = useJob(jobId, () => {
    setJobId(null);
    void client.invalidateQueries({ queryKey: ["toolkit", ventureId] });
  });
  const generate = useSubmit(async (overwrite: boolean) => {
    const job = await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/plan/generate", { params: { path: { venture_id: ventureId } }, body: { overwrite_edited: overwrite } }));
    setJobId(job.id);
  });
  const exporter = useExport((format) =>
    unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/plan/export", { params: { path: { venture_id: ventureId } }, body: { format: format as "docx" | "pdf" } })),
  );
  const restore = useMutation({
    mutationFn: (version: number) => unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/plan/versions/{version}/restore", { params: { path: { venture_id: ventureId, version } } })),
    onSuccess: async () => { toast.show("Earlier version restored"); await client.invalidateQueries({ queryKey: ["toolkit", ventureId] }); },
  });
  const generating = generate.busy || Boolean(jobId && running.running);
  const needsProfile = generate.error instanceof ApiError && Boolean(generate.error.fieldErrors.profile);

  const chapters = new Map<string, NonNullable<typeof plan.data>["sections"]>();
  for (const s of plan.data?.sections ?? []) chapters.set(s.chapter, [...(chapters.get(s.chapter) ?? []), s]);

  return (
    <div className="app-stack app-stack--lg">
      <div className="app-cluster" style={{ justifyContent: "space-between" }}>
        <p className="body app-muted" style={{ margin: 0, maxWidth: "60ch" }}>
          {ai
            ? "A full plan written from your profile, forecast and cited sources. Every section is yours to edit."
            : "A full business plan laid out section by section, each with what it should cover, for you to write. Your profile and forecast are kept alongside."}
        </p>
        <div className="app-cluster">
          {plan.data ? (
            <>
              <Button variant="secondary" loading={exporter.busy} onClick={() => void exporter.run("docx")}>Download Word</Button>
              <Button variant="secondary" loading={exporter.busy} onClick={() => void exporter.run("pdf")}>Download PDF</Button>
            </>
          ) : null}
          <Button loading={generating} onClick={() => void generate.run(false)}>{plan.data ? (ai ? "Update the plan" : "Add any missing sections") : ai ? "Write my plan" : "Lay out my plan"}</Button>
        </div>
      </div>
      {needsProfile ? (
        <Alert tone="info" title="Complete the profile first" action={<Link className="wo-btn wo-btn--secondary wo-btn--sm" to="../profile">Open the profile</Link>}>{messageOf(generate.error)}</Alert>
      ) : <FormError error={generate.error ?? exporter.error} />}
      {jobId ? <JobStatus job={running.job} error={running.error} onCancel={() => void cancelJob(jobId)} /> : running.failure ? <JobStatus job={running.failure} /> : null}
      {exporter.busy ? <JobStatus job={exporter.job} /> : null}
      <Loaded
        query={plan}
        skeleton={<SkeletonRows />}
        isEmpty={(d) => !d}
        empty={<EmptyState title="No plan yet" icon={<FileText size={22} strokeWidth={1.5} />}>It takes about a minute. Sections you edit by hand are kept when you update the plan.</EmptyState>}
      >
        {(data) => (
          <div className="app-split">
            <div className="app-stack">
              {readiness.data && !readiness.data.ready ? (
                <Alert tone="warning" title="Not ready to share yet">
                  {/* A plan laid out to be written has a blocker per section: show the first few. */}
                  <ul style={{ margin: 0 }}>{readiness.data.blockers.slice(0, 5).map((b) => <li key={b}>{b}</li>)}</ul>
                  {readiness.data.blockers.length > 5 ? (
                    <p style={{ margin: "var(--space-2) 0 0" }}>And {readiness.data.blockers.length - 5} more. Sections marked &ldquo;Needs you&rdquo; below are still to write.</p>
                  ) : null}
                </Alert>
              ) : null}
              {data && [...chapters.entries()].map(([chapter, sections]) => (
                <section key={chapter} aria-label={chapter}>
                  <h2 className="h4" style={{ margin: "0 0 var(--space-2)" }}>{chapter}</h2>
                  <ul className="app-list">
                    {sections.map((s) => (
                      <li key={s.number}>
                        <button type="button" className="app-list__item" onClick={() => setOpen(s.number)} aria-current={open === s.number ? "true" : undefined}>
                          <div className="app-list__main">
                            <p className="app-list__title">{s.number}. {s.title}</p>
                            <p className="app-list__meta">{s.word_count} words{s.edited_by_member ? " · edited by you" : ""}</p>
                          </div>
                          {s.status === "needs_input" ? <Badge variant="warning">Needs you</Badge> : s.stale || s.status === "needs_refresh" ? <Badge variant="warning">Out of date</Badge> : <Badge variant="success">Ready</Badge>}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
            <aside className="app-stack">
              {open !== null ? <Editor key={open} number={open} onClose={() => setOpen(null)} /> : <Card><p className="body app-muted" style={{ margin: 0 }}>Choose a section to read or edit it.</p></Card>}
              {versions.data && versions.data.length > 0 ? (
                <Card>
                  <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Earlier versions</h2>
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
        )}
      </Loaded>
    </div>
  );
}
