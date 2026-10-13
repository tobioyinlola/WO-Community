import * as Dialog from "@radix-ui/react-dialog";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Check, Copy, Download, X } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { API_BASE, api, authFetch, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Button, Input, Select } from "../components";
import { formatDateTime, humanise, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, Skeleton, useDocumentTitle } from "../ui/blocks";
import { StatusChip } from "./kit/TableBits";

type Entry = components["schemas"]["AuditEntry"];

const GROUPS = [
  { value: "members", label: "Members" },
  { value: "content", label: "Content" },
  { value: "jobs", label: "Jobs" },
  { value: "events", label: "Events" },
  { value: "courses", label: "Courses" },
  { value: "certificates", label: "Certificates" },
  { value: "settings", label: "Settings" },
  { value: "security", label: "Security" },
];
const PRESETS = [
  { value: "", label: "Any time" },
  { value: "today", label: "Today" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "custom", label: "Choose dates" },
];

const day = (d: Date) => d.toISOString().slice(0, 10);
const daysAgo = (n: number) => day(new Date(Date.now() - n * 86_400_000));

/** The date range the address asks for: a preset, or two dates typed in. */
function range(params: URLSearchParams): { date_from?: string; date_to?: string } {
  const preset = params.get("when") ?? "";
  if (preset === "today") return { date_from: day(new Date()), date_to: day(new Date()) };
  if (preset === "7" || preset === "30") return { date_from: daysAgo(Number(preset)), date_to: day(new Date()) };
  if (preset === "custom") {
    const from = params.get("from");
    const to = params.get("to");
    return { ...(from ? { date_from: from } : {}), ...(to ? { date_to: to } : {}) };
  }
  return {};
}

function Diff({ entry }: { entry: Entry }) {
  if (entry.changes.length === 0) return <p className="body-sm app-muted" style={{ margin: 0 }}>No field changes were recorded for this action.</p>;
  const show = (v: unknown) => (v === null || v === undefined || v === "" ? "empty" : typeof v === "object" ? JSON.stringify(v) : String(v));
  return (
    <table className="adm-difftable">
      <caption className="wo-visually-hidden">What changed</caption>
      <thead>
        <tr><th scope="col">Field</th><th scope="col">Before</th><th scope="col">After</th></tr>
      </thead>
      <tbody>
        {entry.changes.map((c) => (
          <tr key={c.field}>
            <th scope="row">{humanise(c.field)}</th>
            <td className="adm-difftable__old">{show(c.before)}</td>
            <td className="adm-difftable__new">{show(c.after)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Where the target of an entry lives in the console, when it still can be opened. */
function targetLink(entry: Entry): string | null {
  const { type, id } = entry.target;
  if (!id) return null;
  if (type === "user") return `/admin/members/${id}`;
  return null;
}

function EntryDrawer({ entry, onClose }: { entry: Entry; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const detail = useQuery({
    queryKey: ["admin", "audit", "entry", entry.id],
    queryFn: () => unwrap(api.GET("/api/v1/admin/audit/{entry_id}", { params: { path: { entry_id: entry.id } } })),
  });
  const full = detail.data;
  const raw = JSON.stringify(full ?? entry, null, 2);
  const link = targetLink(entry);
  const rows: Array<[string, React.ReactNode]> = [
    ["Time", <time key="t" dateTime={entry.created_at}>{formatDateTime(entry.created_at)}</time>],
    ["Who", `${entry.actor.name}${entry.actor.email && entry.actor.email !== entry.actor.name ? ` · ${entry.actor.email}` : ""}`],
    ["Role", entry.actor.roles.length ? entry.actor.roles.map(humanise).join(", ") : "None"],
    ["Action", <code key="a">{entry.action}</code>],
    ["Target", link ? <Link key="l" to={link}>{entry.target.title || entry.target.id}</Link> : entry.target.title || "None"],
    ["Result", entry.outcome === "failure" ? "Failed" : "Succeeded"],
    ["Reason given", entry.reason || "None"],
    ["Network reference", entry.ip_ref || "Not recorded"],
    ["Request", entry.request_id ? <code key="r">{entry.request_id}</code> : "Not recorded"],
  ];
  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="adm-scrim adm-scrim--blur" />
        <Dialog.Content className="adm-sheet" aria-describedby={undefined}>
          <header className="adm-sheet__head">
            <div className="adm-sheet__meta"><span className="adm-sheet__label">Audit entry</span></div>
            <Dialog.Close className="adm-iconbtn adm-iconbtn--ring" aria-label="Close"><X size={18} strokeWidth={1.5} aria-hidden="true" /></Dialog.Close>
          </header>
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
          <div className="adm-sheet__body" tabIndex={0} role="region" aria-label="Entry details">
            <div>
              <Dialog.Title className="adm-sheet__title">{humanise(entry.action.replace(/\./g, " "))}</Dialog.Title>
              <p className="adm-sheet__chips"><StatusChip tone={entry.outcome === "failure" ? "danger" : "success"}>{entry.outcome === "failure" ? "Failed" : "Succeeded"}</StatusChip></p>
            </div>
            <dl className="adm-kv">
              {rows.map(([k, v]) => (<div key={k} className="adm-kv__row"><dt>{k}</dt><dd>{v}</dd></div>))}
            </dl>
            <section aria-labelledby="audit-diff">
              <h3 className="adm-sheet__h" id="audit-diff">What changed</h3>
              {detail.isPending ? <Skeleton height={60} /> : <Diff entry={full ?? entry} />}
            </section>
            <details>
              <summary>Raw record</summary>
              <div style={{ marginTop: "var(--space-2)" }}>
                <Button
                  size="sm"
                  variant="secondary"
                  icon={copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
                  onClick={() => { void navigator.clipboard?.writeText(raw); setCopied(true); }}
                >
                  {copied ? "Copied" : "Copy JSON"}
                </Button>
                {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
                <pre className="adm-raw" tabIndex={0}>{raw}</pre>
              </div>
            </details>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function AuditLog() {
  useDocumentTitle("Audit log");
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState<Entry | null>(null);
  const get = (k: string) => params.get(k) ?? "";
  const set = (k: string, v: string) =>
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (v) next.set(k, v);
      else next.delete(k);
      return next;
    }, { replace: true });

  const groups = get("group");
  const filters = {
    ...range(params),
    ...(get("actor") ? { actor: get("actor") } : {}),
    ...(groups ? { group: groups } : {}),
    ...(get("outcome") ? { outcome: get("outcome") as "success" | "failure" } : {}),
    ...(get("q") ? { q: get("q") } : {}),
    ...(get("target_type") ? { target_type: get("target_type") } : {}),
    ...(get("target_id") ? { target_id: get("target_id") } : {}),
  };
  const key = params.toString();

  const list = useInfiniteQuery({
    queryKey: ["admin", "audit", key],
    initialPageParam: "",
    queryFn: ({ pageParam }) => unwrap(api.GET("/api/v1/admin/audit", { params: { query: { ...filters, ...(pageParam ? { cursor: pageParam } : {}) } } })),
    getNextPageParam: (last) => (last.next ? (new URL(last.next, window.location.origin).searchParams.get("cursor") ?? undefined) : undefined),
  });
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  const filtered = [...params.keys()].some((k) => k !== "");
  const exportHref = `/api/v1/admin/audit/export?${new URLSearchParams(Object.entries(filters).map(([k, v]) => [k, String(v)])).toString()}`;
  const toggleGroup = (value: string) => {
    const now = new Set(groups.split(",").filter(Boolean));
    if (now.has(value)) now.delete(value);
    else now.add(value);
    set("group", [...now].join(","));
  };

  const [exportError, setExportError] = useState(false);
  const download = async () => {
    setExportError(false);
    const response = await authFetch(new Request(new URL(API_BASE + exportHref, window.location.origin)));
    if (!response.ok) {
      setExportError(true);
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = "audit-log.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <PageHeader
        eyebrow="Security"
        title="Audit log"
        lead="Every sensitive action, who did it and what changed. Entries cannot be edited or deleted. The log starts on the day it was switched on; earlier actions are not listed."
        actions={<Button variant="secondary" icon={<Download size={16} strokeWidth={1.5} aria-hidden="true" />} onClick={() => void download()}>Export CSV</Button>}
      />
      {exportError ? <p role="alert" className="app-error">The export could not be made. Try again, or narrow the dates.</p> : null}

      <form className="adm-filterbar" role="search" aria-label="Filter the audit log" onSubmit={(e) => e.preventDefault()}>
        <Input label="Search" placeholder="Target or action" value={get("q")} onChange={(e) => set("q", e.target.value)} />
        <Input label="Who did it" placeholder="Name or email" value={get("actor")} onChange={(e) => set("actor", e.target.value)} />
        <Select label="When" value={get("when")} onChange={(e) => set("when", e.target.value)} options={PRESETS} />
        {get("when") === "custom" ? (
          <>
            <Input label="From" type="date" value={get("from")} onChange={(e) => set("from", e.target.value)} />
            <Input label="To" type="date" value={get("to")} onChange={(e) => set("to", e.target.value)} />
          </>
        ) : null}
        <Select label="Result" value={get("outcome")} onChange={(e) => set("outcome", e.target.value)} options={[{ value: "", label: "Any" }, { value: "success", label: "Succeeded" }, { value: "failure", label: "Failed" }]} />
        <fieldset className="adm-checkset">
          <legend>Area</legend>
          {GROUPS.map((g) => (
            <label key={g.value} className="adm-checkset__item">
              <input type="checkbox" checked={groups.split(",").includes(g.value)} onChange={() => toggleGroup(g.value)} /> {g.label}
            </label>
          ))}
        </fieldset>
        {filtered ? <Button variant="ghost" onClick={() => setParams({}, { replace: true })}>Clear filters</Button> : null}
      </form>

      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : list.isPending ? (
        <Skeleton height={240} />
      ) : rows.length === 0 ? (
        <EmptyState title={filtered ? "No entries match these filters" : "Nothing recorded yet"}>{filtered ? "Try a wider date range or fewer filters." : "Actions will appear here as they happen."}</EmptyState>
      ) : (
        <div className="adm-tablewrap">
          <table className="adm-table">
            <caption className="wo-visually-hidden">Audit log, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Time</th><th scope="col">Who</th><th scope="col">Action</th><th scope="col">Target</th><th scope="col">Result</th><th scope="col">Network</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id} className="adm-row--click" onClick={() => setOpen(e)}>
                  <td><time dateTime={e.created_at} title={formatDateTime(e.created_at)}>{timeAgo(e.created_at)}</time></td>
                  <td>{e.actor.name}{e.actor.email && e.actor.email !== e.actor.name ? <span className="app-faint"> · {e.actor.email}</span> : null}</td>
                  <td>
                    <button type="button" className="wo-linkbtn" onClick={() => setOpen(e)} aria-label={`Open entry: ${e.action}`}>{e.action}</button>
                  </td>
                  <td>{e.target.title || "None"}</td>
                  <td><StatusChip tone={e.outcome === "failure" ? "danger" : "success"}>{e.outcome === "failure" ? "Failed" : "Succeeded"}</StatusChip></td>
                  <td><code>{e.ip_ref || "-"}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <LoadMore hasNext={Boolean(list.hasNextPage)} loading={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()} />
      {open ? <EntryDrawer entry={open} onClose={() => setOpen(null)} /> : null}
    </>
  );
}
