import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Check, Download, MoreHorizontal, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { REFERRAL_SOURCES } from "../referrals/ref";
import { api, unwrap } from "../api/client";
import { useCountries } from "../api/reference";
import type { components } from "../api/schema";
import { Avatar, Button, Input, Select } from "../components";
import { formatDate, formatNumber, humanise, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, PageHeader, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { useMemberCount } from "./data/members";
import { iso, monthWindows } from "./data/series";
import { ConfirmDialog, ReasonDialog } from "./dialogs";
import { DataTable, type ColumnMeta, type Sort } from "./kit/DataTable";
import { SavedViews } from "./kit/SavedViews";
import { BulkBar, ColumnsMenu, DensityToggle, FilterChips, Pager, StatStrip, StatusChip, type Density, type Tone } from "./kit/TableBits";
import { useUndoable } from "./kit/undo";
import { ROLE_LABELS } from "./permissions";
import { usePref } from "./shell/prefs";
import { MemberDrawer, type DrawerAction } from "./MemberDrawer";
import { useStepUp } from "./StepUp";

type Member = components["schemas"]["MemberRow"];
type Status = "pending" | "active" | "suspended" | "removed" | "rejected";
type Ordering = "created_at" | "-created_at" | "email" | "-email" | "last_login" | "-last_login" | "status" | "-status";

const STATUSES: Status[] = ["pending", "active", "suspended", "removed", "rejected"];
const TONE: Record<string, Tone> = { active: "success", pending: "warning", suspended: "danger", removed: "neutral", rejected: "neutral" };
const SORTABLE = ["created_at", "email", "last_login", "status"];
const SIZES = [25, 50, 100];
const COLUMN_LABELS: Record<string, string> = { country: "Country", startup: "Startup", source: "Source", referrer: "Referred by", roles: "Roles", status: "Status", verified: "Email confirmed", created_at: "Joined", last_login: "Last active" };

type Action = { kind: "approve" | "reinstate" | "reset-mfa" | "reject" | "suspend" | "remove"; member: Member };

function zoneName(): string {
  const part = new Intl.DateTimeFormat("en-NG", { timeZoneName: "short" }).formatToParts(new Date()).find((p) => p.type === "timeZoneName");
  return part?.value ?? "";
}

// The start of a time ordered id is the same for everyone who joined together, so show the end.
const shortId = (id: string) => id.slice(-8);

function parseSort(value: string | null): Sort {
  const desc = (value ?? "-created_at").startsWith("-");
  const id = (value ?? "-created_at").replace(/^-/, "");
  return SORTABLE.includes(id) ? { id, desc } : { id: "created_at", desc: true };
}

function RowActions({ member, onAct }: { member: Member; onAct: (kind: Action["kind"]) => void }) {
  const items: Array<{ kind: Action["kind"]; label: string }> = [];
  if (member.status === "pending") items.push({ kind: "approve", label: "Approve" }, { kind: "reject", label: "Reject" });
  if (member.status === "active") items.push({ kind: "suspend", label: "Suspend" }, { kind: "reset-mfa", label: "Reset two step sign in" });
  if (member.status === "suspended") items.push({ kind: "reinstate", label: "Reinstate" });
  if (member.status === "active" || member.status === "suspended") items.push({ kind: "remove", label: "Remove" });
  if (items.length === 0) return <span className="app-faint">No actions</span>;
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button type="button" className="adm-iconbtn" aria-label={`Actions for ${member.email}`}>
          <MoreHorizontal size={20} strokeWidth={1.5} aria-hidden="true" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} className="adm-menu">
          {items.map((item) => (
            <DropdownMenu.Item key={item.kind} className="adm-menu__item" onSelect={() => onAct(item.kind)}>
              {item.label}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

export default function Members() {
  useDocumentTitle("Members");
  const [params, setParams] = useSearchParams();
  const { memberId } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const undoable = useUndoable();
  const countries = useCountries();
  const countryName = useMemo(() => new Map((countries.data ?? []).map((c) => [c.value, c.label])), [countries.data]);
  const [density, setDensity] = usePref<Density>("members:density", "comfortable");
  const [hidden, setHidden] = usePref<string[]>("members:hidden-columns", []);
  const [showFilters, setShowFilters] = usePref<boolean>("members:filters-open", true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [action, setAction] = useState<Action | null>(null);
  const [exporting, setExporting] = useState(false);

  const q = params.get("q") ?? "";
  const status = (params.get("status") ?? "") as Status | "";
  const role = params.get("role") ?? "";
  const verified = params.get("verified") ?? "";
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const source = params.get("source") ?? "";
  const sort = parseSort(params.get("sort"));
  const size = SIZES.includes(Number(params.get("size"))) ? Number(params.get("size")) : 25;
  const page = Math.max(0, Number(params.get("page") ?? 0) || 0);
  const ordering = `${sort.desc ? "-" : ""}${sort.id}` as Ordering;

  // The panel edits a draft; Apply writes it to the address so the view can be shared.
  const [draft, setDraft] = useState({ q, status, role, verified, from, to, source });
  const set = (next: Record<string, string>, keepPage = false) => {
    const merged = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) merged.set(k, v);
      else merged.delete(k);
    }
    if (!keepPage) merged.delete("page");
    setParams(merged, { replace: true });
    setSelected(new Set());
  };
  const apply = () => set({ q: draft.q.trim(), status: draft.status, role: draft.role, verified: draft.verified, from: draft.from, to: draft.to, source: draft.source });
  const clearAll = () => {
    setDraft({ q: "", status: "", role: "", verified: "", from: "", to: "", source: "" });
    set({ q: "", status: "", role: "", verified: "", from: "", to: "", source: "" });
  };

  const filters = useMemo(
    () => ({
      ...(q ? { q } : {}),
      ...(status ? { status } : {}),
      ...(role ? { role } : {}),
      ...(verified ? { email_verified: verified === "yes" } : {}),
      ...(from ? { joined_after: from } : {}),
      ...(to ? { joined_before: to } : {}),
      ...(source ? { referral_source: source } : {}),
    }),
    [q, status, role, verified, from, to, source],
  );

  const list = useQuery({
    queryKey: ["admin", "members", "list", filters, ordering, page, size],
    queryFn: () => unwrap(api.GET("/api/v1/admin/members", { params: { query: { limit: size, offset: page * size, ordering, ...filters } as never } })),
    placeholderData: keepPreviousData,
  });

  // Summary figures follow the search, role and period, but not the status or confirmation filters.
  const base = useMemo(() => ({ ...(q ? { q } : {}), ...(role ? { role } : {}), ...(from ? { joined_after: from } : {}), ...(to ? { joined_before: to } : {}) }), [q, role, from, to]);
  const total = useMemberCount({}, base);
  const pending = useMemberCount({ status: "pending" }, base);
  const active = useMemberCount({ status: "active" }, base);
  const suspended = useMemberCount({ status: "suspended" }, base);
  const rejected = useMemberCount({ status: "rejected" }, base);
  const unconfirmed = useMemberCount({ email_verified: false }, base);
  const n = (c: { data?: number }) => (c.data === undefined ? "…" : formatNumber(c.data));

  const rows = list.data?.results ?? [];
  const count = list.data?.count ?? 0;

  const refresh = () => client.invalidateQueries({ queryKey: ["admin"] });
  const path = (m: Member) => ({ params: { path: { user_id: m.id } } });
  const run = async (a: Action, reason = "") => {
    const m = a.member;
    await guard(async () => {
      if (a.kind === "approve") await unwrap(api.POST("/api/v1/admin/members/{user_id}/approve", path(m)));
      else if (a.kind === "reinstate") await unwrap(api.POST("/api/v1/admin/members/{user_id}/reinstate", path(m)));
      else if (a.kind === "reset-mfa") await unwrap(api.POST("/api/v1/admin/members/{user_id}/reset-mfa", path(m)));
      else if (a.kind === "reject") await unwrap(api.POST("/api/v1/admin/members/{user_id}/reject", { ...path(m), body: { reason } }));
      else if (a.kind === "suspend") await unwrap(api.POST("/api/v1/admin/members/{user_id}/suspend", { ...path(m), body: { reason } }));
      else await unwrap(api.POST("/api/v1/admin/members/{user_id}/remove", { ...path(m), body: { reason } }));
    });
    toast.show({ approve: "Member approved", reject: "Request rejected", suspend: "Member suspended", reinstate: "Member reinstated", remove: "Member removed", "reset-mfa": "Two step sign in reset" }[a.kind]);
    await refresh();
  };

  const bulkApprove = () => {
    const targets = rows.filter((m) => selected.has(m.id) && m.status === "pending");
    if (targets.length === 0) return;
    setSelected(new Set());
    undoable({
      message: `Approving ${targets.length} ${targets.length === 1 ? "member" : "members"}`,
      commit: async () => {
        await guard(async () => {
          for (const m of targets) await unwrap(api.POST("/api/v1/admin/members/{user_id}/approve", path(m)));
        });
        toast.show(`${targets.length} ${targets.length === 1 ? "member" : "members"} approved`);
        await refresh();
      },
    });
  };

  const csvEscape = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const download = (members: Member[], name: string) => {
    const head = ["Email", "Status", "Roles", "Email confirmed", "Joined", "Last active"];
    const lines = members.map((m) => [m.email, m.status, m.roles.join(" "), m.email_verified_at ? "yes" : "no", m.created_at, m.last_login ?? ""].map(csvEscape).join(","));
    const url = URL.createObjectURL(new Blob([[head.join(","), ...lines].join("\n")], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
  };
  const exportAll = async () => {
    setExporting(true);
    try {
      const all: Member[] = [];
      for (let offset = 0; offset < Math.min(count, 5000); offset += 100) {
        const chunk = await unwrap(api.GET("/api/v1/admin/members", { params: { query: { limit: 100, offset, ordering, ...filters } as never } }));
        all.push(...chunk.results);
      }
      download(all, `members-${iso(new Date())}.csv`);
    } finally {
      setExporting(false);
    }
  };

  const columns = useMemo<Array<ColumnDef<Member, unknown>>>(
    () => [
      {
        id: "email",
        header: "Member",
        meta: { sortKey: "email", label: "Member" } satisfies ColumnMeta,
        cell: ({ row }) => (
          <span className="adm-who">
            <Avatar name={row.original.email} id={row.original.id} size="sm" />
            <span className="adm-who__text">
              <Link className="adm-who__name" to={{ pathname: `/admin/members/${row.original.id}`, search: params.toString() }}>{row.original.name || row.original.email}</Link>
              <span className="adm-who__id">{row.original.name ? `${row.original.email} · ` : ""}{shortId(row.original.id)}</span>
            </span>
          </span>
        ),
      },
      {
        id: "country",
        header: "Country",
        meta: { label: "Country" } satisfies ColumnMeta,
        cell: ({ row }) => (row.original.country ? (countryName.get(row.original.country) ?? row.original.country) : <span className="app-faint">Not given</span>),
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
        id: "source",
        header: "Source",
        meta: { label: "Source" } satisfies ColumnMeta,
        cell: ({ row }) => row.original.referral_label || <span className="app-faint">Did not say</span>,
      },
      {
        id: "referrer",
        header: "Referred by",
        meta: { label: "Referred by" } satisfies ColumnMeta,
        cell: ({ row }) => (row.original.referrer ? row.original.referrer.name : <span className="app-faint">Nobody named</span>),
      },
      {
        id: "roles",
        header: "Roles",
        meta: { label: "Roles" } satisfies ColumnMeta,
        cell: ({ row }) => (row.original.roles.length === 0 ? <span className="app-faint">None yet</span> : row.original.roles.map((r) => ROLE_LABELS[r] ?? humanise(r)).join(", ")),
      },
      {
        id: "status",
        header: "Status",
        meta: { sortKey: "status", label: "Status" } satisfies ColumnMeta,
        cell: ({ row }) => <StatusChip tone={TONE[row.original.status] ?? "neutral"}>{humanise(row.original.status)}</StatusChip>,
      },
      {
        id: "verified",
        header: "Email",
        meta: { label: "Email confirmed" } satisfies ColumnMeta,
        cell: ({ row }) =>
          row.original.email_verified_at ? (
            <span className="adm-yes"><Check size={16} strokeWidth={2} aria-hidden="true" />Confirmed</span>
          ) : (
            <span className="adm-no"><X size={16} strokeWidth={2} aria-hidden="true" />Not confirmed</span>
          ),
      },
      {
        id: "created_at",
        header: "Joined",
        meta: { sortKey: "created_at", label: "Joined" } satisfies ColumnMeta,
        cell: ({ row }) => formatDate(row.original.created_at),
      },
      {
        id: "last_login",
        header: "Last active",
        meta: { sortKey: "last_login", label: "Last active" } satisfies ColumnMeta,
        cell: ({ row }) => (row.original.last_login ? timeAgo(row.original.last_login) : "Never"),
      },
      {
        id: "actions",
        header: () => <span className="wo-visually-hidden">Actions</span>,
        meta: { align: "end" } satisfies ColumnMeta,
        cell: ({ row }) => <RowActions member={row.original} onAct={(kind) => setAction({ kind, member: row.original })} />,
      },
    ],
    [countryName, params],
  );
  const visibility = Object.fromEntries(hidden.map((id) => [id, false]));

  const chips = [
    q && { id: "q", label: `Search: ${q}`, onRemove: () => set({ q: "" }) },
    status && { id: "status", label: `Status: ${humanise(status)}`, onRemove: () => set({ status: "" }) },
    role && { id: "role", label: `Role: ${ROLE_LABELS[role] ?? humanise(role)}`, onRemove: () => set({ role: "" }) },
    verified && { id: "verified", label: verified === "yes" ? "Email confirmed" : "Email not confirmed", onRemove: () => set({ verified: "" }) },
    source && { id: "source", label: source === "none" ? "Source: did not say" : `Source: ${REFERRAL_SOURCES.find((s) => s.value === source)?.label ?? source}`, onRemove: () => set({ source: "" }) },
    (from || to) && { id: "period", label: `Joined ${from ? formatDate(from) : "any time"} to ${to ? formatDate(to) : "now"}`, onRemove: () => set({ from: "", to: "" }) },
  ].filter(Boolean) as Array<{ id: string; label: string; onRemove: () => void }>;

  const quick = (key: string) => {
    const w = monthWindows();
    const day = (offset: number) => {
      const d = new Date(w.today);
      d.setDate(d.getDate() + offset);
      return iso(d);
    };
    const ranges: Record<string, [string, string]> = {
      today: [iso(w.today), iso(w.today)],
      yesterday: [day(-1), day(-1)],
      week: [day(-6), iso(w.today)],
      month: [iso(w.thisStart), iso(w.today)],
      last: [iso(w.lastStart), iso(w.lastEnd)],
      all: ["", ""],
    };
    const [a, b] = ranges[key] ?? ["", ""];
    setDraft((d) => ({ ...d, from: a, to: b }));
  };

  const periodText = from || to ? `${from ? formatDate(from) : "The start"} to ${to ? formatDate(to) : "today"}` : "All time";
  const viewQuery = (() => {
    const p = new URLSearchParams(params);
    p.delete("page");
    return p.toString();
  })();

  return (
    <>
      <PageHeader
        eyebrow="Members"
        title="Members"
        lead={`${periodText} · ${zoneName()} · sorted by ${COLUMN_LABELS[sort.id]?.toLowerCase() ?? sort.id}, ${sort.desc ? "newest first" : "oldest first"}`}
        actions={
          <div className="adm-toolbar">
            <SavedViews
              storageKey="members"
              currentQuery={viewQuery}
              onApply={(query) => {
                setParams(new URLSearchParams(query), { replace: true });
                setSelected(new Set());
              }}
            />
            <ColumnsMenu
              columns={Object.entries(COLUMN_LABELS).map(([id, label]) => ({ id, label, visible: !hidden.includes(id) }))}
              onToggle={(id) => setHidden((h) => (h.includes(id) ? h.filter((x) => x !== id) : [...h, id]))}
              onReset={() => setHidden([])}
            />
            <Button variant="secondary" aria-expanded={showFilters} aria-controls="members-filters" onClick={() => setShowFilters((s) => !s)}>
              {showFilters ? "Hide filters" : "Show filters"}
            </Button>
            <Button variant="primary" loading={exporting} onClick={() => void exportAll()} icon={<Download size={16} strokeWidth={1.5} aria-hidden="true" />}>Export</Button>
          </div>
        }
      />

      {showFilters ? (
        <form id="members-filters" className="adm-card adm-filters" aria-label="Filters" onSubmit={(e) => { e.preventDefault(); apply(); }}>
          <div className="app-stack" style={{ gap: "var(--space-3)" }}>
            <span className="wo-label">Joined</span>
            <div className="adm-quick" role="group" aria-label="Quick periods">
              {[["today", "Today"], ["yesterday", "Yesterday"], ["week", "Last 7 days"], ["month", "This month"], ["last", "Last month"], ["all", "All time"]].map(([key, label]) => (
                <button key={key} type="button" onClick={() => quick(key ?? "all")}>{label}</button>
              ))}
            </div>
          </div>
          <div className="adm-filters__grid">
            <Input label="From" type="date" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} />
            <Input label="To" type="date" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
            <Input label="Search by email" value={draft.q} onChange={(e) => setDraft({ ...draft, q: e.target.value })} />
            <Select label="Status" options={[{ value: "", label: "Any status" }, ...STATUSES.map((s) => ({ value: s, label: humanise(s) }))]} value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value as Status | "" })} />
            <Select label="Role" options={[{ value: "", label: "Any role" }, ...Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))]} value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value })} />
            <Select label="How they heard of us" options={[{ value: "", label: "Any source" }, { value: "none", label: "Did not say" }, ...REFERRAL_SOURCES.map((s) => ({ value: s.value, label: s.label }))]} value={draft.source} onChange={(e) => setDraft({ ...draft, source: e.target.value })} />
            <Select label="Email" options={[{ value: "", label: "Any" }, { value: "yes", label: "Confirmed" }, { value: "no", label: "Not confirmed" }]} value={draft.verified} onChange={(e) => setDraft({ ...draft, verified: e.target.value })} />
          </div>
          <div className="adm-filters__actions">
            <Button variant="ghost" onClick={clearAll}>Clear all</Button>
            <Button type="submit">Apply filters</Button>
          </div>
        </form>
      ) : null}

      <FilterChips chips={chips} onClear={clearAll} />

      <StatStrip
        loading={total.isPending}
        items={[
          { label: "Members", value: n(total) },
          { label: "Waiting for approval", value: n(pending) },
          { label: "Active", value: n(active) },
          { label: "Suspended", value: n(suspended) },
          { label: "Rejected", value: n(rejected) },
          { label: "Email not confirmed", value: n(unconfirmed) },
        ]}
      />

      <section className="adm-card adm-tablecard" aria-labelledby="members-title">
        <div className="adm-tablecard__head">
          <h2 className="adm-card__title" id="members-title">{formatNumber(count)} {count === 1 ? "member" : "members"}</h2>
          <div className="adm-tablecard__tools">
            <DensityToggle value={density} onChange={setDensity} />
            <Button variant="secondary" size="sm" onClick={() => void list.refetch()} loading={list.isFetching && !list.isPending}>Refresh</Button>
          </div>
        </div>
        {list.isError ? (
          <div style={{ padding: "var(--space-6)" }}><ErrorState error={list.error} onRetry={() => void list.refetch()} /></div>
        ) : (
          <DataTable
            caption="Members"
            columns={columns}
            data={rows}
            getRowId={(m) => m.id}
            rowLabel={(m) => m.email}
            loading={list.isPending}
            density={density}
            visibility={visibility}
            sort={sort}
            onSortChange={(s) => set({ sort: `${s.desc ? "-" : ""}${s.id}` })}
            selected={selected}
            onSelectedChange={setSelected}
            empty={<div style={{ padding: "var(--space-6)" }}><EmptyState title="No members match">Try different filters, or clear them to see everyone.</EmptyState></div>}
          />
        )}
        <Pager page={page} size={size} total={count} onPage={(p) => set({ page: p === 0 ? "" : String(p) }, true)} onSize={(s) => set({ size: s === 25 ? "" : String(s) })} />
      </section>

      <BulkBar count={selected.size} noun={selected.size === 1 ? "member selected" : "members selected"} onClear={() => setSelected(new Set())}>
        <Button size="sm" variant="accent" onClick={bulkApprove} disabled={!rows.some((m) => selected.has(m.id) && m.status === "pending")}>Approve waiting</Button>
        <Button size="sm" variant="white" onClick={() => download(rows.filter((m) => selected.has(m.id)), `members-selected-${iso(new Date())}.csv`)}>Export selected</Button>
      </BulkBar>

      {memberId ? (
        <MemberDrawer
          memberId={memberId}
          onClose={() => navigate({ pathname: "/admin/members", search: params.toString() })}
          onAct={(kind: DrawerAction, member) => setAction({ kind, member: member as Member })}
        />
      ) : null}

      {action && (action.kind === "reject" || action.kind === "suspend" || action.kind === "remove") ? (
        <ReasonDialog
          title={{ reject: "Reject this request?", suspend: "Suspend this member?", remove: "Remove this member?" }[action.kind]}
          confirmLabel={{ reject: "Reject", suspend: "Suspend", remove: "Remove" }[action.kind]}
          tone={action.kind === "remove" ? "danger" : "primary"}
          intro={`${action.member.email}. ${action.kind === "reject" ? "They are told their request was not accepted." : action.kind === "suspend" ? "They cannot sign in until reinstated." : "Their access ends and their profile is hidden."}`}
          onConfirm={(reason) => run(action, reason)}
          onClose={() => setAction(null)}
        />
      ) : null}
      {action && (action.kind === "approve" || action.kind === "reinstate" || action.kind === "reset-mfa") ? (
        <ConfirmDialog
          title={{ approve: "Approve this member?", reinstate: "Reinstate this member?", "reset-mfa": "Reset two step sign in?" }[action.kind]}
          body={`${action.member.email}. ${action.kind === "approve" ? "They get full access and an email telling them so." : action.kind === "reinstate" ? "They can sign in again." : "They must set up an authenticator app again next time they sign in."}`}
          confirmLabel={{ approve: "Approve", reinstate: "Reinstate", "reset-mfa": "Reset" }[action.kind]}
          onConfirm={() => run(action)}
          onClose={() => setAction(null)}
        />
      ) : null}
    </>
  );
}
