import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import { useCountries } from "../api/reference";
import type { components } from "../api/schema";
import { Avatar } from "../components";
import { formatDate, formatNumber, humanise, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, PageHeader, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { ApprovalDrawer } from "./ApprovalDrawer";
import { iso, monthWindows, useDailySeries, type DailySeries } from "./data/series";
import { useMemberCount } from "./data/members";
import { DataTable, type ColumnMeta } from "./kit/DataTable";
import { Pager, StatStrip, StatusChip, type Tone } from "./kit/TableBits";
import { useUndoable } from "./kit/undo";
import { Segmented } from "./kit/Segmented";
import { isTyping } from "./shell/prefs";
import { useStepUp } from "./StepUp";

type Row = components["schemas"]["MemberRow"];
type Tab = "waiting" | "unconfirmed" | "approved" | "rejected" | "all";

const TABS: Array<{ value: Tab; label: string }> = [
  { value: "waiting", label: "Waiting" },
  { value: "unconfirmed", label: "Email not confirmed" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];
const TONE: Record<string, Tone> = { active: "success", pending: "warning", suspended: "danger", removed: "neutral", rejected: "neutral" };
const SIZES = [25, 50, 100];

/** What each tab asks the server for. The waiting queue runs oldest first, so nobody is left behind. */
const QUERY: Record<Tab, Record<string, string | boolean>> = {
  waiting: { status: "pending", email_verified: true, ordering: "created_at" },
  unconfirmed: { status: "pending", email_verified: false, ordering: "created_at" },
  approved: { status: "active", ordering: "-created_at" },
  rejected: { status: "rejected", ordering: "-created_at" },
  all: { ordering: "-created_at" },
};

const shortId = (id: string) => id.slice(-8);

function lastDays(series: DailySeries | undefined, days: number): { sum: number; average: number | null } {
  const today = monthWindows().today;
  let sum = 0;
  let nonZero = 0;
  for (let i = 0; i < days; i += 1) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const v = series?.byDay.get(iso(d)) ?? 0;
    sum += v;
    if (v > 0) nonZero += 1;
  }
  return { sum, average: nonZero === 0 ? null : sum / nonZero };
}

export default function Approvals() {
  useDocumentTitle("Approvals");
  const [params, setParams] = useSearchParams();
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const undoable = useUndoable();
  const countries = useCountries();
  const countryName = useMemo(() => new Map((countries.data ?? []).map((c) => [c.value, c.label])), [countries.data]);
  const [held, setHeld] = useState<Set<string>>(new Set());
  const [rejecting, setRejecting] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);

  const tab = (TABS.some((t) => t.value === params.get("tab")) ? params.get("tab") : "waiting") as Tab;
  const size = SIZES.includes(Number(params.get("size"))) ? Number(params.get("size")) : 25;
  const page = Math.max(0, Number(params.get("page") ?? 0) || 0);
  const requestId = params.get("request");

  const setParam = useCallback(
    (next: Record<string, string>, replace = true) => {
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
      );
    },
    [setParams],
  );

  const list = useQuery({
    queryKey: ["admin", "members", "approvals", tab, page, size],
    queryFn: () => unwrap(api.GET("/api/v1/admin/members", { params: { query: { limit: size, offset: page * size, ...QUERY[tab] } as never } })),
    placeholderData: keepPreviousData,
  });
  const rows = useMemo(() => (list.data?.results ?? []).filter((m) => !held.has(m.id)), [list.data, held]);
  const total = list.data?.count ?? 0;

  const waiting = useMemberCount(QUERY.waiting);
  const unconfirmed = useMemberCount(QUERY.unconfirmed);
  const approved = useMemberCount(QUERY.approved);
  const rejected = useMemberCount(QUERY.rejected);
  const everyone = useMemberCount({});
  const counts: Record<Tab, number | undefined> = { waiting: waiting.data, unconfirmed: unconfirmed.data, approved: approved.data, rejected: rejected.data, all: everyone.data };

  const w = useMemo(() => monthWindows(), []);
  const approvedSeries = useDailySeries("events.member_approved", w);
  const rejectedSeries = useDailySeries("events.member_rejected", w);
  const timeSeries = useDailySeries("approval_time_hours", w);
  const approvedWeek = lastDays(approvedSeries.data, 7).sum;
  const rejectedWeek = lastDays(rejectedSeries.data, 7).sum;
  const avgHours = lastDays(timeSeries.data, 30).average;

  const open = rows.find((m) => m.id === requestId) ?? null;
  const openIndex = open ? rows.indexOf(open) : -1;

  const openRequest = useCallback((id: string | null) => {
    setRejecting(false);
    setCursor(id);
    setParam({ request: id ?? "" });
  }, [setParam]);

  // The command palette sends people here to deal with the oldest request.
  useEffect(() => {
    if (params.get("next") && rows.length > 0 && tab === "waiting") {
      setParam({ next: "", request: rows[0]?.id ?? "" });
      setCursor(rows[0]?.id ?? null);
    }
  }, [params, rows, tab, setParam]);

  const goTo = useCallback(
    (delta: number) => {
      if (rows.length === 0) return;
      const at = open ? openIndex : cursor ? rows.findIndex((m) => m.id === cursor) : -1;
      const next = rows[Math.max(0, Math.min(rows.length - 1, at + delta))];
      if (!next) return;
      setCursor(next.id);
      setRejecting(false);
      if (open) setParam({ request: next.id });
    },
    [rows, open, openIndex, cursor, setParam],
  );

  const refresh = useCallback(() => client.invalidateQueries({ queryKey: ["admin"] }), [client]);

  // Holding the request off the list while the Undo window is open, then sending it.
  const decide = useCallback(
    (member: Row, kind: "approve" | "reject", reason = "") => {
      const label = member.name || member.email;
      const at = rows.findIndex((m) => m.id === member.id);
      const after = rows[at + 1] ?? rows[at - 1];
      setHeld((h) => new Set(h).add(member.id));
      setRejecting(false);
      if (open) {
        if (after) {
          setParam({ request: after.id });
          setCursor(after.id);
        } else setParam({ request: "" });
      }
      const release = () =>
        setHeld((h) => {
          const next = new Set(h);
          next.delete(member.id);
          return next;
        });
      undoable({
        message: kind === "approve" ? `Approving ${label}` : `Rejecting ${label}`,
        onUndo: release,
        commit: async () => {
          try {
            await guard(async () => {
              const args = { params: { path: { user_id: member.id } } };
              if (kind === "approve") await unwrap(api.POST("/api/v1/admin/members/{user_id}/approve", args));
              else await unwrap(api.POST("/api/v1/admin/members/{user_id}/reject", { ...args, body: { reason } }));
            });
            toast.show(kind === "approve" ? `${label} approved` : `${label} rejected`);
          } catch (error) {
            toast.show(`${label} could not be ${kind === "approve" ? "approved" : "rejected"}: ${messageOf(error)}`);
          } finally {
            await refresh();
            release();
          }
        },
      });
    },
    [rows, open, setParam, undoable, guard, toast, refresh],
  );

  // J and K move through the list, Enter opens, and A and R decide on the open request.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey || rejecting) return;
      const k = event.key.toLowerCase();
      if (k === "j") {
        event.preventDefault();
        goTo(1);
      } else if (k === "k") {
        event.preventDefault();
        goTo(-1);
      } else if (k === "enter" && !open && cursor && (event.target === document.body || (event.target as HTMLElement).tagName === "TR")) {
        openRequest(cursor);
      } else if (open && open.status === "pending" && k === "a") {
        event.preventDefault();
        decide(open, "approve");
      } else if (open && open.status === "pending" && k === "r") {
        event.preventDefault();
        setRejecting(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goTo, open, cursor, rejecting, decide, openRequest]);

  const columns = useMemo<Array<ColumnDef<Row, unknown>>>(
    () => [
      {
        id: "applicant",
        header: "Applicant",
        meta: { label: "Applicant" } satisfies ColumnMeta,
        cell: ({ row }) => (
          <span className="adm-who">
            <Avatar name={row.original.name || row.original.email} id={row.original.id} size="sm" />
            <span className="adm-who__text">
              <span className="adm-who__name">{row.original.name || row.original.email}</span>
              <span className="adm-who__id">{row.original.name ? `${row.original.email} · ` : ""}{shortId(row.original.id)}</span>
            </span>
          </span>
        ),
      },
      {
        id: "startup",
        header: "Startup",
        meta: { label: "Startup" } satisfies ColumnMeta,
        cell: ({ row }) =>
          row.original.startup ? (
            <span className="adm-who__text">
              <span className="adm-who__name">{row.original.startup}</span>
              <span className="adm-who__id" style={{ fontFamily: "var(--font-body)" }}>{[row.original.sector, row.original.stage].filter(Boolean).join(" · ")}</span>
            </span>
          ) : (
            <span className="app-faint">None</span>
          ),
      },
      {
        id: "country",
        header: "Country",
        meta: { label: "Country" } satisfies ColumnMeta,
        cell: ({ row }) => (row.original.country ? (countryName.get(row.original.country) ?? row.original.country) : <span className="app-faint">Not given</span>),
      },
      {
        id: "submitted",
        header: "Asked to join",
        meta: { label: "Asked to join" } satisfies ColumnMeta,
        cell: ({ row }) => <span title={formatDate(row.original.created_at)}>{timeAgo(row.original.created_at)}</span>,
      },
      {
        id: "status",
        header: "Status",
        meta: { label: "Status" } satisfies ColumnMeta,
        cell: ({ row }) => <StatusChip tone={TONE[row.original.status] ?? "neutral"}>{humanise(row.original.status)}</StatusChip>,
      },
    ],
    [countryName],
  );

  return (
    <>
      <PageHeader
        eyebrow="Members"
        title="Approvals"
        lead="People who asked to join. Use J and K to move down the list, Enter to open a request, A to approve and R to reject."
      />

      <StatStrip
        columns={4}
        loading={waiting.isPending}
        items={[
          { label: "Waiting for review", value: waiting.data === undefined ? "…" : formatNumber(waiting.data) },
          { label: "Approved, 7 days", value: formatNumber(approvedWeek) },
          { label: "Rejected, 7 days", value: formatNumber(rejectedWeek) },
          { label: "Average time to review", value: avgHours === null ? "Not yet" : avgHours < 1 ? "Under an hour" : `${Math.round(avgHours)} h` },
        ]}
      />

      <section className="adm-card adm-tablecard" aria-labelledby="queue-title">
        <div className="adm-tablecard__head">
          <h2 className="adm-card__title" id="queue-title">Requests</h2>
        </div>
        <div style={{ padding: "0 var(--space-6) var(--space-4)" }}>
          <Segmented
            label="Requests by state"
            idPrefix="queue"
            value={tab}
            onChange={(v) => setParam({ tab: v === "waiting" ? "" : v, page: "", request: "" })}
            options={TABS.map((t) => ({ value: t.value, label: counts[t.value] === undefined ? t.label : `${t.label} ${formatNumber(counts[t.value] ?? 0)}` }))}
          />
        </div>
        <div id="queue-panel" role="tabpanel" aria-labelledby={`queue-${tab}`}>
          {list.isError ? (
            <div style={{ padding: "var(--space-6)" }}><ErrorState error={list.error} onRetry={() => void list.refetch()} /></div>
          ) : (
            <DataTable
              caption="Requests to join"
              columns={columns}
              data={rows}
              getRowId={(m) => m.id}
              loading={list.isPending}
              activeRowId={open?.id ?? cursor}
              onRowClick={(m) => openRequest(m.id)}
              empty={
                <div style={{ padding: "var(--space-6)" }}>
                  <EmptyState title={tab === "waiting" ? "Nobody is waiting" : "Nothing here"}>
                    {tab === "waiting" ? "Every request has been dealt with." : "No requests in this state."}
                  </EmptyState>
                </div>
              }
            />
          )}
        </div>
        <Pager page={page} size={size} total={total} onPage={(p) => setParam({ page: p === 0 ? "" : String(p) })} onSize={(s) => setParam({ size: s === 25 ? "" : String(s), page: "" })} />
      </section>

      {open ? (
        <ApprovalDrawer
          member={open}
          position={{ index: openIndex, total: rows.length }}
          onClose={() => openRequest(null)}
          onPrevious={() => goTo(-1)}
          onNext={() => goTo(1)}
          onApprove={() => decide(open, "approve")}
          rejecting={rejecting}
          onRejectingChange={setRejecting}
          onReject={(reason) => decide(open, "reject", reason)}
        />
      ) : null}
    </>
  );
}
