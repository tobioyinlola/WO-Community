import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { isStatus } from "../../api/errors";
import { Alert, Badge, Button, Card } from "../../components";
import { formatDate, humanise } from "../../lib/format";
import { EmptyState, Loaded, SkeletonRows } from "../../ui/blocks";
import { FormError, useSubmit } from "../../ui/forms";
import { JobStatus, cancelJob, useJob } from "./jobs";
import { packageKey, useWorkspace } from "./Workspace";

export default function ScoreTab() {
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const latest = useQuery({
    queryKey: ["toolkit", ventureId, "score", "latest"],
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/score/latest", { params: { path: { venture_id: ventureId } } }));
      } catch (error) {
        if (isStatus(error, 404)) return null;
        throw error;
      }
    },
  });
  const history = useQuery({
    queryKey: ["toolkit", ventureId, "score", "history"],
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/score/history", { params: { path: { venture_id: ventureId } } })),
  });
  const running = useJob(jobId, () => {
    void client.invalidateQueries({ queryKey: ["toolkit", ventureId] });
    setJobId(null);
  });
  const start = useSubmit(async () => {
    const job = await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/score", { params: { path: { venture_id: ventureId } } }));
    setJobId(job.id);
    await client.invalidateQueries({ queryKey: packageKey(ventureId) });
  });
  const busy = start.busy || Boolean(jobId && running.running);

  return (
    <div className="app-stack app-stack--lg">
      <div className="app-cluster" style={{ justifyContent: "space-between" }}>
        <p className="body app-muted" style={{ margin: 0, maxWidth: "60ch" }}>
          The score reads your profile against a set of criteria and says what would make the idea stronger. It is guidance, not a verdict.
        </p>
        <Button onClick={() => void start.run()} loading={busy}>{latest.data ? "Score it again" : "Score my idea"}</Button>
      </div>
      <FormError error={start.error} />
      {jobId ? <JobStatus job={running.job} error={running.error} onCancel={() => void cancelJob(jobId)} /> : null}
      <Loaded
        query={latest}
        skeleton={<SkeletonRows />}
        isEmpty={(d) => !d}
        empty={
          <EmptyState title="No score yet">
            Fill in the profile, then score it. If something required is missing we tell you what.
            <div style={{ marginTop: "var(--space-3)" }}><Link className="wo-btn wo-btn--secondary wo-btn--sm" to="../profile">Open the profile</Link></div>
          </EmptyState>
        }
      >
        {(report) => {
          if (!report) return null;
          return (
            <div className="app-stack app-stack--lg">
              <Card variant="brand">
                <p className="eyebrow" style={{ margin: 0 }}>Overall</p>
                <p className="display-sm" style={{ margin: "var(--space-2) 0" }}>{report.overall_score === null ? "Not enough information" : `${Math.round(report.overall_score)} / 100`}</p>
                <p className="body" style={{ margin: 0 }}>{report.verdict}</p>
                <p className="caption" style={{ margin: "var(--space-3) 0 0" }}>Scored {formatDate(report.created_at)}</p>
              </Card>
              {report.explanation ? <p className="body" style={{ margin: 0, maxWidth: "70ch" }}>{report.explanation}</p> : null}
              <section aria-label="Dimensions">
                <h2 className="h3" style={{ margin: "0 0 var(--space-3)" }}>How each area did</h2>
                <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {report.dimensions.map((d) => (
                    <li key={d.key}>
                      <Card>
                        <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                          <h3 className="h4" style={{ margin: 0 }}>{d.label}</h3>
                          {d.status === "scored" && d.score !== null ? <Badge variant="neutral">{Math.round(d.score)} / 100</Badge> : <Badge variant="warning">Need more information</Badge>}
                        </div>
                        {d.status === "scored" && d.score !== null ? (
                          <div className="app-meter" style={{ margin: "var(--space-3) 0" }} role="progressbar" aria-valuenow={Math.round(d.score)} aria-valuemin={0} aria-valuemax={100} aria-label={`${d.label} score`}><span style={{ width: `${d.score}%` }} /></div>
                        ) : null}
                        <p className="body-sm" style={{ margin: "var(--space-2) 0 0" }}>{d.reason}</p>
                        {d.next_step ? <p className="body-sm app-muted" style={{ margin: "var(--space-2) 0 0" }}>Next: {d.next_step}</p> : null}
                        {d.evidence.length > 0 ? (
                          <details style={{ marginTop: "var(--space-3)" }}>
                            <summary>What this is based on</summary>
                            <ul>{d.evidence.map((e, i) => <li key={i} className="body-sm">{e.text}{e.source_name ? <span className="app-muted"> ({e.source_name})</span> : null}</li>)}</ul>
                          </details>
                        ) : null}
                      </Card>
                    </li>
                  ))}
                </ul>
              </section>
              <div className="app-split">
                <Card>
                  <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Strengths</h2>
                  {report.strengths.length === 0 ? <p className="body-sm app-muted">None stood out yet.</p> : <ul>{report.strengths.map((s, i) => <li key={i} className="body-sm"><strong>{s.label}.</strong> {s.text}</li>)}</ul>}
                </Card>
                <Card>
                  <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Gaps</h2>
                  {report.gaps.length === 0 ? <p className="body-sm app-muted">No clear gaps.</p> : <ul>{report.gaps.map((s, i) => <li key={i} className="body-sm"><strong>{s.label}.</strong> {s.text}</li>)}</ul>}
                </Card>
              </div>
              {report.next_actions.length > 0 ? (
                <section aria-label="What to do next">
                  <h2 className="h3" style={{ margin: "0 0 var(--space-3)" }}>Best next steps</h2>
                  <ul className="app-list">
                    {report.next_actions.map((a, i) => (
                      <li key={i}>
                        <Link className="app-list__item" to={a.action?.type === "open_forecast" ? "../forecast" : "../profile"}>
                          <div className="app-list__main">
                            <p className="app-list__title">{a.text}</p>
                            <p className="app-list__meta">{a.label}{a.estimated_points ? `, about ${a.estimated_points} points` : ""}</p>
                          </div>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
              {report.disclaimer ? <Alert tone="info" title="Please note">{report.disclaimer}</Alert> : null}
            </div>
          );
        }}
      </Loaded>
      {history.data && history.data.length > 1 ? (
        <section aria-label="Earlier scores">
          <h2 className="h3" style={{ margin: "0 0 var(--space-3)" }}>Earlier scores</h2>
          <ul className="app-list">
            {history.data.map((h) => (
              <li key={h.id}><div className="app-list__item"><div className="app-list__main"><p className="app-list__title">{h.overall_score === null ? "Not enough information" : `${Math.round(h.overall_score)} / 100`}</p><p className="app-list__meta">{formatDate(h.created_at)} &middot; {humanise(h.verdict)}</p></div></div></li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
