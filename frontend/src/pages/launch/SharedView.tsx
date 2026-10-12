import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { API_BASE } from "../../api/client";
import type { components } from "../../api/schema";
import { Badge, Button, Card, Input } from "../../components";
import { RichText, useDocumentTitle } from "../../ui/blocks";
import { Logo } from "../../components/Logo";

type Content = components["schemas"]["TkSharedContent"];
type State = { kind: "loading" } | { kind: "password" } | { kind: "missing" } | { kind: "ready"; content: Content };

const text = (v: unknown) => (typeof v === "string" ? v : "");
const list = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

function Body({ content }: { content: Content }) {
  if (content.type === "score_summary") {
    return (
      <div className="app-stack">
        <Card variant="brand">
          <p className="eyebrow" style={{ margin: 0 }}>Overall</p>
          <p className="display-sm" style={{ margin: "var(--space-2) 0" }}>{content.overall_score == null ? "Not enough information" : `${Math.round(content.overall_score)} / 100`}</p>
          <p className="body" style={{ margin: 0 }}>{content.verdict}</p>
        </Card>
        <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {(content.dimensions ?? []).map((d, i) => (
            <li key={i}><Card><div className="app-cluster" style={{ justifyContent: "space-between" }}><strong>{text(d.label)}</strong>{typeof d.score === "number" ? <Badge variant="neutral">{Math.round(d.score)} / 100</Badge> : <Badge variant="warning">Need more information</Badge>}</div></Card></li>
          ))}
        </ul>
        {content.disclaimer ? <p className="caption app-muted">{content.disclaimer}</p> : null}
      </div>
    );
  }
  if (content.type === "plan_summary") {
    return (
      <div className="app-stack">
        {(content.sections ?? []).map((s, i) => (
          <Card key={i}><h2 className="h4" style={{ margin: "0 0 var(--space-2)" }}>{text(s.title)}</h2><RichText html={text(s.html) || text(s.body)} /></Card>
        ))}
      </div>
    );
  }
  if (content.type === "deck") {
    return (
      <ol className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {(content.slides ?? []).map((s, i) => (
          <li key={i}>
            <Card>
              <p className="caption app-faint" style={{ margin: 0 }}>Slide {i + 1}</p>
              <h2 className="h3" style={{ margin: "var(--space-1) 0 var(--space-3)" }}>{text(s.title) || text(s.headline)}</h2>
              {list(s.bullets).length > 0 ? <ul>{list(s.bullets).map((b, j) => <li key={j}>{b}</li>)}</ul> : null}
              {text(s.body) ? <p className="body">{text(s.body)}</p> : null}
            </Card>
          </li>
        ))}
      </ol>
    );
  }
  return (
    <Card>
      <p className="body" style={{ margin: 0 }}>This prototype is shared as a read-only preview. Open it from the member who shared it to click through.</p>
    </Card>
  );
}

export default function SharedView() {
  const { token = "" } = useParams();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [password, setPassword] = useState("");
  const [wrong, setWrong] = useState(false);
  const [busy, setBusy] = useState(false);
  useDocumentTitle(state.kind === "ready" ? state.content.title : "Shared with you");

  const url = `${API_BASE}/api/v1/toolkit/public/share/${encodeURIComponent(token)}`;
  const read = async (response: Response, fromPassword: boolean) => {
    if (response.ok) return setState({ kind: "ready", content: (await response.json()) as Content });
    if (response.status === 401) return setState({ kind: "password" });
    if (fromPassword) setWrong(true);
    setState(fromPassword ? { kind: "password" } : { kind: "missing" });
  };

  useEffect(() => {
    const controller = new AbortController();
    fetch(url, { signal: controller.signal }).then((r) => read(r, false)).catch(() => { if (!controller.signal.aborted) setState({ kind: "missing" }); });
    return () => controller.abort();
  }, [url]);

  const submit = async () => {
    setBusy(true);
    setWrong(false);
    try {
      const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
      await read(response, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main style={{ maxWidth: 820, margin: "0 auto", padding: "var(--space-8) var(--space-4)" }}>
      <meta name="robots" content="noindex" />
      <div style={{ marginBottom: "var(--space-6)" }}><Logo /></div>
      {state.kind === "loading" ? <p className="body app-muted" role="status">Opening…</p> : null}
      {state.kind === "missing" ? (
        <Card><h1 className="h2" style={{ margin: "0 0 var(--space-2)" }}>This link is not available</h1><p className="body" style={{ margin: 0 }}>It may have expired or been turned off by the person who shared it.</p></Card>
      ) : null}
      {state.kind === "password" ? (
        <Card>
          <h1 className="h2" style={{ margin: "0 0 var(--space-2)" }}>This is protected</h1>
          <form className="app-stack" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
            <Input label="Password" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} error={wrong ? "That did not open it. Check the password and try again." : undefined} />
            <div><Button type="submit" loading={busy} disabled={!password}>Open</Button></div>
          </form>
        </Card>
      ) : null}
      {state.kind === "ready" ? (
        <>
          <header style={{ marginBottom: "var(--space-6)" }}>
            {state.content.venture_name ? <p className="eyebrow" style={{ margin: 0 }}>{state.content.venture_name}</p> : null}
            <h1 className="h1" style={{ margin: "var(--space-1) 0 0" }}>{state.content.title}</h1>
          </header>
          <Body content={state.content} />
        </>
      ) : null}
    </main>
  );
}
