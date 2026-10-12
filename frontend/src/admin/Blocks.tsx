import { ArrowDown, ArrowUp, Trash2 } from "lucide-react";
import { Button, Input, Select, Textarea } from "../components";
import { htmlToText, textToHtml } from "../lib/html";

/** One piece of a newsletter. Images need an upload, so an existing one is kept as it is. */
export type Block =
  | { type: "heading"; text: string; level: 1 | 2 }
  | { type: "paragraph"; html: string }
  | { type: "button"; label: string; url: string }
  | { type: "divider" }
  | { type: "image"; [key: string]: unknown };

const LABELS: Record<string, string> = { heading: "Heading", paragraph: "Paragraph", button: "Button", divider: "Divider line", image: "Image" };

export function blankBlock(type: "heading" | "paragraph" | "button" | "divider"): Block {
  if (type === "heading") return { type, text: "", level: 2 };
  if (type === "paragraph") return { type, html: "" };
  if (type === "button") return { type, label: "", url: "" };
  return { type };
}

export function asBlocks(value: unknown): Block[] {
  return Array.isArray(value) ? (value as Block[]) : [];
}

/** Edits a list of newsletter blocks: add, reorder, change and remove. */
export function BlocksEditor({ blocks, onChange, error }: { blocks: Block[]; onChange: (next: Block[]) => void; error?: string }) {
  const update = (i: number, block: Block) => onChange(blocks.map((b, j) => (j === i ? block : b)));
  const move = (i: number, by: number) => {
    const next = [...blocks];
    const [item] = next.splice(i, 1);
    if (item) next.splice(i + by, 0, item);
    onChange(next);
  };
  return (
    <div className="app-stack">
      <span className="wo-label">Content</span>
      <p className="caption app-muted" style={{ margin: 0 }}>Use {"{{first_name}}"} to greet each person by name.</p>
      {blocks.length === 0 ? <p className="body-sm app-muted" style={{ margin: 0 }}>No content yet. Add a block below.</p> : null}
      {blocks.map((b, i) => (
        <div key={i} className="app-proto-card">
          <div className="app-cluster" style={{ justifyContent: "space-between", marginBottom: "var(--space-2)" }}>
            <strong>{LABELS[b.type]}</strong>
            <span className="app-cluster" style={{ flexWrap: "nowrap", gap: 0 }}>
              <button type="button" className="app-iconbtn" aria-label={`Move block ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp size={18} strokeWidth={1.5} /></button>
              <button type="button" className="app-iconbtn" aria-label={`Move block ${i + 1} down`} disabled={i === blocks.length - 1} onClick={() => move(i, 1)}><ArrowDown size={18} strokeWidth={1.5} /></button>
              <button type="button" className="app-iconbtn" aria-label={`Remove block ${i + 1}`} onClick={() => onChange(blocks.filter((_, j) => j !== i))}><Trash2 size={18} strokeWidth={1.5} /></button>
            </span>
          </div>
          {b.type === "heading" ? (
            <div className="app-formgrid">
              <Input label="Heading text" value={b.text} onChange={(e) => update(i, { ...b, text: e.target.value })} />
              <Select label="Size" options={[{ value: "1", label: "Large" }, { value: "2", label: "Medium" }]} value={String(b.level)} onChange={(e) => update(i, { ...b, level: e.target.value === "1" ? 1 : 2 })} />
            </div>
          ) : b.type === "paragraph" ? (
            <Textarea label="Text" rows={4} hint="Leave a blank line between paragraphs." value={htmlToText(b.html)} onChange={(e) => update(i, { ...b, html: textToHtml(e.target.value) })} />
          ) : b.type === "button" ? (
            <div className="app-formgrid">
              <Input label="Button label" value={b.label} onChange={(e) => update(i, { ...b, label: e.target.value })} />
              <Input label="Link" value={b.url} onChange={(e) => update(i, { ...b, url: e.target.value })} />
            </div>
          ) : b.type === "image" ? (
            <p className="body-sm app-muted" style={{ margin: 0 }}>{String(b.alt || "An image")}. Images are kept as they are.</p>
          ) : (
            <p className="body-sm app-muted" style={{ margin: 0 }}>A thin line between sections.</p>
          )}
        </div>
      ))}
      {error ? <p className="wo-error" style={{ margin: 0 }}><span aria-hidden="true">!</span>{error}</p> : null}
      <div className="app-cluster">
        {(["heading", "paragraph", "button", "divider"] as const).map((t) => (
          <Button key={t} size="sm" variant="secondary" onClick={() => onChange([...blocks, blankBlock(t)])}>Add {LABELS[t]?.toLowerCase()}</Button>
        ))}
      </div>
    </div>
  );
}
