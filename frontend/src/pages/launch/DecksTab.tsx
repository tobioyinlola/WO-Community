import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Presentation } from "lucide-react";
import { useEffect, useState } from "react";
import { api, unwrap } from "../../api/client";
import { ApiError } from "../../api/errors";
import { Alert, Badge, Button, Card, CardText, CardTitle, Input, Select, Textarea } from "../../components";
import { formatDate } from "../../lib/format";
import { EmptyState, Loaded, SkeletonCards, SkeletonRows } from "../../ui/blocks";
import { FormError, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";
import { useExport } from "./jobs";
import { useWorkspace } from "./Workspace";
import { useAiEnabled } from "./config";

type El = Record<string, unknown> & { id: string; type: string };
type Slide = { id: string; layout: string; title: string; notes: string; elements: El[] };
type Op = { op: "replace" | "remove" | "add" | "move"; path: string; value?: unknown; from?: string };

const str = (v: unknown) => (typeof v === "string" ? v : "");
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

/** One slide as it will be shown, with figures looked up from the forecast. */
function SlidePreview({ slide, theme }: { slide: Record<string, unknown>; theme: Record<string, unknown> }) {
  const elements = (Array.isArray(slide.elements) ? slide.elements : []) as El[];
  const palette = (theme.colors ?? theme.palette_colors ?? {}) as Record<string, string>;
  return (
    <div
      className="app-slide"
      style={{ background: palette.background, color: palette.text }}
    >
      <p className="app-slide__title" style={{ color: palette.accent }}>{str(slide.title)}</p>
      <div className="app-stack" style={{ gap: "var(--space-2)" }}>
        {elements.map((el) => {
          if (el.type === "bullets") return <ul key={el.id} style={{ margin: 0 }}>{strs(el.items).map((t, i) => <li key={i}>{t}</li>)}</ul>;
          if (el.type === "metric") return <p key={el.id} style={{ margin: 0 }}><strong>{str(el.value)}</strong> {str(el.label)}</p>;
          if (el.type === "table")
            return (
              <table key={el.id} className="app-table">
                <thead><tr>{strs(el.columns).map((c, i) => <th key={i} scope="col">{c}</th>)}</tr></thead>
                <tbody>{((el.rows as string[][]) ?? []).map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
              </table>
            );
          if (el.type === "image") return <p key={el.id} className="caption" style={{ margin: 0 }}>Image: {str(el.alt)}</p>;
          const text = str(el.text) || str(el.value) || strs(el.items).join(", ");
          return el.type === "heading" ? <h3 key={el.id} className="h4" style={{ margin: 0 }}>{text}</h3> : <p key={el.id} style={{ margin: 0 }}>{text}</p>;
        })}
      </div>
    </div>
  );
}

function DeckEditor({ deckId, onBack }: { deckId: string; onBack: () => void }) {
  const ai = useAiEnabled();
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const toast = useToast();
  const base = { venture_id: ventureId, deck_id: deckId };
  const deck = useQuery({ queryKey: ["toolkit", ventureId, "deck", deckId], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/decks/{deck_id}", { params: { path: base } })) });
  const shown = useQuery({ queryKey: ["toolkit", ventureId, "deck", deckId, "shown", deck.data?.version], enabled: Boolean(deck.data), queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/decks/{deck_id}/shown", { params: { path: base } })) });
  const findings = useQuery({ queryKey: ["toolkit", ventureId, "deck", deckId, "check", deck.data?.version], enabled: Boolean(deck.data), queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/decks/{deck_id}/check", { params: { path: base } })) });
  const versions = useQuery({ queryKey: ["toolkit", ventureId, "deck", deckId, "versions", deck.data?.version], enabled: Boolean(deck.data), queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/decks/{deck_id}/versions", { params: { path: base } })) });
  const [index, setIndex] = useState(0);
  const [slide, setSlide] = useState<Slide | null>(null);
  const [title, setTitle] = useState("");
  const slides = ((deck.data?.content.slides as Slide[] | undefined) ?? []);

  useEffect(() => {
    const current = slides[Math.min(index, Math.max(slides.length - 1, 0))];
    setSlide(current ? (JSON.parse(JSON.stringify(current)) as Slide) : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deck.data, index]);
  useEffect(() => { if (deck.data) setTitle(deck.data.title); }, [deck.data]);

  const refresh = () => client.invalidateQueries({ queryKey: ["toolkit", ventureId, "deck", deckId] });
  const apply = useSubmit(async (ops: Op[], note: string = "") => {
    await unwrap(api.PATCH("/api/v1/toolkit/ventures/{venture_id}/decks/{deck_id}", { params: { path: base }, body: { ops, base_version: deck.data?.version ?? 1, label: note } }));
    await refresh();
  });
  const exporter = useExport((format) => unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/decks/{deck_id}/export", { params: { path: base }, body: { format: format as "pptx" | "pdf" } })));
  const restore = useMutation({
    mutationFn: (v: number) => unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/decks/{deck_id}/versions/{version}/restore", { params: { path: { ...base, version: v } } })),
    onSuccess: async () => { toast.show("Earlier version restored"); await refresh(); },
  });
  const assist = useSubmit(async (action: "shorten" | "punchier" | "simplify") => {
    if (!slide) return null;
    return unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/decks/{deck_id}/assist", { params: { path: base }, body: { slide_id: slide.id, action } }));
  });
  const [suggestion, setSuggestion] = useState<Awaited<ReturnType<typeof assist.run>>>(null);

  const stale = apply.error instanceof ApiError && apply.error.status === 409;
  const original = slides[index];
  const changed = slide && original && JSON.stringify(slide) !== JSON.stringify(original);
  const saveSlide = () => {
    if (!slide || !original) return;
    const ops: Op[] = [];
    if (slide.title !== original.title) ops.push({ op: "replace", path: `/slides/${index}/title`, value: slide.title });
    if (slide.notes !== original.notes) ops.push({ op: "replace", path: `/slides/${index}/notes`, value: slide.notes });
    slide.elements.forEach((el, i) => {
      if (JSON.stringify(el) !== JSON.stringify(original.elements[i])) ops.push({ op: "replace", path: `/slides/${index}/elements/${i}`, value: el });
    });
    void apply.run(ops, `Edited slide ${index + 1}`).then(() => toast.show("Slide saved"));
  };
  const setEl = (i: number, patch: Partial<El>) => setSlide((s) => (s ? { ...s, elements: s.elements.map((el, j) => (j === i ? { ...el, ...patch } : el)) } : s));

  return (
    <Loaded query={deck} skeleton={<SkeletonRows />}>
      {(d) => (
        <div className="app-stack app-stack--lg">
          <div className="app-cluster" style={{ justifyContent: "space-between" }}>
            <div className="app-cluster">
              <Button variant="ghost" size="sm" onClick={onBack}>All decks</Button>
              <h2 className="h3" style={{ margin: 0 }}>{title}</h2>
              <Badge variant="neutral">Version {d.version}</Badge>
            </div>
            <div className="app-cluster">
              <Button variant="secondary" size="sm" loading={exporter.busy} onClick={() => void exporter.run("pptx")}>Download PowerPoint</Button>
              <Button variant="secondary" size="sm" loading={exporter.busy} onClick={() => void exporter.run("pdf")}>Download PDF</Button>
            </div>
          </div>
          <FormError error={exporter.error} />
          {findings.data && findings.data.length > 0 ? (
            <Alert tone="info" title={`${findings.data.length} thing${findings.data.length > 1 ? "s" : ""} to look at before you show this`}>
              <ul style={{ margin: 0 }}>{findings.data.slice(0, 6).map((f, i) => <li key={i}>Slide {f.slide}: {f.message}</li>)}</ul>
            </Alert>
          ) : null}
          <div className="app-split">
            <nav aria-label="Slides">
              <ol className="app-list" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {slides.map((s, i) => (
                  <li key={s.id}>
                    <button type="button" className="app-list__item" aria-current={i === index ? "true" : undefined} onClick={() => setIndex(i)}>
                      <div className="app-list__main"><p className="app-list__title">{i + 1}. {s.title || "Untitled slide"}</p><p className="app-list__meta">{s.layout.replace("_", " ")}</p></div>
                    </button>
                  </li>
                ))}
              </ol>
            </nav>
            <div className="app-stack">
              {shown.data?.slides[index] ? <SlidePreview slide={shown.data.slides[index]} theme={shown.data.theme} /> : null}
              {slide ? (
                <Card>
                  {stale ? <Alert tone="warning" title="This changed somewhere else" action={<Button size="sm" variant="secondary" onClick={() => void deck.refetch()}>Reload</Button>}>Reload to see the latest.</Alert> : <FormError error={apply.error} />}
                  <div className="app-stack">
                    <Input label="Slide title" value={slide.title} onChange={(e) => setSlide({ ...slide, title: e.target.value })} />
                    {slide.elements.map((el, i) =>
                      el.type === "bullets" ? (
                        <Textarea key={el.id} label="Bullet points, one per line" rows={4} value={strs(el.items).join("\n")} onChange={(e) => setEl(i, { items: e.target.value.split("\n").filter((x) => x.trim()) })} />
                      ) : el.type === "text" || el.type === "heading" ? (
                        <Textarea key={el.id} label={el.type === "heading" ? "Heading" : "Text"} rows={el.type === "heading" ? 1 : 3} value={str(el.text)} onChange={(e) => setEl(i, { text: e.target.value })} />
                      ) : el.type === "metric" ? (
                        <div key={el.id} className="app-formgrid">
                          <Input label="Figure" value={str(el.value)} onChange={(e) => setEl(i, { value: e.target.value })} />
                          <Input label="What it measures" value={str(el.label)} onChange={(e) => setEl(i, { label: e.target.value })} />
                        </div>
                      ) : el.type === "linked" ? (
                        <p key={el.id} className="body-sm app-muted" style={{ margin: 0 }}>This content stays in step with your {str(el.kind).replace("_", " ")}, so there is nothing to type here.</p>
                      ) : null,
                    )}
                    <Textarea label="Speaker notes" rows={2} value={slide.notes} onChange={(e) => setSlide({ ...slide, notes: e.target.value })} />
                    <div className="app-cluster">
                      <Button loading={apply.busy} disabled={!changed} onClick={saveSlide}>Save this slide</Button>
                      <Button variant="ghost" onClick={() => void apply.run([{ op: "remove", path: `/slides/${index}` }], `Removed slide ${index + 1}`)}>Remove slide</Button>
                    </div>
                    {ai ? (<>
                    <hr className="app-rule" />
                    <div className="app-cluster">
                      <span className="body-sm app-muted">Reword this slide:</span>
                      {(["shorten", "punchier", "simplify"] as const).map((a) => (
                        <Button key={a} size="sm" variant="secondary" loading={assist.busy} onClick={async () => setSuggestion(await assist.run(a) ?? null)}>{a === "shorten" ? "Shorter" : a === "punchier" ? "Punchier" : "Simpler"}</Button>
                      ))}
                    </div>
                    <FormError error={assist.error} />
                    </>) : null}
                    {suggestion ? (
                      <Card variant="white">
                        <p className="eyebrow" style={{ margin: "0 0 var(--space-2)" }}>Suggestion</p>
                        <ul className="app-stack" style={{ margin: 0, listStyle: "none", padding: 0 }}>{suggestion.elements.map((e, i) => <li key={i} className="body-sm">{str(e.text) || strs(e.items).join("; ")}</li>)}</ul>
                        {suggestion.removed.length > 0 ? <p className="caption app-muted">Left out because we could not back them up: {suggestion.removed.join(", ")}.</p> : null}
                        <div className="app-cluster" style={{ marginTop: "var(--space-3)" }}>
                          <Button size="sm" onClick={async () => {
                            const ops: Op[] = suggestion.elements.map((e) => {
                              const at = slide.elements.findIndex((x) => x.id === e.id);
                              return { op: "replace" as const, path: `/slides/${index}/elements/${at}`, value: { ...slide.elements[at], ...e } };
                            }).filter((o) => !o.path.endsWith("/-1"));
                            await apply.run(ops, "Reworded");
                            setSuggestion(null);
                          }}>Use this</Button>
                          <Button size="sm" variant="ghost" onClick={() => setSuggestion(null)}>Discard</Button>
                        </div>
                      </Card>
                    ) : null}
                  </div>
                </Card>
              ) : null}
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
            </div>
          </div>
        </div>
      )}
    </Loaded>
  );
}

export default function DecksTab() {
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [template, setTemplate] = useState("");
  const [name, setName] = useState("");
  const decks = useQuery({ queryKey: ["toolkit", ventureId, "decks"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/decks", { params: { path: { venture_id: ventureId } } })) });
  const templates = useQuery({ queryKey: ["toolkit", "deck-templates"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/deck-templates")), staleTime: 3_600_000 });
  const create = useSubmit(async () => {
    const made = await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/decks", { params: { path: { venture_id: ventureId } }, body: { template: template || (templates.data?.[0]?.slug ?? ""), ...(name.trim() ? { title: name.trim() } : {}) } }));
    await client.invalidateQueries({ queryKey: ["toolkit", ventureId] });
    setName("");
    setOpen(made.id);
  });
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/toolkit/ventures/{venture_id}/decks/{deck_id}", { params: { path: { venture_id: ventureId, deck_id: id } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["toolkit", ventureId] }),
  });
  if (open) return <DeckEditor deckId={open} onBack={() => setOpen(null)} />;
  return (
    <div className="app-stack app-stack--lg">
      <Card>
        <h2 className="h3" style={{ margin: "0 0 var(--space-2)" }}>Start a pitch deck</h2>
        <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-4)" }}>Slides are filled from your profile in your own words, and figures stay linked to the forecast.</p>
        <div className="app-stack">
          <FormError error={create.error} />
          <div className="app-formgrid">
            <Select label="Template" options={(templates.data ?? []).map((t) => ({ value: t.slug, label: `${t.name} (${t.slide_count} slides)` }))} value={template || templates.data?.[0]?.slug || ""} onChange={(e) => setTemplate(e.target.value)} hint={templates.data?.find((t) => t.slug === (template || templates.data?.[0]?.slug))?.description} />
            <Input label="Name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div><Button loading={create.busy} disabled={!(template || templates.data?.[0]?.slug)} onClick={() => void create.run()}>Create deck</Button></div>
        </div>
      </Card>
      <Loaded query={decks} skeleton={<SkeletonCards count={2} />} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No decks yet" icon={<Presentation size={22} strokeWidth={1.5} />}>Your decks will be listed here.</EmptyState>}>
        {(list) => (
          <div className="app-grid">
            {list.map((d) => (
              <Card key={d.id}>
                <CardTitle>{d.title}</CardTitle>
                <CardText>{d.slide_count} slides &middot; updated {formatDate(d.updated_at)}</CardText>
                <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                  <Button size="sm" variant="secondary" onClick={() => setOpen(d.id)}>Open</Button>
                  <Button size="sm" variant="ghost" onClick={() => remove.mutate(d.id)} aria-label={`Delete ${d.title}`}>Delete</Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </Loaded>
    </div>
  );
}
