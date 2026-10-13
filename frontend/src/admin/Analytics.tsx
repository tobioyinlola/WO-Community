import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Button, Card } from "../components";
import { formatDate } from "../lib/format";
import { ErrorState, PageHeader, Skeleton, TableScroll, useDocumentTitle } from "../ui/blocks";
import { iso } from "./data/series";
import { BarChart, type DayPoint } from "./kit/BarChart";
import { changeBetween, Delta } from "./kit/Delta";
import { KpiCard } from "./kit/KpiCard";
import { Segmented } from "./kit/Segmented";

type Analytics = components["schemas"]["Analytics"];
type RangeKey = "7" | "30" | "90";

const RANGES: Array<{ value: RangeKey; label: string }> = [
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
];

function useAnalytics(days: RangeKey) {
  return useQuery({
    queryKey: ["admin", "analytics", days],
    refetchInterval: 60_000,
    queryFn: () => {
      const end = new Date();
      const start = new Date(end.getFullYear(), end.getMonth(), end.getDate() - (Number(days) - 1));
      return unwrap(api.GET("/api/v1/admin/analytics", { params: { query: { date_from: iso(start), date_to: iso(end) } } }));
    },
  });
}

function RangePicker({ value, onChange }: { value: RangeKey; onChange: (next: RangeKey) => void }) {
  return <Segmented label="Time range" options={RANGES} value={value} onChange={onChange} idPrefix="range" controls={false} />;
}

const short = (day: string) => formatDate(day).replace(/\s\d{4}$/, "");

function points(series: Analytics["series"][number]): DayPoint[] {
  return series.points.map((p) => ({ label: short(p.day), current: p.count, previous: p.previous }));
}

function Failed({ query }: { query: { error: unknown; refetch: () => unknown } }) {
  return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
}

export function AnalyticsOverview() {
  useDocumentTitle("Analytics");
  const [range, setRange] = useState<RangeKey>("30");
  const query = useAnalytics(range);
  const data = query.data;
  const [chartKey, setChartKey] = useState("members");
  const chosen = data?.series.find((s) => s.key === chartKey) ?? data?.series[0];
  return (
    <>
      <PageHeader eyebrow="Analytics" title="Overview" lead="How the community is growing and what people are doing, counted live from the platform." actions={<RangePicker value={range} onChange={setRange} />} />
      {query.isError ? <Failed query={query} /> : (
        <>
          <div className="adm-kpis">
            {(data?.stats ?? Array.from({ length: 7 }, () => null)).map((s, i) => (
              <KpiCard
                key={s?.key ?? i}
                loading={!s}
                label={s?.title ?? ""}
                value={s ? s.value.toLocaleString("en-NG") : ""}
                delta={s ? <Delta change={changeBetween(s.value, s.previous)} versus="on the period before" /> : undefined}
                rows={s ? [{ label: "Period before", value: s.previous.toLocaleString("en-NG") }] : []}
                highlight={i === 0}
              />
            ))}
          </div>
          <Card style={{ marginTop: "var(--space-6)" }}>
            <div className="app-cluster" style={{ justifyContent: "space-between", marginBottom: "var(--space-4)" }}>
              <h2 className="h4" style={{ margin: 0 }}>{chosen?.title ?? "Activity"} each day</h2>
              <Segmented
                label="Measure"
                idPrefix="measure"
                controls={false}
                value={chartKey}
                onChange={setChartKey}
                options={(data?.series ?? []).filter((s) => ["members", "posts", "comments", "sessions"].includes(s.key)).map((s) => ({ value: s.key, label: s.title }))}
              />
            </div>
            {chosen && data ? (
              <BarChart title={chosen.title} points={points(chosen)} currentLabel="This period" previousLabel="Period before" />
            ) : <Skeleton height={220} />}
          </Card>
        </>
      )}
    </>
  );
}

export function AnalyticsFunnels() {
  useDocumentTitle("Funnels");
  const [range, setRange] = useState<RangeKey>("30");
  const query = useAnalytics(range);
  const funnel = query.data?.funnel ?? [];
  const top = Math.max(1, funnel[0]?.count ?? 0);
  return (
    <>
      <PageHeader eyebrow="Analytics" title="Funnels" lead="Of the people who signed up in this period, how far did they get?" actions={<RangePicker value={range} onChange={setRange} />} />
      {query.isError ? <Failed query={query} /> : (
        <Card>
          <h2 className="h4" style={{ margin: "0 0 var(--space-5)" }}>From sign up to taking part</h2>
          {query.isPending ? <Skeleton height={180} /> : funnel[0]?.count === 0 ? (
            <p className="body" style={{ margin: 0 }}>Nobody signed up in this period, so there is no funnel to show. Try a longer range.</p>
          ) : (
            <ol className="adm-funnel">
              {funnel.map((step, i) => {
                const share = Math.round((step.count / top) * 100);
                const prev = funnel[i - 1];
                const drop = prev && prev.count > 0 ? Math.round(((prev.count - step.count) / prev.count) * 100) : null;
                return (
                  <li key={step.name} className="adm-funnel__step">
                    <div className="adm-funnel__head">
                      <span>{step.name}</span>
                      <strong>{step.count.toLocaleString("en-NG")} <span className="app-muted">({share}%)</span></strong>
                    </div>
                    <div className="adm-funnel__track" role="img" aria-label={`${step.name}: ${step.count} people, ${share} percent of those who signed up`}>
                      <div className="adm-funnel__bar" style={{ width: `${Math.max(share, step.count > 0 ? 2 : 0)}%` }} />
                    </div>
                    {drop !== null && drop > 0 ? <p className="caption app-muted" style={{ margin: "4px 0 0" }}>{drop}% fewer than the step before</p> : null}
                  </li>
                );
              })}
            </ol>
          )}
        </Card>
      )}
    </>
  );
}

function toCsv(data: Analytics): string {
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
  const lines: string[] = [["Section", "Name", "Value", "Previous period"].map(esc).join(",")];
  for (const s of data.stats) lines.push(["Totals", s.title, s.value, s.previous].map(esc).join(","));
  for (const b of data.breakdowns) for (const r of b.rows) lines.push([b.title, r.name, r.count, ""].map(esc).join(","));
  for (const f of data.funnel) lines.push(["Funnel", f.name, f.count, ""].map(esc).join(","));
  lines.push("");
  lines.push(["Day", ...data.series.map((s) => s.title)].map(esc).join(","));
  const days = data.series[0]?.points ?? [];
  days.forEach((d, i) => lines.push([d.day, ...data.series.map((s) => s.points[i]?.count ?? 0)].map(esc).join(",")));
  return lines.join("\n");
}

export function AnalyticsReports() {
  useDocumentTitle("Reports");
  const [range, setRange] = useState<RangeKey>("30");
  const query = useAnalytics(range);
  const data = query.data;
  const csv = useMemo(() => (data ? toCsv(data) : ""), [data]);
  const download = () => {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `wo-community-report-${data.start}-to-${data.end}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <>
      <PageHeader
        eyebrow="Analytics"
        title="Reports"
        lead={data ? `Who is here and what they do, ${formatDate(data.start)} to ${formatDate(data.end)}.` : "Who is here and what they do."}
        actions={
          <div className="app-cluster">
            <RangePicker value={range} onChange={setRange} />
            <Button variant="secondary" disabled={!data} onClick={download}><Download size={16} strokeWidth={1.5} aria-hidden="true" /> Download CSV</Button>
          </div>
        }
      />
      {query.isError ? <Failed query={query} /> : (
        <div className="adm-reportgrid">
          {(data?.breakdowns ?? []).map((b) => {
            const max = Math.max(1, ...b.rows.map((r) => r.count));
            return (
              <Card key={b.key}>
                <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>{b.title}</h2>
                {b.rows.length === 0 ? <p className="body-sm app-muted" style={{ margin: 0 }}>Nothing to show yet.</p> : (
                  <TableScroll label={b.title}>
                    <table className="adm-miniTable">
                      <caption className="wo-visually-hidden">{b.title}</caption>
                      <tbody>
                        {b.rows.map((r) => (
                          <tr key={r.name}>
                            <th scope="row">{r.name.length === 2 && r.name === r.name.toUpperCase() ? r.name : r.name.replace(/_/g, " ")}</th>
                            <td className="adm-miniTable__bar"><span style={{ width: `${(r.count / max) * 100}%` }} /></td>
                            <td className="adm-miniTable__n">{r.count.toLocaleString("en-NG")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </TableScroll>
                )}
              </Card>
            );
          })}
          {query.isPending ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} height={160} />) : null}
        </div>
      )}
    </>
  );
}
