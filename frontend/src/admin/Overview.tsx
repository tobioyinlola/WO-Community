import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Badge, Button, Card, Select, StatTile } from "../components";
import { formatDate, formatDateTime, humanise } from "../lib/format";
import { Loaded, PageHeader, SkeletonCards, useDocumentTitle, TableScroll } from "../ui/blocks";
import { useStepUp } from "./StepUp";

type QueueKey = "registrations_awaiting_approval" | "registrations_unverified" | "open_reports" | "jobs_awaiting_review" | "wins_awaiting_review";

const QUEUES: Array<{ key: QueueKey; label: string; to: string }> = [
  { key: "registrations_awaiting_approval", label: "Waiting for approval", to: "/admin/members?status=pending" },
  { key: "open_reports", label: "Open reports", to: "/admin/reports" },
  { key: "jobs_awaiting_review", label: "Jobs to review", to: "/admin/jobs" },
  { key: "wins_awaiting_review", label: "Wins to review", to: "/admin/wins" },
  { key: "registrations_unverified", label: "Email not confirmed", to: "/admin/members?status=pending" },
];

const num = (v: number | null | undefined) => (v === null || v === undefined ? "Not available" : v.toLocaleString("en-NG"));
const pct = (v: number | null | undefined) => (v === null || v === undefined ? "Not available" : `${Math.round(v * 100)}%`);

/** One metric over the last 30 days as a line, with the numbers behind it for anyone who prefers them. */
function Trend({ metric }: { metric: string }) {
  const series = useQuery({
    queryKey: ["admin", "series", metric],
    queryFn: () => unwrap(api.GET("/api/v1/admin/dashboard/series", { params: { query: { metric } } })),
  });
  return (
    <Loaded query={series} skeleton={<p className="body app-muted">Loading…</p>}>
      {(s) => {
        const points = s.points.map((p) => p.value ?? 0);
        const max = Math.max(...points, 1);
        const W = 640;
        const H = 140;
        const x = (i: number) => (i / Math.max(points.length - 1, 1)) * W;
        const y = (v: number) => H - (v / max) * (H - 8) - 4;
        const path = points.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
        return (
          <figure style={{ margin: 0 }}>
            <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${humanise(metric)} each day over ${s.points.length} days, highest ${max}`} style={{ width: "100%", height: "auto", display: "block" }}>
              <path d={path} fill="none" stroke="var(--accent-fill)" strokeWidth="3" />
            </svg>
            <figcaption className="caption app-muted">
              {s.description} {s.total !== null ? `Total in this period: ${s.total.toLocaleString("en-NG")}.` : ""}
            </figcaption>
            <details>
              <summary className="caption">See the numbers</summary>
              <TableScroll label="Daily values">
                <table className="app-table">
                  <thead><tr><th scope="col">Day</th><th scope="col">Value</th></tr></thead>
                  <tbody>
                    {s.points.slice(-14).map((p) => (
                      <tr key={p.date}><th scope="row">{formatDate(p.date)}</th><td>{p.value ?? "None"}</td></tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
            </details>
          </figure>
        );
      }}
    </Loaded>
  );
}

export default function Overview() {
  useDocumentTitle("Console overview");
  const guard = useStepUp();
  const [metric, setMetric] = useState("registrations");
  const dash = useQuery({ queryKey: ["admin", "dashboard"], queryFn: () => unwrap(api.GET("/api/v1/admin/dashboard")) });
  const metrics = useQuery({ queryKey: ["admin", "metrics"], queryFn: () => unwrap(api.GET("/api/v1/admin/dashboard/metrics")), staleTime: 3_600_000 });
  return (
    <>
      <PageHeader
        eyebrow="Console"
        title="Overview"
        lead="What needs a decision, and how the community is doing."
        actions={<Button variant="secondary" onClick={() => void guard(() => unwrap(api.POST("/api/v1/admin/dashboard/refresh"))).then(() => dash.refetch())}>Refresh figures</Button>}
      />
      <Loaded query={dash} skeleton={<SkeletonCards count={4} />}>
        {(d) => (
          <div className="app-stack app-stack--lg">
            <section aria-label="Waiting for you">
              <div className="app-grid">
                {QUEUES.map((q) => (
                  <Link key={q.key} to={q.to} className="wo-card" style={{ textDecoration: "none" }}>
                    <p className="caption app-muted" style={{ margin: 0 }}>{q.label}</p>
                    <p className="h2" style={{ margin: "var(--space-1) 0 0" }}>{d.pending[q.key]}</p>
                  </Link>
                ))}
              </div>
              <p className="caption app-faint" style={{ margin: "var(--space-2) 0 0" }}>
                {d.refreshed_at ? `Figures last updated ${formatDateTime(d.refreshed_at)}.` : "Figures have not been calculated yet."}
              </p>
            </section>

            <section aria-label="Trend">
              <div className="app-cluster" style={{ justifyContent: "space-between", marginBottom: "var(--space-3)" }}>
                <h2 className="h3" style={{ margin: 0 }}>Last 30 days</h2>
                <Select label="Measure" options={(metrics.data ?? []).map((m) => ({ value: m.metric, label: humanise(m.metric) }))} value={metric} onChange={(e) => setMetric(e.target.value)} />
              </div>
              <Card><Trend metric={metric} /></Card>
            </section>

            <section aria-label="Community">
              <h2 className="h3" style={{ margin: "0 0 var(--space-3)" }}>Community</h2>
              <div className="app-grid">
                <StatTile label="Active members" value={num(d.community.active_members)} />
                <StatTile label="Joined in 30 days" value={num(d.community.registered_last_30_days)} />
                <StatTile label="Growth on the 30 days before" value={pct(d.community.growth)} />
                <StatTile label="Weekly active" value={num(d.activity.weekly_active)} />
                <StatTile label="Posts this week" value={num(d.activity.posts_last_7_days)} />
                <StatTile label="Jobs live" value={num(d.activity.jobs_live)} />
              </div>
              <div className="app-split app-split--even" style={{ marginTop: "var(--space-4)" }}>
                <Card>
                  <h3 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Where members are</h3>
                  <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0, gap: "var(--space-2)" }}>
                    {d.community.by_country.slice(0, 6).map((c) => (
                      <li key={c.name} className="app-cluster" style={{ justifyContent: "space-between" }}><span>{c.name}</span><Badge variant="neutral">{c.count}</Badge></li>
                    ))}
                  </ul>
                </Card>
                <Card>
                  <h3 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Startups by sector</h3>
                  <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0, gap: "var(--space-2)" }}>
                    {d.community.startups_by_sector.slice(0, 6).map((c) => (
                      <li key={c.name} className="app-cluster" style={{ justifyContent: "space-between" }}><span>{c.name}</span><Badge variant="neutral">{c.count}</Badge></li>
                    ))}
                  </ul>
                </Card>
              </div>
            </section>

            {d.mentorship.available ? (
              <section aria-label="Mentoring">
                <h2 className="h3" style={{ margin: "0 0 var(--space-3)" }}>Mentoring</h2>
                <div className="app-grid">
                  <StatTile label="Applications waiting" value={num(d.mentorship.pending_applications)} />
                  <StatTile label="Active mentors" value={num(d.mentorship.active_mentors)} />
                  <StatTile label="Requests waiting" value={num(d.mentorship.requests_waiting)} />
                  <StatTile label="Unanswered over 48 hours" value={num(d.mentorship.unanswered_over_48h)} />
                  <StatTile label="Sessions in 30 days" value={num(d.mentorship.sessions_held_30d)} />
                  <StatTile label="Average rating" value={d.mentorship.average_rating === null ? "Not available" : d.mentorship.average_rating.toFixed(1)} />
                </div>
              </section>
            ) : null}

            {d.learning.available ? (
              <section aria-label="Learning">
                <h2 className="h3" style={{ margin: "0 0 var(--space-3)" }}>Learning</h2>
                <div className="app-grid">
                  <StatTile label="Published courses" value={num(d.learning.published_courses)} />
                  <StatTile label="Enrolments" value={num(d.learning.enrolments)} />
                  <StatTile label="Completion rate" value={pct(d.learning.completion_rate)} />
                  <StatTile label="Certificates" value={num(d.learning.certificates)} />
                </div>
              </section>
            ) : null}
          </div>
        )}
      </Loaded>
    </>
  );
}
