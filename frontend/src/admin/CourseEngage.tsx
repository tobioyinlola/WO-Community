import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Button, Input, Textarea } from "../components";
import { formatDate, formatDateTime, plural } from "../lib/format";
import { TableScroll, EmptyState, ErrorState, Loaded, LoadMore, RichText, SkeletonRows } from "../ui/blocks";
import { DownloadButton } from "../ui/DownloadButton";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { ConfirmDialog } from "./dialogs";
import { StatusChip } from "./kit/TableBits";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Request = components["schemas"]["AdminAccessRequest"];
type Learner = components["schemas"]["AdminLearner"];
type Question = components["schemas"]["AdminQuestion"];

/** Everyone enrolled, how far they have got, with the list as a spreadsheet and a way to remove someone. */
export function Learners({ courseId, slug }: { courseId: string; slug: string }) {
  const client = useQueryClient();
  const guard = useStepUp();
  const toast = useToast();
  const [removing, setRemoving] = useState<Learner | null>(null);
  const list = useOffsetList<Learner>(["admin", "course", courseId, "learners"], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/courses/{course_id}/learners", { params: { path: { course_id: courseId }, query: { limit, offset } } })),
  );
  if (list.query.isPending) return <SkeletonRows />;
  if (list.query.isError) return <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />;
  return (
    <div className="app-stack">
      <div className="app-cluster" style={{ justifyContent: "space-between" }}>
        <p className="body-sm app-muted" style={{ margin: 0 }}>
          {plural(list.items.length, "learner")}
          {list.hasNext ? " so far" : ""}
        </p>
        <DownloadButton variant="secondary" size="sm" path={`/api/v1/admin/courses/${courseId}/learners.csv`} filename={`learners-${slug}.csv`}>
          Download CSV
        </DownloadButton>
      </div>
      {list.isEmpty ? (
        <EmptyState title="No learners yet">People who enrol appear here.</EmptyState>
      ) : (
        <TableScroll label="Learners">
          <table className="app-table">
            <thead>
              <tr>
                <th scope="col">Learner</th>
                <th scope="col">How they joined</th>
                <th scope="col">Started</th>
                <th scope="col">Progress</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {list.items.map((l) => (
                <tr key={l.user_id}>
                  <th scope="row">
                    {l.name}
                    <div className="caption app-muted">{l.email}</div>
                  </th>
                  <td>{l.origin === "request" ? "Approved request" : l.origin === "granted" ? "Granted" : "Enrolled"}</td>
                  <td>{formatDate(l.started_at)}</td>
                  <td>{l.completed_at ? `Completed ${formatDate(l.completed_at)}` : `${l.percent}%`}</td>
                  <td>
                    <Button size="sm" variant="ghost" onClick={() => setRemoving(l)} aria-label={`Remove ${l.name} from this course`}>
                      Remove
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      )}
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
      {removing ? (
        <ConfirmDialog
          title="Remove this learner?"
          body={`${removing.name} loses their progress on this course. A certificate they already earned stays valid.`}
          confirmLabel="Remove"
          tone="danger"
          onConfirm={async () => {
            await guard(() => unwrap(api.DELETE("/api/v1/admin/courses/{course_id}/learners/{user_id}", { params: { path: { course_id: courseId, user_id: removing.user_id } } })));
            toast.show("Learner removed");
            await client.invalidateQueries({ queryKey: ["admin", "course", courseId] });
          }}
          onClose={() => setRemoving(null)}
        />
      ) : null}
    </div>
  );
}

/** Requests for access while payments are off: approve to give the course, or decline. Both tell the member. */
export function Requests({ courseId }: { courseId: string | null }) {
  const client = useQueryClient();
  const guard = useStepUp();
  const toast = useToast();
  const [state, setState] = useState<"pending" | "approved" | "rejected">("pending");
  const list = useOffsetList<Request>(["admin", "course-requests", courseId ?? "all", state], (offset, limit) =>
    courseId
      ? unwrap(api.GET("/api/v1/admin/courses/{course_id}/requests", { params: { path: { course_id: courseId }, query: { status: state, limit, offset } } }))
      : unwrap(api.GET("/api/v1/admin/course-requests", { params: { query: { status: state, limit, offset } } })),
  );
  const decide = async (r: Request, approve: boolean) => {
    const path = { params: { path: { request_id: r.id } } };
    await guard(() => (approve ? unwrap(api.POST("/api/v1/admin/course-requests/{request_id}/approve", path)) : unwrap(api.POST("/api/v1/admin/course-requests/{request_id}/decline", path))));
    toast.show(approve ? `${r.user.name} now has the course` : "Request declined");
    await client.invalidateQueries({ queryKey: ["admin", "course-requests"] });
    await client.invalidateQueries({ queryKey: ["admin", "courses"] });
  };
  return (
    <div className="app-stack">
      <div className="app-cluster" role="group" aria-label="Which requests">
        {(["pending", "approved", "rejected"] as const).map((s) => (
          <Button key={s} size="sm" variant={state === s ? "primary" : "secondary"} aria-pressed={state === s} onClick={() => setState(s)}>
            {s === "pending" ? "Waiting" : s === "approved" ? "Approved" : "Declined"}
          </Button>
        ))}
      </div>
      {list.query.isPending ? <SkeletonRows /> : null}
      {list.query.isError ? <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} /> : null}
      {list.isEmpty ? <EmptyState title={state === "pending" ? "Nothing waiting" : "No requests here"}>Requests for paid courses appear here while payments are off.</EmptyState> : null}
      <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {list.items.map((r) => (
          <li key={r.id} className="wo-row-card">
            <div>
              <strong>{r.user.name}</strong> <span className="caption app-muted">{r.user.email}</span>
              {courseId ? null : <div className="body-sm">{r.course.title}</div>}
              {r.message ? <p className="body-sm" style={{ margin: "var(--space-1) 0 0" }}>“{r.message}”</p> : null}
              <div className="caption app-muted">Asked {formatDateTime(r.created_at)}</div>
            </div>
            {r.status === "pending" ? (
              <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
                <Button size="sm" onClick={() => void decide(r, true)} aria-label={`Approve ${r.user.name}`}>
                  Approve
                </Button>
                <Button size="sm" variant="secondary" onClick={() => void decide(r, false)} aria-label={`Decline ${r.user.name}`}>
                  Decline
                </Button>
              </div>
            ) : (
              <StatusChip tone={r.status === "approved" ? "success" : "neutral"}>{r.status === "approved" ? "Approved" : "Declined"}</StatusChip>
            )}
          </li>
        ))}
      </ul>
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
    </div>
  );
}

async function setHidden(kind: "reviews" | "questions" | "answers", id: string, hide: boolean) {
  const path = { params: { path: { item_id: id } } };
  if (kind === "reviews") return unwrap(hide ? api.POST("/api/v1/admin/reviews/{item_id}/hide", path) : api.POST("/api/v1/admin/reviews/{item_id}/restore", path));
  if (kind === "questions") return unwrap(hide ? api.POST("/api/v1/admin/questions/{item_id}/hide", path) : api.POST("/api/v1/admin/questions/{item_id}/restore", path));
  return unwrap(hide ? api.POST("/api/v1/admin/answers/{item_id}/hide", path) : api.POST("/api/v1/admin/answers/{item_id}/restore", path));
}

export function Reviews({ courseId }: { courseId: string }) {
  const client = useQueryClient();
  const guard = useStepUp();
  const key = ["admin", "course", courseId, "reviews"];
  const query = useQuery({ queryKey: key, queryFn: () => unwrap(api.GET("/api/v1/admin/courses/{course_id}/reviews", { params: { path: { course_id: courseId } } })) });
  return (
    <Loaded query={query} skeleton={<SkeletonRows />} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No reviews yet">Learners can review once they are a quarter of the way through.</EmptyState>}>
      {(items) => (
        <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {items.map((r) => (
            <li key={r.id} className="wo-row-card" data-hidden={r.hidden}>
              <div>
                <strong>{r.reviewer}</strong> <span aria-label={`${r.stars} out of 5 stars`}>{r.stars}/5</span> <span className="caption app-muted">{formatDate(r.created_at)}</span>
                {r.hidden ? <StatusChip>Hidden</StatusChip> : null}
                <p className="body-sm" style={{ margin: "var(--space-1) 0 0" }}>
                  {r.feedback || "No written feedback."}
                </p>
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={async () => {
                  await guard(() => setHidden("reviews", r.id, !r.hidden));
                  await client.invalidateQueries({ queryKey: key });
                }}
                aria-label={`${r.hidden ? "Restore" : "Hide"} the review by ${r.reviewer}`}
              >
                {r.hidden ? "Restore" : "Hide"}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Loaded>
  );
}

function Answering({ question, onDone }: { question: Question; onDone: () => Promise<void> }) {
  const [body, setBody] = useState("");
  const send = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/admin/questions/{question_id}/answer", { params: { path: { question_id: question.id } }, body: { body: body.trim() } }));
    setBody("");
    await onDone();
  });
  return (
    <div className="app-stack">
      <FormError error={send.error} />
      <Textarea label="Answer as course staff" rows={3} value={body} onChange={(e) => setBody(e.target.value)} />
      <div>
        <Button size="sm" loading={send.busy} disabled={!body.trim()} onClick={() => void send.run()}>
          Post answer
        </Button>
      </div>
    </div>
  );
}

export function Questions({ courseId }: { courseId: string }) {
  const client = useQueryClient();
  const guard = useStepUp();
  const key = ["admin", "course", courseId, "questions"];
  const query = useQuery({ queryKey: key, queryFn: () => unwrap(api.GET("/api/v1/admin/courses/{course_id}/questions", { params: { path: { course_id: courseId } } })) });
  const refresh = () => client.invalidateQueries({ queryKey: key });
  return (
    <Loaded query={query} skeleton={<SkeletonRows />} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No questions yet">Questions learners ask on a lecture appear here.</EmptyState>}>
      {(items) => (
        <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {items.map((q) => (
            <li key={q.id} className="wo-qa__item" data-hidden={q.hidden}>
              <p className="wo-qa__who">
                <strong>{q.asker}</strong> on {q.lecture} · {formatDateTime(q.created_at)} {q.hidden ? <StatusChip>Hidden</StatusChip> : null}
              </p>
              <p className="wo-qa__body">{q.body}</p>
              {q.answers.length ? (
                <ul className="wo-qa__answers">
                  {q.answers.map((a) => (
                    <li key={a.id}>
                      <p className="wo-qa__who">
                        <strong>{a.author}</strong>
                        {a.is_staff ? <span className="wo-qa__badge">Staff</span> : null} · {formatDateTime(a.created_at)} {a.hidden ? <StatusChip>Hidden</StatusChip> : null}
                      </p>
                      <p className="wo-qa__body">{a.body}</p>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={async () => {
                          await guard(() => setHidden("answers", a.id, !a.hidden));
                          await refresh();
                        }}
                        aria-label={`${a.hidden ? "Restore" : "Hide"} the answer by ${a.author}`}
                      >
                        {a.hidden ? "Restore" : "Hide"}
                      </Button>
                    </li>
                  ))}
                </ul>
              ) : null}
              <Answering question={q} onDone={refresh} />
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  await guard(() => setHidden("questions", q.id, !q.hidden));
                  await refresh();
                }}
                aria-label={`${q.hidden ? "Restore" : "Hide"} the question by ${q.asker}`}
              >
                {q.hidden ? "Restore question" : "Hide question"}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Loaded>
  );
}

export function Announcements({ courseId }: { courseId: string }) {
  const client = useQueryClient();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const key = ["admin", "course", courseId, "announcements"];
  const query = useQuery({ queryKey: key, queryFn: () => unwrap(api.GET("/api/v1/admin/courses/{course_id}/announcements", { params: { path: { course_id: courseId } } })) });
  const post = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/admin/courses/{course_id}/announcements", { params: { path: { course_id: courseId } }, body: { title: title.trim(), body: body.trim() } }));
    setTitle("");
    setBody("");
    toast.show("Announcement sent to every learner");
    await client.invalidateQueries({ queryKey: key });
  });
  const errors = errorsFrom(post.error).fields;
  return (
    <div className="app-stack">
      <div className="app-stack">
        <FormError error={post.error} />
        <Input label="Title" value={title} maxLength={160} onChange={(e) => setTitle(e.target.value)} error={errors.title} />
        <Textarea label="Message" rows={4} hint="Every enrolled learner is told, in the app and by email." value={body} onChange={(e) => setBody(e.target.value)} error={errors.body} />
        <div>
          <Button loading={post.busy} disabled={!title.trim() || !body.trim()} onClick={() => void post.run()}>
            Post announcement
          </Button>
        </div>
      </div>
      <Loaded query={query} skeleton={<SkeletonRows />} isEmpty={(d) => d.length === 0} empty={<p className="body-sm app-muted">Nothing posted yet.</p>}>
        {(items) => (
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {items.map((a) => (
              <li key={a.id} className="wo-row-card">
                <div>
                  <strong>{a.title}</strong> <span className="caption app-muted">{formatDateTime(a.created_at)}</span>
                  <RichText html={a.body} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Loaded>
    </div>
  );
}
