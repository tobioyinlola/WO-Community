import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Alert, Badge, Button, Input, Textarea } from "../components";
import { formatDateTime, humanise, timeAgo } from "../lib/format";
import { ErrorState, PageHeader, Skeleton, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { ConfirmDialog } from "./dialogs";

type Summary = components["schemas"]["MailTemplateSummary"];
type Template = components["schemas"]["MailTemplate"];
type Version = components["schemas"]["Version"];

function Preview({ keyName, subject, preheader, body, mobile }: { keyName: string; subject: string; preheader: string; body: string; mobile: boolean }) {
  const [debounced, setDebounced] = useState({ subject, preheader, body });
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced({ subject, preheader, body }), 400);
    return () => window.clearTimeout(id);
  }, [subject, preheader, body]);
  const preview = useQuery({
    queryKey: ["admin", "email-template", keyName, "preview", debounced],
    queryFn: async () => {
      const response = await api.POST("/api/v1/admin/email-templates/{key}/preview", { params: { path: { key: keyName } }, body: debounced });
      if (response.error || !response.data) return { error: (errorsFrom(response.error).fields.body ?? errorsFrom(response.error).general) || "This wording cannot be previewed.", subject: "", html: "", text: "", preheader: "" };
      return { ...response.data, error: "" };
    },
    placeholderData: (previous) => previous,
  });
  const data = preview.data;
  return (
    <div className="app-stack">
      {data?.error ? <Alert tone="danger" title="This wording has a problem">{data.error}</Alert> : null}
      {data && !data.error ? (
        <>
          <p className="body-sm" style={{ margin: 0 }}><strong>Subject:</strong> {data.subject}</p>
          <p className="body-sm app-muted" style={{ margin: 0 }}><strong>Preview text:</strong> {data.preheader || "none"}</p>
          <iframe
            title={mobile ? "Preview at phone width" : "Preview at desktop width"}
            sandbox=""
            srcDoc={data.html}
            style={{ width: mobile ? 375 : "100%", maxWidth: "100%", height: 560, border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", background: "var(--bg-surface)", margin: mobile ? "0 auto" : 0 }}
          />
          <details>
            <summary>Plain text version</summary>
            {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
            <pre className="adm-raw" tabIndex={0}>{data.text}</pre>
          </details>
        </>
      ) : preview.isPending ? <Skeleton height={300} /> : null}
    </div>
  );
}

function Editor({ summary, onBack }: { summary: Summary; onBack: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const [mobile, setMobile] = useState(false);
  const [confirm, setConfirm] = useState<"reset" | null>(null);
  const detail = useQuery({
    queryKey: ["admin", "email-template", summary.key],
    queryFn: () => unwrap(api.GET("/api/v1/admin/email-templates/{key}", { params: { path: { key: summary.key } } })),
  });
  const versions = useQuery({
    queryKey: ["admin", "email-template", summary.key, "versions"],
    queryFn: () => unwrap(api.GET("/api/v1/admin/email-templates/{key}/versions", { params: { path: { key: summary.key } } })),
  });
  const [draft, setDraft] = useState<{ subject: string; preheader: string; body: string } | null>(null);
  const [loaded, setLoaded] = useState("");
  const t: Template | undefined = detail.data;
  if (t && loaded !== `${t.key}:${t.version}`) {
    setLoaded(`${t.key}:${t.version}`);
    setDraft({ subject: t.subject, preheader: t.preheader, body: t.body });
  }
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["admin", "email-templates"] });
    await client.invalidateQueries({ queryKey: ["admin", "email-template", summary.key] });
  };
  const save = useSubmit(async () => {
    if (!draft) return;
    await unwrap(api.PUT("/api/v1/admin/email-templates/{key}", { params: { path: { key: summary.key } }, body: { ...draft, note: "" } }));
    toast.show("Wording saved");
    await refresh();
  });
  const test = useSubmit(async () => {
    if (!draft) return;
    await unwrap(api.POST("/api/v1/admin/email-templates/{key}/test", { params: { path: { key: summary.key } }, body: draft }));
    toast.show("A test email is on its way to you");
  });
  const restore = async (v: Version) => {
    await unwrap(api.POST("/api/v1/admin/email-templates/{key}/restore", { params: { path: { key: summary.key } }, body: { version: v.version } }));
    toast.show(`Version ${v.version} restored`);
    await refresh();
  };
  const reset = async () => {
    await unwrap(api.POST("/api/v1/admin/email-templates/{key}/reset", { params: { path: { key: summary.key } } }));
    toast.show("Back to the built in wording");
    await refresh();
  };

  if (detail.isPending) return <Skeleton height={300} />;
  if (detail.isError || !t || !draft) return <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />;
  const changed = draft.subject !== t.subject || draft.preheader !== t.preheader || draft.body !== t.body;
  const fieldErrors = errorsFrom(save.error).fields;

  return (
    <>
      <PageHeader
        eyebrow="Email templates"
        title={t.name}
        lead={t.about}
        actions={<Button variant="ghost" onClick={onBack}>All templates</Button>}
      />
      <div className="app-split">
        <div className="app-stack">
          <FormError error={save.error} listFields />
          <Alert tone="info" title="Only the words are editable">
            The layout, logo, colours and the sign off are fixed. Write paragraphs separated by a blank line. Use **bold**, [a link](https://example.com), lines starting with "- " for a list, and one [button: Label | {"{{"}link{"}}"}].
          </Alert>
          <Input label="Subject" value={draft.subject} maxLength={200} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} error={fieldErrors.subject} />
          <Input label="Preview text" hint="The grey line shown beside the subject in an inbox." value={draft.preheader} maxLength={200} onChange={(e) => setDraft({ ...draft, preheader: e.target.value })} />
          <Textarea label="Body" rows={12} value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} error={fieldErrors.body} />
          <div>
            <p className="wo-label" style={{ margin: "0 0 var(--space-2)" }}>Details you can put in</p>
            <ul className="app-cluster" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {t.variables.map((v) => (
                <li key={v.name}>
                  <button
                    type="button"
                    className="adm-chip"
                    title={`${v.is_required ? "Always filled in" : "Optional; a paragraph using it is left out when empty"}${v.must_appear ? ". Keep it in the body." : ""}`}
                    onClick={() => setDraft({ ...draft, body: `${draft.body}{{${v.name}}}` })}
                  >
                    {`{{${v.name}}}`} {v.must_appear ? "(keep)" : ""}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="app-cluster">
            <Button loading={save.busy} disabled={!changed} onClick={() => void save.run()}>Save wording</Button>
            <Button variant="secondary" loading={test.busy} onClick={() => void test.run()}>Send me a test</Button>
            <Button variant="ghost" disabled={draft.subject === t.default_subject && draft.preheader === t.default_preheader && draft.body === t.default_body && !t.edited} onClick={() => setConfirm("reset")}>Reset to default</Button>
          </div>
          <section aria-labelledby="versions-title">
            <h2 className="h4" id="versions-title">History</h2>
            {versions.data && versions.data.length > 0 ? (
              <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {versions.data.map((v) => (
                  <li key={v.version} className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <span className="body-sm">Version {v.version} · <time dateTime={v.created_at} title={formatDateTime(v.created_at)}>{timeAgo(v.created_at)}</time>{v.note ? ` · ${v.note}` : ""}{v.version === t.version ? " (current)" : ""}</span>
                    {v.version !== t.version ? <Button size="sm" variant="secondary" onClick={() => void restore(v)}>Restore</Button> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="body-sm app-muted" style={{ margin: 0 }}>Nothing has been changed yet. This is the built in wording.</p>
            )}
          </section>
        </div>
        <div className="app-stack">
          <div className="app-cluster" role="group" aria-label="Preview size">
            <Button size="sm" variant={mobile ? "secondary" : "primary"} aria-pressed={!mobile} onClick={() => setMobile(false)}>Desktop</Button>
            <Button size="sm" variant={mobile ? "primary" : "secondary"} aria-pressed={mobile} onClick={() => setMobile(true)}>Phone</Button>
          </div>
          <Preview keyName={summary.key} subject={draft.subject} preheader={draft.preheader} body={draft.body} mobile={mobile} />
        </div>
      </div>
      {confirm === "reset" ? (
        <ConfirmDialog title="Go back to the built in wording?" body="Your edits stay in the history, so you can restore them later." confirmLabel="Reset" onConfirm={reset} onClose={() => setConfirm(null)} />
      ) : null}
    </>
  );
}

export default function EmailTemplates() {
  useDocumentTitle("Email templates");
  const [params, setParams] = useSearchParams();
  const list = useQuery({ queryKey: ["admin", "email-templates"], queryFn: () => unwrap(api.GET("/api/v1/admin/email-templates")) });
  const open = list.data?.find((t) => t.key === params.get("t"));
  if (open) return <Editor summary={open} onBack={() => setParams({}, { replace: true })} />;
  return (
    <>
      <PageHeader eyebrow="Email" title="Email templates" lead="The wording of every email the platform sends. The layout and brand are fixed; only the words change, and every change is kept in a history." />
      {list.isError ? <ErrorState error={list.error} onRetry={() => void list.refetch()} /> : list.isPending ? <Skeleton height={300} /> : (
        <div className="adm-tablewrap">
          <table className="adm-table">
            <caption className="wo-visually-hidden">Email templates</caption>
            <thead><tr><th scope="col">Template</th><th scope="col">Sent</th><th scope="col">Subject</th><th scope="col">State</th></tr></thead>
            <tbody>
              {list.data.map((t) => (
                <tr key={t.key} className="adm-row--click" onClick={() => setParams({ t: t.key })}>
                  <td><button type="button" className="wo-linkbtn" onClick={(e) => { e.stopPropagation(); setParams({ t: t.key }); }}>{t.name}</button></td>
                  <td>{t.stream === "broadcast" ? "To everyone who opted in" : humanise(t.stream)}</td>
                  <td>{t.subject}</td>
                  <td>{t.edited ? <Badge variant="info" dot>Edited{t.updated_at ? ` ${timeAgo(t.updated_at)}` : ""}</Badge> : <Badge variant="neutral">Built in</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
