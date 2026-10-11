import { TableScroll } from "../../ui/blocks";
import type { ReactNode } from "react";
import { Badge } from "../../components";

export interface ProtoNode {
  id: string;
  component: string;
  props: Record<string, unknown>;
  children: ProtoNode[];
  action?: { type: "navigate" | "back" | "none"; screen?: string };
}
export interface ProtoScreen { id: string; name: string; root: ProtoNode }
export interface ProtoSpec { kind: "web" | "mobile"; start: string; screens: ProtoScreen[] }

const text = (v: unknown) => (typeof v === "string" ? v : "");
const list = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
const gap = (v: unknown) => (v === "lg" ? "var(--space-6)" : v === "sm" ? "var(--space-2)" : "var(--space-4)");
const align = (v: unknown) => (v === "center" ? "center" : v === "end" ? "flex-end" : "flex-start");
const toneBadge = (v: unknown) => (v === "success" || v === "warning" || v === "danger" ? v : v === "primary" ? "info" : "neutral");

/** Draws a prototype node from its name and props. Only the registered components exist, so nothing here reads markup. */
export function Node({ node, go, back }: { node: ProtoNode; go: (screen: string) => void; back: () => void }): ReactNode {
  const p = node.props;
  const kids = node.children.map((c) => <Node key={c.id} node={c} go={go} back={back} />);
  const act = () => {
    if (node.action?.type === "navigate" && node.action.screen) go(node.action.screen);
    else if (node.action?.type === "back") back();
  };
  const clickable = Boolean(node.action && node.action.type !== "none");
  switch (node.component) {
    case "container":
      return <div style={{ padding: gap(p.padding) }}>{kids}</div>;
    case "row":
      return <div style={{ display: "flex", flexWrap: "wrap", gap: gap(p.gap), alignItems: "center", justifyContent: align(p.align) }}>{kids}</div>;
    case "column":
      return <div style={{ display: "flex", flexDirection: "column", gap: gap(p.gap), alignItems: align(p.align) }}>{kids}</div>;
    case "grid":
      return <div style={{ display: "grid", gap: gap(p.gap), gridTemplateColumns: `repeat(${Math.min(Number(p.columns) || 2, 4)}, minmax(0, 1fr))` }}>{kids}</div>;
    case "card":
      return (
        <div className="app-proto-card" onClick={clickable ? act : undefined} role={clickable ? "button" : undefined} tabIndex={clickable ? 0 : undefined} onKeyDown={clickable ? (e) => { if (e.key === "Enter") act(); } : undefined}>
          {text(p.title) ? <strong>{text(p.title)}</strong> : null}
          {kids}
        </div>
      );
    case "divider":
      return <hr className="app-rule" />;
    case "spacer":
      return <div style={{ height: gap(p.size) }} aria-hidden="true" />;
    case "scroll":
    case "modal":
    case "navbar":
      return (
        <div className={node.component === "navbar" ? "app-proto-bar" : undefined}>
          {text(p.title) ? <strong>{text(p.title)}</strong> : null}
          {node.component === "navbar" ? list(p.items).map((i) => <span key={i} className="body-sm">{i}</span>) : null}
          {kids}
        </div>
      );
    case "tabs":
    case "tab_bar":
      return <div className="app-cluster">{list(p.labels).map((l, i) => <span key={l} className={i === 0 ? "app-proto-tab app-proto-tab--on" : "app-proto-tab"}>{l}</span>)}{kids}</div>;
    case "heading": {
      const level = Number(p.level) || 2;
      return <p className={level <= 1 ? "h2" : level === 2 ? "h3" : "h4"} style={{ margin: 0, textAlign: p.align === "center" ? "center" : p.align === "end" ? "right" : "left" }}>{text(p.text)}</p>;
    }
    case "text":
      return <p className="body" style={{ margin: 0, textAlign: p.align === "center" ? "center" : p.align === "end" ? "right" : "left" }}>{text(p.text)}</p>;
    case "label":
      return <span className="caption app-muted">{text(p.text)}</span>;
    case "badge":
      return <Badge variant={toneBadge(p.tone) as "neutral"}>{text(p.text)}</Badge>;
    case "quote":
      return <blockquote style={{ margin: 0 }}>{text(p.text)}{text(p.author) ? <footer className="caption app-muted">{text(p.author)}</footer> : null}</blockquote>;
    case "list": {
      const Tag = p.ordered ? "ol" : "ul";
      return <Tag style={{ margin: 0 }}>{list(p.items).map((i) => <li key={i}>{i}</li>)}</Tag>;
    }
    case "list_item":
      return <div className="app-proto-card" onClick={clickable ? act : undefined} role={clickable ? "button" : undefined} tabIndex={clickable ? 0 : undefined} onKeyDown={clickable ? (e) => { if (e.key === "Enter") act(); } : undefined}><strong>{text(p.title)}</strong>{text(p.subtitle) ? <span className="body-sm app-muted"> {text(p.subtitle)}</span> : null}</div>;
    case "button":
    case "link":
    case "icon_button":
    case "fab":
      return (
        <button type="button" className={node.component === "link" ? "app-linklike" : `wo-btn wo-btn--${p.tone === "primary" || p.tone === undefined ? "primary" : "secondary"} wo-btn--${p.size === "lg" ? "lg" : p.size === "sm" ? "sm" : "md"}`} onClick={act}>
          {text(p.text) || text(p.label) || text(p.icon)}
        </button>
      );
    case "text_input": case "email_input": case "password_input": case "number_input": case "search": case "date_picker":
      return <label className="wo-field"><span className="wo-label">{text(p.label) || text(p.placeholder) || "Field"}</span><input className="wo-input" readOnly placeholder={text(p.placeholder)} type="text" tabIndex={-1} /></label>;
    case "textarea":
      return <label className="wo-field"><span className="wo-label">{text(p.label)}</span><textarea className="wo-input" readOnly rows={3} placeholder={text(p.placeholder)} tabIndex={-1} /></label>;
    case "select":
    case "radio_group":
      return <div><span className="wo-label">{text(p.label)}</span><ul className="body-sm" style={{ margin: 0 }}>{list(p.options).map((o) => <li key={o}>{o}</li>)}</ul></div>;
    case "checkbox":
    case "toggle":
      return <label className="wo-check"><input type="checkbox" readOnly checked={Boolean(p.checked ?? p.on)} tabIndex={-1} />{text(p.label)}</label>;
    case "table":
      return (
        <TableScroll label="Table">
          <table className="app-table">
            <thead><tr>{list(p.columns).map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
            <tbody>{((p.rows as string[][]) ?? []).map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
          </table>
        </TableScroll>
      );
    case "stat":
      return <div><p className="caption app-muted" style={{ margin: 0 }}>{text(p.label)}</p><p className="h3" style={{ margin: 0 }}>{text(p.value)}</p>{text(p.change) ? <p className="caption" style={{ margin: 0 }}>{text(p.change)}</p> : null}</div>;
    case "chart_bar":
    case "chart_line": {
      const values = Array.isArray(p.values) ? (p.values as number[]) : [];
      const max = Math.max(...values, 1);
      return (
        <figure style={{ margin: 0 }}>
          {text(p.title) ? <figcaption className="body-sm app-muted">{text(p.title)}</figcaption> : null}
          <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 80 }} role="img" aria-label={`${text(p.title) || "Chart"}: ${values.join(", ")}`}>
            {values.map((v, i) => <span key={i} style={{ flex: 1, height: `${(v / max) * 100}%`, background: "var(--accent-fill)", borderRadius: "var(--radius-sm)" }} />)}
          </div>
        </figure>
      );
    }
    case "progress":
      return <div><span className="caption">{text(p.label)}</span><div className="app-meter"><span style={{ width: `${Number(p.value) || 0}%` }} /></div></div>;
    case "avatar":
      return <span className="wo-avatar" aria-label={text(p.name)}>{text(p.name).slice(0, 2).toUpperCase()}</span>;
    case "rating":
      return <span aria-label={`${p.value} out of 5`}>{"★".repeat(Number(p.value) || 0)}{"☆".repeat(5 - (Number(p.value) || 0))}</span>;
    case "timeline":
      return <ol style={{ margin: 0 }}>{list(p.items).map((i) => <li key={i}>{i}</li>)}</ol>;
    case "sidebar":
      return <ul style={{ margin: 0 }}>{list(p.items).map((i) => <li key={i}>{i}</li>)}</ul>;
    default:
      return <div className="app-proto-card caption app-muted">{text(p.label) || node.component.replace("_", " ")}</div>;
  }
}
