import type { ReactNode } from "react";

/**
 * Draws a policy written in a small subset of Markdown: "## " headings, paragraphs, "- " and "1. "
 * lists, pipe tables, **bold** and *italic*. Everything becomes React elements, so the text can never
 * inject markup.
 */
type Block =
  | { kind: "heading"; text: string; id: string }
  | { kind: "paragraph"; text: string }
  | { kind: "bullets"; items: string[] }
  | { kind: "numbers"; items: string[] }
  | { kind: "table"; head: string[]; rows: string[][] };

export const slug = (text: string) =>
  "s-" + text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

const cells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export function parse(source: string): Block[] {
  const blocks: Block[] = [];
  const lines = source.replace(/\r/g, "").split("\n");
  const at = (k: number) => lines[k] ?? "";
  let i = 0;
  while (i < lines.length) {
    const line = at(i);
    if (!line.trim()) {
      i++;
    } else if (line.startsWith("## ")) {
      const text = line.slice(3).trim();
      blocks.push({ kind: "heading", text, id: slug(text) });
      i++;
    } else if (line.startsWith("|")) {
      const rows: string[][] = [];
      for (; i < lines.length && at(i).startsWith("|"); i++) {
        if (!/^\|[\s|:-]+\|?$/.test(at(i).trim())) rows.push(cells(at(i)));
      }
      blocks.push({ kind: "table", head: rows[0] ?? [], rows: rows.slice(1) });
    } else if (/^- /.test(line)) {
      const items: string[] = [];
      for (; i < lines.length && /^- /.test(at(i)); i++) items.push(at(i).slice(2).trim());
      blocks.push({ kind: "bullets", items });
    } else if (/^\d+\. /.test(line)) {
      const items: string[] = [];
      for (; i < lines.length && /^\d+\. /.test(at(i)); i++) items.push(at(i).replace(/^\d+\. /, "").trim());
      blocks.push({ kind: "numbers", items });
    } else {
      const text: string[] = [];
      for (; i < lines.length && at(i).trim() && !/^(## |\||- |\d+\. )/.test(at(i)); i++) text.push(at(i).trim());
      blocks.push({ kind: "paragraph", text: text.join(" ") });
    }
  }
  return blocks;
}

/** **bold** and *italic* inside a line of text. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={i}>{part.slice(1, -1)}</em>;
    return part;
  });
}

export function LegalText({ source }: { source: string }) {
  return (
    <div className="wo-legal__body">
      {parse(source).map((block, i) => {
        switch (block.kind) {
          case "heading":
            return <h2 key={i} id={block.id} className="wo-legal__h">{block.text}</h2>;
          case "paragraph":
            return <p key={i}>{inline(block.text)}</p>;
          case "bullets":
            return <ul key={i}>{block.items.map((item, j) => <li key={j}>{inline(item)}</li>)}</ul>;
          case "numbers":
            return <ol key={i}>{block.items.map((item, j) => <li key={j}>{inline(item)}</li>)}</ol>;
          case "table":
            return (
              <div key={i} className="wo-legal__table">
                <table>
                  <thead><tr>{block.head.map((h, j) => <th key={j} scope="col">{inline(h)}</th>)}</tr></thead>
                  <tbody>{block.rows.map((row, j) => <tr key={j}>{row.map((c, k) => <td key={k} data-label={block.head[k]}>{inline(c)}</td>)}</tr>)}</tbody>
                </table>
              </div>
            );
        }
      })}
    </div>
  );
}
