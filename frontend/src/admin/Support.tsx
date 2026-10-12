import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Avatar, Input, Select } from "../components";
import { formatDate, formatNumber, timeAgo } from "../lib/format";
import { ADMIN_STATUS_LABEL, CATEGORIES, PRIORITIES, STATUS_TONE } from "../support/constants";
import { EmptyState, ErrorState, PageHeader, useDocumentTitle } from "../ui/blocks";
import { DataTable, type ColumnMeta, type Sort } from "./kit/DataTable";
import { Segmented } from "./kit/Segmented";
import { Pager, StatStrip, StatusChip } from "./kit/TableBits";
import { isTyping } from "./shell/prefs";
import { TicketDrawer, useAgents } from "./TicketDrawer";

type Row = components["schemas"]["AdminTicketRow"];
type Person = components["schemas"]["SupportPerson"];
type Tab = "working" | "open" | "in_progress" | "awaiting_member" | "resolved" | "all";

const TABS: Array<{ value: Tab; label: string; count: (c: Counts) => number }> = [
  { value: "working", label: "All open", count: (c) => c.working },
  { value: "open", label: "New", count: (c) => c.open },
  { value: "in_progress", label: "In progress", count: (c) => c.in_progress },
  { value: "awaiting_member", label: "Awaiting member", count: (c) => c.awaiting_member },
  { value: "resolved", label: "Resolved", count: (c) => c.resolved },
  { value: "all", label: "All", count: (c) => c.total },
];
type Counts = components["schemas"]["Counts"];

const SORTS: Record<string, string> = { ticket: "number", created: "created_at", activity: "last_activity_at", status: "status", category: "category" };
const SIZES = [25, 50, 100];

function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "No replies yet";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${Math.max(1, minutes)} min`;
  const hours = Math.floor(minutes / 60);
  return hours < 48 ? `${hours} h ${minutes % 60} min` : `${Math.round(hours / 24)} days`;
}

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** The support inbox: what needs a reply, who has it, and the request open beside the list. */
export default function Support() {
  useDocumentTitle("Support inbox");
  const [params, setParams] = useSearchParams();
  const agents = useAgents();

  const tab = (TABS.some((t) => t.value === params.get("tab")) ? params.get("tab") : "working") as Tab;
  const size = SIZES.includes(Number(params.get("size"))) ? Number(params.get("size")) : 25;
  const page = Math.max(0, Number(params.get("page") ?? 0) || 0);
  const sortParam = params.get("sort") ?? "-activity";
  const sort: Sort = { id: sortParam.replace(/^-/, ""), desc: sortParam.startsWith("-") };
  const category = params.get("category") ?? "";
  const priority = params.get("priority") ?? "";
  const assignee = params.get("assignee") ?? "";
  const ticketId = params.get("ticket");
  const [typed, setTyped] = useState(params.get("q") ?? "");
  const q = useDebounced(typed.trim());
  const [cursor, setCursor] = useState<string | null>(null);

  const setParam = useCallback(
    (next: Record<string, string>, replace = true) =>
      setParams(
        (current) => {
          const merged = new URLSearchParams(current);
          for (const [k, v] of Object.entries(next)) {
            if (v) merged.set(k, v);
            else merged.delete(k);
          }
          return merged;
        },
        { replace },
      ),
    [setParams],
  );
  useEffect(() => {
    if ((params.get("q") ?? "") !== q) setParam({ q, page: "" });
  }, [q, params, setParam]);

  const ordering = `${sort.desc ? "-" : ""}${SORTS[sort.id] ?? "last_activity_at"}`;
  const list = useQuery({
    queryKey: ["admin", "support", "list", tab, q, category, priority, assignee, ordering, page, size],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/support/tickets", {
          params: {
            query: {
              limit: size,
              offset: page * size,
              ordering,
              ...(tab === "all" ? {} : { status: tab }),
              ...(q ? { q } : {}),
              ...(category ? { category } : {}),
              ...(priority ? { priority } : {}),
              ...(assignee ? { assignee } : {}),
            } as never,
          },
        }),
      ),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });
  const stats = useQuery({ queryKey: ["admin", "support", "stats"], queryFn: () => unwrap(api.GET("/api/v1/admin/support/stats")), refetchInterval: 60_000 });
  const rows = useMemo(() => list.data?.results ?? [], [list.data]);
  const counts = stats.data?.counts;
  const open = rows.find((r) => r.id === ticketId) ?? null;
  const openIndex = open ? rows.indexOf(open) : -1;

  const openTicket = useCallback(
    (id: string | null) => {
      setCursor(id);
      setParam({ ticket: id ?? "" });
    },
    [setParam],
  );
  const goTo = useCallback(
    (delta: number) => {
      if (rows.length === 0) return;
      const at = open ? openIndex : cursor ? rows.findIndex((r) => r.id === cursor) : -1;
      const next = rows[Math.max(0, Math.min(rows.length - 1, at + delta))];
      if (!next) return;
      setCursor(next.id);
      if (open) setParam({ ticket: next.id });
    },
    [rows, open, openIndex, cursor, setParam],
  );

  // J and K move through the list and Enter opens the one the cursor is on.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;
      if ((event.target as HTMLElement | null)?.getAttribute?.("contenteditable") === "true") return;
      const k = event.key.toLowerCase();
      if (k === "j") {
        event.preventDefault();
        goTo(1);
      } else if (k === "k") {
        event.preventDefault();
        goTo(-1);
      } else if (k === "enter" && !open && cursor && (event.target === document.body || (event.target as HTMLElement).tagName === "TR")) {
        openTicket(cursor);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goTo, open, cursor, openTicket]);

  const columns = useMemo<Array<ColumnDef<Row, unknown>>>(
    () => [
      {
        id: "ticket",
        header: "Ticket",
        meta: { label: "Ticket", sortKey: "ticket" } satisfies ColumnMeta,
        cell: ({ row }) => <span className="wo-tickets__ref">{row.original.reference}</span>,
      },
      {
        id: "member",
        header: "Member",
        meta: { label: "Member" } satisfies ColumnMeta,
        cell: ({ row }) => {
          const m = row.original.member as Person;
          return (
            <span className="adm-who">
              <Avatar name={m.name} id={m.id ?? undefined} src={(m.avatar as { thumb?: string } | null)?.thumb} size="sm" />
              <span className="adm-who__text">
                <span className="adm-who__name">{m.name}</span>
                <span className="adm-who__id" style={{ fontFamily: "var(--font-body)" }}>
                  {m.email}
                </span>
              </span>
            </span>
          );
        },
      },
      {
        id: "subject",
        header: "Subject",
        meta: { label: "Subject" } satisfies ColumnMeta,
        cell: ({ row }) => (
          <span className="adm-who__text">
            <span className="adm-who__name">{row.original.subject}</span>
            <span className="adm-who__id" style={{ fontFamily: "var(--font-body)" }}>
              {row.original.category_label}
              {row.original.priority === "high" ? " · High priority" : ""}
            </span>
          </span>
        ),
      },
      {
        id: "status",
        header: "Status",
        meta: { label: "Status", sortKey: "status" } satisfies ColumnMeta,
        cell: ({ row }) => (
          <span className="wo-ticket__statuscell">
            <StatusChip tone={STATUS_TONE[row.original.status]}>{ADMIN_STATUS_LABEL[row.original.status]}</StatusChip>
            {row.original.is_overdue ? <span className="wo-ticket__late">Overdue</span> : null}
          </span>
        ),
      },
      {
        id: "assignee",
        header: "Assignee",
        meta: { label: "Assignee" } satisfies ColumnMeta,
        cell: ({ row }) => {
          const a = row.original.assignee as Person | null;
          return a ? a.name : <span className="app-faint">Unassigned</span>;
        },
      },
      {
        id: "created",
        header: "Created",
        meta: { label: "Created", sortKey: "created" } satisfies ColumnMeta,
        cell: ({ row }) => <span title={formatDate(row.original.created_at)}>{formatDate(row.original.created_at)}</span>,
      },
      {
        id: "activity",
        header: "Last activity",
        meta: { label: "Last activity", sortKey: "activity" } satisfies ColumnMeta,
        cell: ({ row }) => <span title={formatDate(row.original.last_activity_at)}>{timeAgo(row.original.last_activity_at)}</span>,
      },
      {
        id: "age",
        header: "Age",
        meta: { label: "Age" } satisfies ColumnMeta,
        cell: ({ row }) => {
          const end = row.original.resolved_at ? new Date(row.original.resolved_at) : new Date();
          const hours = Math.max(0, Math.round((end.getTime() - new Date(row.original.created_at).getTime()) / 3_600_000));
          return hours < 48 ? `${hours} h` : `${Math.round(hours / 24)} d`;
        },
      },
    ],
    [],
  );

  const assigneeOptions = [
    { value: "", label: "Anyone" },
    { value: "me", label: "Me" },
    { value: "unassigned", label: "Unassigned" },
    ...(agents.data ?? []).map((a) => ({ value: a.id as string, label: a.name })),
  ];
  const filtered = Boolean(q || category || priority || assignee);

  return (
    <>
      <PageHeader eyebrow="Support" title="Support inbox" lead="Requests from members. Use J and K to move down the list, and Enter to open one." />

      <StatStrip
        columns={5}
        loading={stats.isPending}
        items={[
          { label: "New", value: counts ? formatNumber(counts.open) : "…" },
          { label: "In progress", value: counts ? formatNumber(counts.in_progress) : "…" },
          { label: "Awaiting member", value: counts ? formatNumber(counts.awaiting_member) : "…" },
          { label: "Resolved this week", value: counts ? formatNumber(counts.resolved_this_week) : "…" },
          { label: "Median first reply, 30 days", value: duration(stats.data?.median_first_response_seconds) },
        ]}
      />

      <section className="adm-card adm-tablecard" aria-labelledby="inbox-title">
        <div className="adm-tablecard__head">
          <h2 className="adm-card__title" id="inbox-title">
            Requests
          </h2>
        </div>
        <div style={{ padding: "0 var(--space-6) var(--space-3)" }}>
          <Segmented
            label="Requests by state"
            idPrefix="inbox"
            value={tab}
            onChange={(v) => {
              setCursor(null);
              setParam({ tab: v === "working" ? "" : v, page: "", ticket: "" });
            }}
            options={TABS.map((t) => ({ value: t.value, label: counts ? `${t.label} ${formatNumber(t.count(counts))}` : t.label }))}
          />
        </div>
        <div className="wo-inbox__filters">
          <Input label="Search" type="search" placeholder="SUP-1042, subject, name or email" value={typed} onChange={(e) => setTyped(e.target.value)} />
          <Select label="Category" value={category} options={[{ value: "", label: "Any category" }, ...CATEGORIES]} onChange={(e) => setParam({ category: e.target.value, page: "" })} />
          <Select label="Assignee" value={assignee} options={assigneeOptions} onChange={(e) => setParam({ assignee: e.target.value, page: "" })} />
          <Select label="Priority" value={priority} options={[{ value: "", label: "Any priority" }, ...PRIORITIES]} onChange={(e) => setParam({ priority: e.target.value, page: "" })} />
        </div>
        <div id="inbox-panel" role="tabpanel" aria-labelledby={`inbox-${tab}`}>
          {list.isError ? (
            <div style={{ padding: "var(--space-6)" }}>
              <ErrorState error={list.error} onRetry={() => void list.refetch()} />
            </div>
          ) : (
            <DataTable
              caption="Support requests"
              columns={columns}
              data={rows}
              getRowId={(r) => r.id}
              loading={list.isPending}
              sort={sort}
              onSortChange={(next) => setParam({ sort: `${next.desc ? "-" : ""}${next.id}`, page: "" })}
              activeRowId={open?.id ?? cursor}
              onRowClick={(r) => openTicket(r.id)}
              empty={
                <div style={{ padding: "var(--space-6)" }}>
                  <EmptyState title={filtered ? "No requests match" : tab === "working" ? "Nothing is waiting" : "Nothing here"}>
                    {filtered ? "Try clearing a filter." : tab === "working" ? "Every request has been dealt with." : "No requests in this state."}
                  </EmptyState>
                </div>
              }
            />
          )}
        </div>
        <Pager page={page} size={size} total={list.data?.count ?? 0} onPage={(p) => setParam({ page: p === 0 ? "" : String(p) })} onSize={(s) => setParam({ size: s === 25 ? "" : String(s), page: "" })} />
      </section>

      {open ? <TicketDrawer id={open.id} onClose={() => openTicket(null)} position={{ index: openIndex, total: rows.length }} onPrevious={() => goTo(-1)} onNext={() => goTo(1)} /> : null}
      {ticketId && !open && !list.isPending ? <TicketDrawer id={ticketId} onClose={() => openTicket(null)} position={{ index: 0, total: 1 }} onPrevious={() => undefined} onNext={() => undefined} /> : null}
    </>
  );
}
