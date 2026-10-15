import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, downloadFile, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Alert, Badge, Button, Checkbox, Input, Modal, Select, StatTile, Textarea } from "../components";
import { formatDate, formatDateTime, formatNumber, humanise } from "../lib/format";
import { EmptyState, ErrorState, Loaded, LoadMore, PageHeader, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { StatusChip } from "./kit/TableBits";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Venture = components["schemas"]["TkAdminVenture"];
type DeckTemplate = components["schemas"]["TkAdminDeckTemplate"];
type PrototypeTemplate = components["schemas"]["TkAdminPrototypeTemplate"];
type PlanSection = components["schemas"]["TkAdminPlanSection"];
type Rubric = components["schemas"]["TkAdminRubric"];

const TOOL_LABELS: Record<string, string> = {
  score: "Validation score",
  plan: "Business plan",
  forecast: "Forecast",
  decks: "Pitch decks",
  prototypes: "Prototypes",
  partner: "Venture partner",
};

/** JSON typed by an admin: parsed, or the reason it could not be. */
function parseJson(text: string): { value?: unknown; problem?: string } {
  try {
    return { value: JSON.parse(text) };
  } catch (error) {
    return { problem: `This is not valid JSON: ${(error as Error).message}` };
  }
}

const pretty = (value: unknown) => JSON.stringify(value, null, 2);

// ---- Ventures --------------------------------------------------------------------------------

export function ToolkitVentures() {
  useDocumentTitle("Ventures");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [deleted, setDeleted] = useState(false);
  const list = useOffsetList<Venture>(["admin", "toolkit", "ventures", term, deleted], (offset, limit) =>
    unwrap(api.GET("/api/v1/toolkit/admin/ventures", { params: { query: { offset, limit, ...(term ? { q: term } : {}), ...(deleted ? { include_deleted: true } : {}) } } })),
  );
  const totals = useQuery({
    queryKey: ["admin", "toolkit", "ventures", "totals"],
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/admin/ventures", { params: { query: { limit: 1 } } })),
  });
  const t = totals.data?.totals;
  return (
    <>
      <PageHeader eyebrow="Toolkit" title="Ventures" lead="Every venture members have started in the launch toolkit, and which tools they have used. What they wrote stays private to them; only names, dates and counts are shown." />
      <div className="app-grid" style={{ marginBottom: "var(--space-6)" }}>
        <StatTile label="Ventures" value={t ? formatNumber(t.ventures) : "…"} delta={t ? `${formatNumber(t.founders)} founders` : undefined} />
        <StatTile label="Scored" value={t ? formatNumber(t.scored) : "…"} />
        <StatTile label="With a business plan" value={t ? formatNumber(t.with_plan) : "…"} />
        <StatTile label="With a pitch deck" value={t ? formatNumber(t.with_deck) : "…"} />
      </div>
      <form className="app-cluster" style={{ alignItems: "end", marginBottom: "var(--space-4)" }} role="search" onSubmit={(e) => { e.preventDefault(); setTerm(q.trim()); }}>
        <Input label="Venture name or owner email" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button type="submit" variant="secondary">Search</Button>
        <Checkbox label="Include deleted" checked={deleted} onChange={(e) => setDeleted(e.target.checked)} />
      </form>
      {list.query.isPending ? <SkeletonRows /> : list.query.isError ? <ErrorState error={list.query.error} /> : list.isEmpty ? (
        <EmptyState title={term ? "No venture matches" : "No ventures yet"}>{term ? "Try another name or email." : "Ventures appear here when members start one in the launch toolkit."}</EmptyState>
      ) : (
        <>
          <div className="adm-tablewrap">
            <table className="adm-table">
              <caption className="wo-visually-hidden">Ventures</caption>
              <thead>
                <tr>
                  <th scope="col">Venture</th>
                  <th scope="col">Owner</th>
                  <th scope="col">Profile</th>
                  <th scope="col">Score</th>
                  <th scope="col">Tools used</th>
                  <th scope="col">Started</th>
                </tr>
              </thead>
              <tbody>
                {list.items.map((v) => {
                  const used = [
                    v.plans ? "Plan" : "",
                    v.has_forecast ? "Forecast" : "",
                    v.decks ? `${v.decks} deck${v.decks === 1 ? "" : "s"}` : "",
                    v.prototypes ? `${v.prototypes} prototype${v.prototypes === 1 ? "" : "s"}` : "",
                    v.partner_conversations ? "Partner" : "",
                    v.share_links ? "Shared" : "",
                  ].filter(Boolean);
                  return (
                    <tr key={v.id}>
                      <td>
                        <strong>{v.name}</strong>
                        {v.status !== "active" ? <> <StatusChip tone={v.status === "deleted" ? "danger" : "neutral"}>{humanise(v.status)}</StatusChip></> : null}
                      </td>
                      <td>{v.owner_email}</td>
                      <td>{v.profile_completeness}%</td>
                      <td>{v.latest_score ?? (v.scored_at ? "Not enough data" : "Not scored")}</td>
                      <td>{used.length ? used.join(", ") : <span className="app-faint">Profile only</span>}</td>
                      <td>{formatDate(v.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
    </>
  );
}

// ---- Templates -------------------------------------------------------------------------------

function DeckTemplates() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "toolkit", "deck-templates"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/admin/deck-templates")) });
  const [editing, setEditing] = useState<DeckTemplate | "new" | null>(null);
  return (
    <section className="app-stack" aria-labelledby="deck-tpl">
      <div className="app-cluster" style={{ justifyContent: "space-between" }}>
        <h2 className="h3" id="deck-tpl" style={{ margin: 0 }}>Pitch deck templates</h2>
        <Button size="sm" onClick={() => setEditing("new")}>New template</Button>
      </div>
      <p className="body-sm app-muted" style={{ margin: 0 }}>The decks members can start from. Each template is checked by building it from an empty profile before it is saved. Changes apply to decks made from now on.</p>
      <Loaded query={query} skeleton={<SkeletonRows />} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No templates">Add one to let members make decks.</EmptyState>}>
        {(rows) => (
          <div className="adm-tablewrap">
            <table className="adm-table">
              <caption className="wo-visually-hidden">Pitch deck templates</caption>
              <thead><tr><th scope="col">Name</th><th scope="col">Slides</th><th scope="col">Order</th><th scope="col">Status</th><th scope="col"><span className="wo-visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.slug}>
                    <td><strong>{t.name}</strong><br /><span className="app-faint">{t.description}</span></td>
                    <td>{t.slides.length}</td>
                    <td>{t.position}</td>
                    <td><StatusChip tone={t.active ? "success" : "neutral"}>{t.active ? "Offered" : "Switched off"}</StatusChip></td>
                    <td><Button size="sm" variant="ghost" onClick={() => setEditing(t)}>Edit</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loaded>
      {editing ? (
        <TemplateEditor
          kind="deck"
          initial={editing === "new" ? null : { slug: editing.slug, name: editing.name, description: editing.description, active: editing.active, position: editing.position, body: editing.slides }}
          example={query.data?.[0]?.slides ?? []}
          onClose={() => setEditing(null)}
          onSaved={() => client.invalidateQueries({ queryKey: ["admin", "toolkit", "deck-templates"] })}
        />
      ) : null}
    </section>
  );
}

function PrototypeTemplates() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "toolkit", "prototype-templates"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/admin/prototype-templates")) });
  const [editing, setEditing] = useState<PrototypeTemplate | "new" | null>(null);
  return (
    <section className="app-stack" aria-labelledby="proto-tpl">
      <div className="app-cluster" style={{ justifyContent: "space-between" }}>
        <h2 className="h3" id="proto-tpl" style={{ margin: 0 }}>Prototype templates</h2>
        <Button size="sm" onClick={() => setEditing("new")}>New template</Button>
      </div>
      <p className="body-sm app-muted" style={{ margin: 0 }}>The clickable mock-ups members can start from. The screens are checked against the component list before saving; <code>{"{name}"}</code> becomes the venture&rsquo;s name.</p>
      <Loaded query={query} skeleton={<SkeletonRows />} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No templates">Add one to let members make prototypes.</EmptyState>}>
        {(rows) => (
          <div className="adm-tablewrap">
            <table className="adm-table">
              <caption className="wo-visually-hidden">Prototype templates</caption>
              <thead><tr><th scope="col">Name</th><th scope="col">For</th><th scope="col">Screens</th><th scope="col">Status</th><th scope="col"><span className="wo-visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {rows.map((t) => {
                  const spec = t.spec as { kind?: string; screens?: unknown[] };
                  return (
                    <tr key={t.slug}>
                      <td><strong>{t.name}</strong><br /><span className="app-faint">{t.description}</span></td>
                      <td>{spec.kind === "mobile" ? "Phone app" : spec.kind === "web" ? "Website" : humanise(String(spec.kind ?? ""))}</td>
                      <td>{Array.isArray(spec.screens) ? spec.screens.length : 0}</td>
                      <td><StatusChip tone={t.active ? "success" : "neutral"}>{t.active ? "Offered" : "Switched off"}</StatusChip></td>
                      <td><Button size="sm" variant="ghost" onClick={() => setEditing(t)}>Edit</Button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Loaded>
      {editing ? (
        <TemplateEditor
          kind="prototype"
          initial={editing === "new" ? null : { slug: editing.slug, name: editing.name, description: editing.description, active: editing.active, body: editing.spec }}
          example={query.data?.[0]?.spec ?? {}}
          onClose={() => setEditing(null)}
          onSaved={() => client.invalidateQueries({ queryKey: ["admin", "toolkit", "prototype-templates"] })}
        />
      ) : null}
    </section>
  );
}

interface TemplateDraft {
  slug: string;
  name: string;
  description: string;
  active: boolean;
  position?: number;
  body: unknown;
}

/** One template's name, switch and content. The content is JSON: slides for a deck, a spec for a prototype. */
function TemplateEditor({ kind, initial, example, onClose, onSaved }: { kind: "deck" | "prototype"; initial: TemplateDraft | null; example: unknown; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const [slug, setSlug] = useState(initial?.slug ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [active, setActive] = useState(initial?.active ?? true);
  const [position, setPosition] = useState(String(initial?.position ?? 100));
  const [body, setBody] = useState(pretty(initial?.body ?? example));
  const [jsonProblem, setJsonProblem] = useState("");
  const save = useSubmit(async () => {
    const parsed = parseJson(body);
    if (parsed.problem) {
      setJsonProblem(parsed.problem);
      return;
    }
    setJsonProblem("");
    const common = { slug: slug.trim(), name: name.trim(), description: description.trim(), active };
    if (kind === "deck") {
      await unwrap(api.PUT("/api/v1/toolkit/admin/deck-templates", { body: { ...common, position: Number(position) || 0, slides: parsed.value as Record<string, unknown>[] } }));
    } else {
      await unwrap(api.PUT("/api/v1/toolkit/admin/prototype-templates", { body: { ...common, spec: parsed.value as Record<string, unknown> } }));
    }
    toast.show(initial ? "Template saved" : "Template added");
    await onSaved();
    onClose();
  });
  const errors = errorsFrom(save.error).fields;
  return (
    <Modal open onClose={onClose} eyebrow="Toolkit" title={initial ? `Edit ${initial.name}` : `New ${kind === "deck" ? "deck" : "prototype"} template`}
      actions={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={save.busy} disabled={!slug.trim() || !name.trim()} onClick={() => void save.run()}>Save</Button></>}>
      <div className="app-stack">
        <FormError error={save.error} />
        <div className="app-formgrid">
          <Input label="Short name (letters, numbers and dashes)" value={slug} readOnly={Boolean(initial)} onChange={(e) => setSlug(e.target.value.toLowerCase())} error={errors.slug} hint={initial ? "Fixed once created." : undefined} />
          <Input label="Name members see" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
        </div>
        <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} />
        {kind === "deck" ? <Input label="Order in the list" type="number" min={0} max={999} value={position} onChange={(e) => setPosition(e.target.value)} error={errors.position} /> : null}
        <Checkbox label="Offer this template to members" checked={active} onChange={(e) => setActive(e.target.checked)} />
        <Textarea
          label={kind === "deck" ? "Slides (JSON)" : "Screens and components (JSON)"}
          rows={14}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          error={jsonProblem || errors.slides || errors.spec}
          hint="Start from an existing template's content and change it. The server explains anything it cannot use."
          style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}
        />
      </div>
    </Modal>
  );
}

function PlanSections() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "toolkit", "plan-sections"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/admin/plan-sections")) });
  const [editing, setEditing] = useState<PlanSection | null>(null);
  return (
    <section className="app-stack" aria-labelledby="plan-secs">
      <h2 className="h3" id="plan-secs" style={{ margin: 0 }}>Business plan sections</h2>
      <p className="body-sm app-muted" style={{ margin: 0 }}>The sections every business plan has, and the guidance each one shows members. Changes apply to plans made from now on.</p>
      <Loaded query={query} skeleton={<SkeletonRows />}>
        {(rows) => (
          <div className="adm-tablewrap">
            <table className="adm-table">
              <caption className="wo-visually-hidden">Business plan sections</caption>
              <thead><tr><th scope="col">No.</th><th scope="col">Section</th><th scope="col">Chapter</th><th scope="col">Status</th><th scope="col"><span className="wo-visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.number}>
                    <td>{s.number}</td>
                    <td><strong>{s.title}</strong></td>
                    <td>{s.chapter}</td>
                    <td><StatusChip tone={s.active ? "success" : "neutral"}>{s.active ? "In use" : "Left out"}</StatusChip></td>
                    <td><Button size="sm" variant="ghost" onClick={() => setEditing(s)}>Edit</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loaded>
      {editing ? <SectionEditor section={editing} onClose={() => setEditing(null)} onSaved={() => client.invalidateQueries({ queryKey: ["admin", "toolkit", "plan-sections"] })} /> : null}
    </section>
  );
}

function SectionEditor({ section, onClose, onSaved }: { section: PlanSection; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const [title, setTitle] = useState(section.title);
  const [chapter, setChapter] = useState(section.chapter);
  const [guidance, setGuidance] = useState(section.guidance);
  const [active, setActive] = useState(section.active);
  const save = useSubmit(async () => {
    await unwrap(api.PATCH("/api/v1/toolkit/admin/plan-sections/{number}", { params: { path: { number: section.number } }, body: { title: title.trim(), chapter: chapter.trim(), guidance: guidance.trim(), active } }));
    toast.show("Section saved");
    await onSaved();
    onClose();
  });
  const errors = errorsFrom(save.error).fields;
  return (
    <Modal open onClose={onClose} eyebrow={`Section ${section.number}`} title={section.title}
      actions={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={save.busy} onClick={() => void save.run()}>Save</Button></>}>
      <div className="app-stack">
        <FormError error={save.error} />
        <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title} />
        <Input label="Chapter" value={chapter} onChange={(e) => setChapter(e.target.value)} error={errors.chapter} />
        <Textarea label="Guidance members see" rows={5} maxLength={2000} value={guidance} onChange={(e) => setGuidance(e.target.value)} error={errors.guidance} hint="What this section should cover. Members see it when they write the section." />
        <Checkbox label="Include this section in business plans" checked={active} onChange={(e) => setActive(e.target.checked)} />
        {section.number === 1 ? <p className="body-sm app-muted" style={{ margin: 0 }}>The executive summary is always included.</p> : null}
      </div>
    </Modal>
  );
}

const TEMPLATE_TABS = [
  { id: "decks", label: "Pitch decks" },
  { id: "prototypes", label: "Prototypes" },
  { id: "plan", label: "Business plan sections" },
] as const;

export function ToolkitTemplates() {
  useDocumentTitle("Toolkit templates");
  const [tab, setTab] = useState<(typeof TEMPLATE_TABS)[number]["id"]>("decks");
  return (
    <>
      <PageHeader eyebrow="Toolkit" title="Templates" lead="What members start from in the launch toolkit: deck and prototype templates, and the sections of the business plan." />
      <div role="tablist" aria-label="Template kinds" className="app-cluster" style={{ marginBottom: "var(--space-6)" }}>
        {TEMPLATE_TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} aria-controls={`tpl-${t.id}`} id={`tpl-tab-${t.id}`} className="app-react" onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </div>
      <div role="tabpanel" id={`tpl-${tab}`} aria-labelledby={`tpl-tab-${tab}`}>
        {tab === "decks" ? <DeckTemplates /> : tab === "prototypes" ? <PrototypeTemplates /> : <PlanSections />}
      </div>
    </>
  );
}

// ---- Scoring rubric --------------------------------------------------------------------------

export function ToolkitRubric() {
  useDocumentTitle("Scoring rubric");
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const query = useQuery({ queryKey: ["admin", "toolkit", "rubrics"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/admin/score-rubrics")) });
  const [viewing, setViewing] = useState<Rubric | null>(null);
  const [drafting, setDrafting] = useState(false);
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "toolkit", "rubrics"] });
  const activate = async (r: Rubric) => {
    await guard(() => unwrap(api.POST("/api/v1/toolkit/admin/score-rubrics/{version}/activate", { params: { path: { version: r.version } } })));
    toast.show(`Version ${r.version} is now used for new scores`);
    await refresh();
  };
  const current = query.data?.find((r) => r.active);
  return (
    <>
      <PageHeader eyebrow="Toolkit" title="Scoring rubric" lead="How a venture's validation score is worked out: the areas, their weights and the verdict for each score. Scores are calculated by code from this rubric, never by AI."
        actions={<Button onClick={() => setDrafting(true)} disabled={!current}>New version</Button>} />
      <Alert tone="info" title="Versions are kept">A new version is not used until you make it active. Scores already given keep the version they were made with. Making a version active asks for a fresh authenticator code.</Alert>
      <div style={{ marginTop: "var(--space-6)" }}>
        <Loaded query={query} skeleton={<SkeletonRows />}>
          {(rows) => (
            <div className="adm-tablewrap">
              <table className="adm-table">
                <caption className="wo-visually-hidden">Rubric versions</caption>
                <thead><tr><th scope="col">Version</th><th scope="col">Areas</th><th scope="col">Notes</th><th scope="col">Added</th><th scope="col">Status</th><th scope="col"><span className="wo-visually-hidden">Actions</span></th></tr></thead>
                <tbody>
                  {rows.map((r) => {
                    const dims = (r.config as { dimensions?: Array<{ label?: string; weight?: number }> }).dimensions ?? [];
                    return (
                      <tr key={r.version}>
                        <td>v{r.version}</td>
                        <td style={{ whiteSpace: "normal", minWidth: "18rem" }}>{dims.map((d) => `${d.label ?? "?"} ${d.weight ?? 0}%`).join(", ") || "—"}</td>
                        <td>{r.notes || <span className="app-faint">No notes</span>}</td>
                        <td>{formatDate(r.created_at)}</td>
                        <td>{r.active ? <StatusChip tone="success">In use</StatusChip> : <StatusChip tone="neutral">Not used</StatusChip>}</td>
                        <td>
                          <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
                            <Button size="sm" variant="ghost" onClick={() => setViewing(r)}>View</Button>
                            {!r.active ? <Button size="sm" variant="secondary" onClick={() => void activate(r)}>Make active</Button> : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Loaded>
      </div>
      {viewing ? (
        <Modal open onClose={() => setViewing(null)} eyebrow="Scoring rubric" title={`Version ${viewing.version}`} actions={<Button variant="ghost" onClick={() => setViewing(null)}>Close</Button>}>
          <pre style={{ margin: 0, maxHeight: "60vh", overflow: "auto", fontSize: 13 }}>{pretty(viewing.config)}</pre>
        </Modal>
      ) : null}
      {drafting && current ? <RubricDraft from={current} onClose={() => setDrafting(false)} onSaved={refresh} /> : null}
    </>
  );
}

function RubricDraft({ from, onClose, onSaved }: { from: Rubric; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const [config, setConfig] = useState(pretty(from.config));
  const [notes, setNotes] = useState("");
  const [jsonProblem, setJsonProblem] = useState("");
  const save = useSubmit(async () => {
    const parsed = parseJson(config);
    if (parsed.problem) {
      setJsonProblem(parsed.problem);
      return;
    }
    setJsonProblem("");
    const made = await unwrap(api.POST("/api/v1/toolkit/admin/score-rubrics", { body: { config: parsed.value as Record<string, unknown>, notes: notes.trim() } }));
    toast.show(`Version ${made.version} added. Make it active to use it.`);
    await onSaved();
    onClose();
  });
  const errors = errorsFrom(save.error).fields;
  return (
    <Modal open onClose={onClose} eyebrow="Scoring rubric" title={`New version, from v${from.version}`}
      actions={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={save.busy} onClick={() => void save.run()}>Add version</Button></>}>
      <div className="app-stack">
        <FormError error={save.error} />
        <Input label="What changed (optional)" maxLength={300} value={notes} onChange={(e) => setNotes(e.target.value)} error={errors.notes} />
        <Textarea label="Rubric (JSON)" rows={16} value={config} onChange={(e) => setConfig(e.target.value)} error={jsonProblem || errors.config}
          hint="Weights must add up to 100 and the verdicts must cover every score from 0 to 100. It is checked before it is stored."
          style={{ fontFamily: "var(--font-mono)", fontSize: 13 }} />
      </div>
    </Modal>
  );
}

// ---- AI usage and settings -------------------------------------------------------------------

function Settings() {
  const query = useQuery({ queryKey: ["admin", "toolkit", "settings"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/admin/settings")) });
  return (
    <section className="adm-card" aria-labelledby="tk-settings">
      <h2 className="adm-card__title" id="tk-settings">How the toolkit is set up</h2>
      <Loaded query={query} skeleton={<SkeletonRows />}>
        {(s) => {
          const aiOn = Boolean(s.ai_provider) && s.ai_provider !== "fake";
          return (
            <div className="app-stack">
              {!aiOn ? (
                <Alert tone="warning" title="AI writing is off">
                  The toolkit works without it. To switch it on, add <code>AI_API_KEY</code> (and <code>AI_BASE_URL</code>) on the API service in Railway.
                </Alert>
              ) : null}
              <dl className="adm-kv">
                <div className="adm-kv__row"><dt>Tools switched on</dt><dd>{Object.entries(s.features).map(([k, on]) => <Badge key={k} variant={on ? "success" : "neutral"}>{TOOL_LABELS[k] ?? humanise(k)}{on ? "" : " (off)"}</Badge>)}</dd></div>
                <div className="adm-kv__row"><dt>AI service</dt><dd>{aiOn ? (s.ai_provider === "http" ? "Connected (OpenAI compatible API)" : s.ai_provider) : "Off"}{s.ai_fallback_provider ? `, with ${s.ai_fallback_provider} as a fallback` : ""}</dd></div>
                <div className="adm-kv__row"><dt>AI requests per member each day</dt><dd>{formatNumber(s.ai_daily_run_ceiling)}</dd></div>
                <div className="adm-kv__row"><dt>Web research</dt><dd>{s.research_provider ? `${s.research_provider} (${s.research_domains} sites allowed)` : "Off: scores and plans use what members wrote"}</dd></div>
                <div className="adm-kv__row"><dt>Ventures per member</dt><dd>{s.max_ventures_per_member}</dd></div>
                <div className="adm-kv__row"><dt>Downloads kept for</dt><dd>{s.export_retention_days} days</dd></div>
                <div className="adm-kv__row"><dt>Deleted ventures can be restored for</dt><dd>{s.venture_delete_grace_days} days</dd></div>
              </dl>
              <p className="body-sm app-muted" style={{ margin: 0 }}>These are set on the API service in Railway, not here.</p>
            </div>
          );
        }}
      </Loaded>
    </section>
  );
}

function isoDaysAgo(days: number): string {
  const d = new Date(Date.now() - days * 86_400_000);
  return d.toISOString().slice(0, 10);
}

export function ToolkitUsage() {
  useDocumentTitle("AI usage");
  const [from, setFrom] = useState(isoDaysAgo(30));
  const [to, setTo] = useState(isoDaysAgo(0));
  const [group, setGroup] = useState<"day" | "prompt" | "agent">("day");
  const [downloading, setDownloading] = useState(false);
  const toast = useToast();
  const params = { from, to, group_by: group };
  const query = useQuery({
    queryKey: ["admin", "toolkit", "usage", from, to, group],
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/admin/usage", { params: { query: params as never } })),
  });
  const rows = query.data ?? [];
  const total = rows.reduce((acc, r) => ({ runs: acc.runs + r.runs, tokens: acc.tokens + r.input_tokens + r.output_tokens, cost: acc.cost + r.estimated_cost_minor }), { runs: 0, tokens: 0, cost: 0 });
  const currency = rows[0]?.currency ?? "USD";
  const download = async () => {
    setDownloading(true);
    try {
      await downloadFile(`/api/v1/toolkit/admin/usage.csv?${new URLSearchParams(params).toString()}`, "toolkit-usage.csv");
    } catch {
      toast.show("Could not download the file. Try again.");
    } finally {
      setDownloading(false);
    }
  };
  return (
    <>
      <PageHeader eyebrow="Toolkit" title="AI usage" lead="How much the launch toolkit asked the AI, and an estimate of what it cost. Only counts and sizes are kept, never what members wrote." />
      <Settings />
      <form className="app-cluster" style={{ alignItems: "end", margin: "var(--space-6) 0 var(--space-4)" }} onSubmit={(e) => e.preventDefault()}>
        <Input label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <Input label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        <Select label="Group by" options={[{ value: "day", label: "Day" }, { value: "prompt", label: "Task" }, { value: "agent", label: "Assistant" }]} value={group} onChange={(e) => setGroup(e.target.value as typeof group)} />
        <Button variant="ghost" loading={downloading} onClick={() => void download()}>Download CSV</Button>
      </form>
      <div className="app-grid" style={{ marginBottom: "var(--space-6)" }}>
        <StatTile label="AI requests" value={formatNumber(total.runs)} />
        <StatTile label="Tokens" value={formatNumber(total.tokens)} />
        <StatTile label="Estimated cost" value={`${currency} ${(total.cost / 100).toFixed(2)}`} delta="From the price table set on the server" />
      </div>
      <Loaded query={query} skeleton={<SkeletonRows />} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No AI use in this period">Requests appear here once members use the AI features.</EmptyState>}>
        {(data) => (
          <div className="adm-tablewrap">
            <table className="adm-table">
              <caption className="wo-visually-hidden">AI usage</caption>
              <thead><tr><th scope="col">{group === "day" ? "Day" : group === "prompt" ? "Task" : "Assistant"}</th><th scope="col">Requests</th><th scope="col">Worked</th><th scope="col">Tokens in</th><th scope="col">Tokens out</th><th scope="col">Estimated cost</th></tr></thead>
              <tbody>
                {data.map((r) => (
                  <tr key={r.key}>
                    <td>{group === "day" ? formatDate(r.key) : r.key}</td>
                    <td>{formatNumber(r.runs)}</td>
                    <td>{formatNumber(r.outcomes.ok ?? 0)}</td>
                    <td>{formatNumber(r.input_tokens)}</td>
                    <td>{formatNumber(r.output_tokens)}</td>
                    <td>{r.currency} {(r.estimated_cost_minor / 100).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loaded>
    </>
  );
}

// ---- Quality ---------------------------------------------------------------------------------

export function ToolkitQuality() {
  useDocumentTitle("Toolkit quality");
  const query = useQuery({ queryKey: ["admin", "toolkit", "quality"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/admin/quality")) });
  return (
    <>
      <PageHeader eyebrow="Toolkit" title="Quality queue" lead="Where the toolkit is failing members over the last seven days: AI answers that could not be used, and jobs that did not finish. Identifiers only; nothing members wrote is shown." />
      <Loaded query={query} skeleton={<SkeletonRows />}>
        {(q) => {
          const rate = q.runs ? Math.round(((q.runs - q.not_ok) / q.runs) * 100) : 100;
          return (
            <div className="app-stack app-stack--lg">
              <div className="app-grid">
                <StatTile label={`AI requests, last ${q.window_days} days`} value={formatNumber(q.runs)} />
                <StatTile label="Answers that worked" value={`${rate}%`} delta={`${formatNumber(q.not_ok)} did not`} />
                <StatTile label="Jobs that failed" value={formatNumber(q.failed_jobs.reduce((n, j) => n + Number(j.count ?? 0), 0))} />
              </div>
              {q.not_ok === 0 && q.failed_jobs.length === 0 ? (
                <EmptyState title="Nothing to look at">No failed answers or jobs in the last {q.window_days} days.</EmptyState>
              ) : (
                <>
                  <section className="app-stack" aria-labelledby="q-prompts">
                    <h2 className="h3" id="q-prompts" style={{ margin: 0 }}>Answers that could not be used, by task</h2>
                    <QualityTable rows={q.by_prompt} columns={[["prompt_id", "Task"], ["outcome", "What happened"], ["count", "Times"]]} empty="None." />
                  </section>
                  <section className="app-stack" aria-labelledby="q-jobs">
                    <h2 className="h3" id="q-jobs" style={{ margin: 0 }}>Jobs that failed, by kind</h2>
                    <QualityTable rows={q.failed_jobs} columns={[["kind", "Job"], ["error_code", "Reason"], ["count", "Times"]]} empty="None." />
                  </section>
                  <section className="app-stack" aria-labelledby="q-recent">
                    <h2 className="h3" id="q-recent" style={{ margin: 0 }}>Most recent</h2>
                    <QualityTable rows={q.recent} columns={[["created_at", "When"], ["prompt_id", "Task"], ["outcome", "What happened"], ["model", "Model"], ["job_id", "Job"]]} empty="None." />
                  </section>
                </>
              )}
            </div>
          );
        }}
      </Loaded>
    </>
  );
}

function QualityTable({ rows, columns, empty }: { rows: Array<Record<string, unknown>>; columns: Array<[string, string]>; empty: string }) {
  if (rows.length === 0) return <p className="body-sm app-muted" style={{ margin: 0 }}>{empty}</p>;
  const show = (key: string, value: unknown) => {
    if (value === null || value === undefined || value === "") return "—";
    if (key === "created_at") return formatDateTime(String(value));
    if (key === "outcome" || key === "error_code") return humanise(String(value));
    return String(value);
  };
  return (
    <div className="adm-tablewrap">
      <table className="adm-table">
        <thead><tr>{columns.map(([, label]) => <th key={label} scope="col">{label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{columns.map(([key]) => <td key={key}>{key === "job_id" && r[key] ? <code>{String(r[key]).slice(-8)}</code> : show(key, r[key])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
