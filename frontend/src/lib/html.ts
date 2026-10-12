const ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };

function escape(text: string): string {
  return text.replace(/[&<>"]/g, (char) => ESCAPES[char] ?? char);
}

/** Plain text a member typed, as the simple HTML the API stores: one paragraph per blank line. */
export function textToHtml(text: string): string {
  return text
    .trim()
    .split(/\n{2,}/)
    .map((block) => `<p>${escape(block).replace(/\n/g, "<br>")}</p>`)
    .join("");
}

/** The words of a piece of HTML, for editing it again as plain text. */
export function htmlToText(html: string): string {
  const doc = new DOMParser().parseFromString(html.replace(/<br\s*\/?>/gi, "\n"), "text/html");
  return Array.from(doc.body.querySelectorAll("p, li"))
    .map((node) => node.textContent ?? "")
    .join("\n\n")
    .trim() || (doc.body.textContent ?? "").trim();
}
