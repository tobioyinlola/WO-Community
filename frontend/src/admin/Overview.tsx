import { useQuery } from "@tanstack/react-query";
import { Briefcase, Download, Flag, LifeBuoy, Mail, ShieldCheck, Trophy, UserCheck, UserPlus, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components";
import { formatDate, formatDateTime, formatNumber, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, Loaded, PageHeader, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { iso, monthWindows, summarise, useDailySeries, type DailySeries, type MonthWindows } from "./data/series";
import { BarChart, type DayPoint } from "./kit/BarChart";
import { changeBetween, Delta } from "./kit/Delta";
import { KpiCard } from "./kit/KpiCard";
import { Segmented } from "./kit/Segmented";
import { ReferralSection } from "./ReferralSection";
import { permissionsFor } from "./permissions";
import { useStepUp } from "./StepUp";

const TABS = [
  { value: "registrations", label: "Sign ups", noun: "sign ups" },
  { value: "events.member_approved", label: "Approvals", noun: "approvals" },
  { value: "events.post_created", label: "Posts", noun: "posts" },
  { value: "events.session_booked", label: "Sessions", noun: "session bookings" },
  { value: "active_members", label: "Active members", noun: "active members" },
] as const;
type Tab = (typeof TABS)[number]["value"];

const n = (v: number) => formatNumber(v);

function dayPoints(series: DailySeries | undefined, w: MonthWindows): DayPoint[] {
  const labelFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
  return Array.from({ length: w.daysThisMonth }, (_, i) => {
    const day = new Date(w.thisStart.getFullYear(), w.thisStart.getMonth(), i + 1);
    const before = new Date(w.lastStart.getFullYear(), w.lastStart.getMonth(), i + 1);
    return {
      label: labelFormat.format(day),
      current: day > w.today ? null : (series?.byDay.get(iso(day)) ?? 0),
      previous: i + 1 > w.daysLastMonth ? null : (series?.byDay.get(iso(before)) ?? 0),
    };
  });
}

function csvOf(points: DayPoint[], measure: string): string {
  const rows = points.map((p) => `${p.label},${p.current ?? ""},${p.previous ?? ""}`);
  return [`Day,This month (${measure}),Last month`, ...rows].join("\n");
}

interface Attention {
  id: string;
  icon: LucideIcon;
  count: number;
  text: string;
  to: string;
  action: string;
}

interface RecentEvent {
  id: string;
  at: string;
  icon: LucideIcon;
  text: string;
}

function AttentionCard({ items, loading }: { items: Attention[]; loading: boolean }) {
  return (
    <section className="adm-card" aria-labelledby="attn-title">
      <h2 className="adm-card__title" id="attn-title">Needs your attention</h2>
      {loading ? (
        <SkeletonRows count={3} />
      ) : items.length === 0 ? (
        <EmptyState title="All clear" icon={<ShieldCheck size={22} strokeWidth={1.5} />}>Nothing is waiting for you right now.</EmptyState>
      ) : (
        <ul className="adm-attn">
          {items.map((item) => (
            <li key={item.id} className="adm-attn__item">
              <span className="adm-attn__icon" aria-hidden="true"><item.icon size={18} strokeWidth={1.5} /></span>
              <p className="adm-attn__text"><strong>{n(item.count)}</strong> {item.text}</p>
              <Link to={item.to} className="wo-btn wo-btn--secondary wo-btn--sm">{item.action}</Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ActivityCard({ events, loading, viewAll }: { events: RecentEvent[]; loading: boolean; viewAll?: boolean }) {
  return (
    <section className="adm-card" aria-labelledby="act-title">
      <h2 className="adm-card__title" id="act-title">Recent activity</h2>
      {loading ? (
        <SkeletonRows count={4} />
      ) : events.length === 0 ? (
        <EmptyState title="Quiet for now">New sign ups, reports and job submissions will appear here.</EmptyState>
      ) : (
        <ol className="adm-timeline">
          {events.map((e) => (
            <li key={e.id} className="adm-timeline__item">
              <span className="adm-timeline__mark" aria-hidden="true"><e.icon size={14} strokeWidth={1.5} /></span>
              <div>
                <p className="adm-timeline__text">{e.text}</p>
                <p className="adm-timeline__time"><time dateTime={e.at} title={formatDateTime(e.at)}>{timeAgo(e.at)}</time></p>
              </div>
            </li>
          ))}
        </ol>
      )}
      {viewAll ? <p style={{ margin: "var(--space-3) 0 0" }}><Link to="/admin/audit">View all in the audit log</Link></p> : null}
    </section>
  );
}

export default function Overview() {
  useDocumentTitle("Dashboard");
  const { me } = useAuth();
  const toast = useToast();
  const guard = useStepUp();
  const have = useMemo(() => permissionsFor(me?.roles ?? []), [me?.roles]);
  const w = useMemo(() => monthWindows(), []);
  const [tab, setTab] = useState<Tab>("registrations");

  const dash = useQuery({ queryKey: ["admin", "dashboard"], queryFn: () => unwrap(api.GET("/api/v1/admin/dashboard")) });
  const regs = useDailySeries("registrations", w);
  const approvals = useDailySeries("events.member_approved", w);
  const sessions = useDailySeries("events.session_booked", w);
  const active = useDailySeries("active_members", w);
  const chart = useDailySeries(tab, w);

  const r = summarise(regs.data, w);
  const a = summarise(approvals.data, w);
  const s = summarise(sessions.data, w);
  const act = summarise(active.data, w);
  const d = dash.data;
  const loading = dash.isPending;

  const points = useMemo(() => dayPoints(chart.data, w), [chart.data, w]);
  const totals = summarise(chart.data, w);
  const current = TABS.find((t) => t.value === tab) ?? TABS[0];
  const monthName = new Intl.DateTimeFormat("en-GB", { month: "long" }).format(w.thisStart);

  const recent = useQuery({
    queryKey: ["admin", "recent-activity"],
    queryFn: async (): Promise<RecentEvent[]> => {
      if (have.has("audit.read")) {
        const page = await unwrap(api.GET("/api/v1/admin/audit", { params: { query: { limit: 10 } } }));
        return page.results.map((e) => ({
          id: e.id,
          at: e.created_at,
          icon: e.outcome === "failure" ? Flag : UserCheck,
          text: `${e.actor.name} · ${e.action.replace(/[._]/g, " ")}${e.target.title ? `: ${e.target.title}` : ""}`,
        }));
      }
      const out: RecentEvent[] = [];
      if (have.has("members.view")) {
        const page = await unwrap(api.GET("/api/v1/admin/members", { params: { query: { limit: 6 } } }));
        for (const m of page.results) {
          const waiting = m.status === "pending";
          out.push({ id: `m-${m.id}`, at: m.created_at, icon: waiting ? UserPlus : UserCheck, text: `${m.email} ${waiting ? "asked to join" : "joined"}` });
        }
      }
      if (have.has("reports.handle")) {
        const page = await unwrap(api.GET("/api/v1/admin/reports", { params: { query: { limit: 4 } } }));
        for (const x of page.results) out.push({ id: `r-${x.id}`, at: x.created_at, icon: Flag, text: `${x.reporter.name} reported a ${x.target.type.replace("_", " ")} for ${x.reason}` });
      }
      if (have.has("jobs.moderate")) {
        const page = await unwrap(api.GET("/api/v1/admin/jobs", { params: { query: { limit: 4 } } }));
        for (const j of page.results) out.push({ id: `j-${j.id}`, at: j.created_at, icon: Briefcase, text: `Job submitted: ${j.title}` });
      }
      return out.sort((x, y) => y.at.localeCompare(x.at)).slice(0, 8);
    },
  });

  const attention: Attention[] = d
    ? ([
        have.has("members.approve") && { id: "approvals", icon: UserPlus, count: d.pending.registrations_awaiting_approval, text: "requests are waiting for approval", to: "/admin/approvals", action: "Review" },
        have.has("reports.handle") && { id: "reports", icon: Flag, count: d.pending.open_reports, text: "reports need a decision", to: "/admin/reports", action: "Review" },
        have.has("mentors.decide") && { id: "mentors", icon: UserCheck, count: d.mentorship.pending_applications, text: "mentor applications are waiting", to: "/admin/mentors", action: "Review" },
        have.has("jobs.moderate") && { id: "jobs", icon: Briefcase, count: d.pending.jobs_awaiting_review, text: "jobs are waiting for review", to: "/admin/jobs", action: "Review" },
        have.has("editorial.manage") && { id: "wins", icon: Trophy, count: d.pending.wins_awaiting_review, text: "wins are waiting for review", to: "/admin/wins", action: "Review" },
        have.has("support.manage") && { id: "support", icon: LifeBuoy, count: d.pending.support_overdue, text: "support requests have waited past the reply time", to: "/admin/support?tab=open&sort=created", action: "Reply" },
        have.has("members.view") && { id: "unconfirmed", icon: Mail, count: d.pending.registrations_unverified, text: "sign ups have not confirmed their email", to: "/admin/members?status=pending", action: "See who" },
      ].filter(Boolean) as Attention[]).filter((x) => x.count > 0)
    : [];

  const refresh = () =>
    void guard(() => unwrap(api.POST("/api/v1/admin/dashboard/refresh"))).then(async () => {
      toast.show("Figures are being refreshed");
      await dash.refetch();
    });
  const exportCsv = () => {
    const url = URL.createObjectURL(new Blob([csvOf(points, current.label)], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${current.value}-${iso(w.today)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <PageHeader
        eyebrow="Console"
        title="Dashboard"
        lead={`${formatDate(w.thisStart)} to ${formatDate(w.today)}${d?.refreshed_at ? ` Â· figures updated ${timeAgo(d.refreshed_at)}` : ""}`}
        actions={
          <div className="adm-toolbar">
            <Button variant="secondary" onClick={refresh}>Refresh figures</Button>
            <Button variant="primary" onClick={exportCsv} icon={<Download size={16} strokeWidth={1.5} aria-hidden="true" />}>Export</Button>
          </div>
        }
      />

      {dash.isError ? <ErrorState error={dash.error} onRetry={() => void dash.refetch()} /> : null}

      <section className="adm-kpis" aria-label="Key figures">
        <KpiCard
          highlight
          loading={loading}
          label="Pending approvals"
          tag="Now"
          value={d ? n(d.pending.registrations_awaiting_approval) : "0"}
          to="/admin/approvals"
          rows={[
            { label: "Approved today", value: n(a.today) },
            { label: "Approved this month", value: n(a.thisMonth) },
            { label: "Email not confirmed", value: d ? n(d.pending.registrations_unverified) : "0" },
          ]}
        />
        <KpiCard
          loading={regs.isPending}
          label="New members"
          tag="Today"
          value={n(r.today)}
          delta={<Delta change={changeBetween(r.today, r.yesterday)} versus="on yesterday" />}
          to="/admin/members"
          rows={[
            { label: "Yesterday", value: n(r.yesterday) },
            { label: "This month", value: n(r.thisMonth) },
            { label: "Last month", value: n(r.lastMonth) },
          ]}
        />
        <KpiCard
          loading={loading || active.isPending}
          label="Active members, 7 days"
          tag="Week"
          value={d?.activity.weekly_active == null ? "Not yet" : n(d.activity.weekly_active)}
          to="/admin/members"
          rows={[
            { label: "Active today", value: n(act.today) },
            { label: "Active yesterday", value: n(act.yesterday) },
            { label: "Active in 30 days", value: d?.activity.monthly_active == null ? "Not yet" : n(d.activity.monthly_active) },
          ]}
        />
        <KpiCard
          loading={sessions.isPending}
          label="Session bookings"
          tag="Today"
          value={n(s.today)}
          delta={<Delta change={changeBetween(s.today, s.yesterday)} versus="on yesterday" />}
          rows={[
            { label: "Yesterday", value: n(s.yesterday) },
            { label: "This month", value: n(s.thisMonth) },
            { label: "Last month", value: n(s.lastMonth) },
          ]}
        />
      </section>

      <section className="adm-card adm-chartcard" aria-labelledby="dyn-title">
        <div className="adm-chartcard__head">
          <div>
            <h2 className="adm-card__title" id="dyn-title">Dynamics</h2>
            <p className="adm-card__sub">Daily {current.noun}, this month against last month</p>
          </div>
          <dl className="adm-totals" aria-label="Totals for the month so far">
            <div><dt><i className="adm-dotkey" data-series="current" />This month</dt><dd>{n(totals.thisMonth)}</dd></div>
            <div><dt><i className="adm-dotkey" data-series="previous" />Last month</dt><dd>{n(totals.lastMonth)}</dd></div>
          </dl>
        </div>
        <Segmented label="Measure" idPrefix="dyn" options={TABS.map((t) => ({ value: t.value, label: t.label }))} value={tab} onChange={setTab} />
        <div id="dyn-panel" role="tabpanel" aria-labelledby={`dyn-${tab}`}>
          <Loaded query={chart} skeleton={<SkeletonRows count={5} />}>
            {() => <BarChart title={current.label} points={points} currentLabel={monthName} previousLabel="Last month" format={n} />}
          </Loaded>
        </div>
      </section>

      {have.has("dashboard.view") ? <ReferralSection /> : null}

      <div className="adm-twocol">
        <AttentionCard items={attention} loading={loading} />
        <ActivityCard events={recent.data ?? []} loading={recent.isPending} viewAll={have.has("audit.read")} />
      </div>
    </>
  );
}
