import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, unwrap } from "../../api/client";
import { messageOf } from "../../api/errors";
import type { components } from "../../api/schema";
import { Alert, Button } from "../../components";

export type Job = components["schemas"]["TkJob"];

const POLL_MS = 1500;
const DONE = ["succeeded", "failed", "cancelled"];

/**
 * Follows a long running job until it ends. Pass the job's id; `onDone` runs once when it finishes.
 * The API answers 304 when nothing changed, so polling is cheap.
 */
export function useJob(jobId: string | null, onDone?: (job: Job) => void) {
  const fired = useRef<string | null>(null);
  const query = useQuery({
    queryKey: ["toolkit", "job", jobId],
    enabled: Boolean(jobId),
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/jobs/{job_id}", { params: { path: { job_id: jobId ?? "" } } })),
    refetchInterval: (q) => (q.state.data && DONE.includes(q.state.data.status) ? false : POLL_MS),
    staleTime: 0,
  });
  const job = query.data;
  useEffect(() => {
    if (job && DONE.includes(job.status) && fired.current !== job.id) {
      fired.current = job.id;
      onDone?.(job);
    }
  }, [job, onDone]);
  return {
    job,
    running: Boolean(jobId) && (!job || !DONE.includes(job.status)),
    failed: job?.status === "failed",
    error: query.error,
  };
}

/** Progress for a running job, with a way to stop it, and the reason if it failed. */
export function JobStatus({ job, error, onCancel }: { job: Job | undefined; error?: unknown; onCancel?: () => void }) {
  if (error) return <Alert tone="danger" title="We lost track of this job">{messageOf(error)}</Alert>;
  if (!job) return null;
  if (job.status === "failed") {
    return (
      <Alert tone="danger" title="That could not be finished">
        {job.error_detail || "Something went wrong. Please try again."}
      </Alert>
    );
  }
  if (job.status === "cancelled") return <Alert tone="info" title="Stopped" />;
  if (job.status === "succeeded") return null;
  return (
    <div className="app-stack" role="status" aria-live="polite">
      <p className="body-strong" style={{ margin: 0 }}>{job.step_label || "Getting started"}</p>
      <div className="app-meter" role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100} aria-label="Progress">
        <span style={{ width: `${Math.max(job.progress, 4)}%` }} />
      </div>
      {onCancel ? <div><Button size="sm" variant="ghost" onClick={onCancel}>Stop</Button></div> : null}
    </div>
  );
}

export async function cancelJob(jobId: string): Promise<void> {
  await unwrap(api.POST("/api/v1/toolkit/jobs/{job_id}/cancel", { params: { path: { job_id: jobId } } }));
}

/**
 * Starts an export job (the plan, a forecast, a deck), follows it, and opens the file when it is ready.
 * `start` posts to the export endpoint and returns the job it started.
 */
export function useExport(start: (format: string) => Promise<Job>) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState<unknown>(null);
  const tracked = useJob(jobId, (done) => {
    setJobId(null);
    const exportId = done.result?.id;
    if (done.status !== "succeeded" || typeof exportId !== "string") return;
    unwrap(api.GET("/api/v1/toolkit/exports/{export_id}", { params: { path: { export_id: exportId } } }))
      .then((file) => {
        const link = document.createElement("a");
        link.href = file.url;
        link.download = file.filename;
        link.rel = "noopener";
        document.body.append(link);
        link.click();
        link.remove();
      })
      .catch(setProblem);
  });
  const run = async (format: string) => {
    setStarting(true);
    setProblem(null);
    try {
      setJobId((await start(format)).id);
    } catch (error) {
      setProblem(error);
    } finally {
      setStarting(false);
    }
  };
  return { run, busy: starting || Boolean(jobId && tracked.running), job: tracked.job, jobId, error: problem ?? tracked.error };
}
