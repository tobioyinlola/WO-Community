import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Button, Input, Select } from "../components";
import { formatDate, formatMoney, humanise } from "../lib/format";
import { TableScroll, EmptyState, ErrorState, LoadMore, PageHeader, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { AddCourse } from "./AddCourse";
import { Segmented } from "./kit/Segmented";
import { StatStrip, StatusChip } from "./kit/TableBits";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Course = components["schemas"]["AdminCourse"];
type Status = "" | "draft" | "published" | "unlisted";

const TABS: Array<{ value: Status; label: string }> = [
  { value: "", label: "All" },
  { value: "published", label: "Published" },
  { value: "unlisted", label: "Unlisted" },
  { value: "draft", label: "Drafts" },
];

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Every course in any state, with what needs attention, and the Add course drawer. */
export default function Courses() {
  useDocumentTitle("Courses");
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = (TABS.some((t) => t.value === params.get("status")) ? params.get("status") : "") as Status;
  const access = params.get("access") ?? "";
  const [q, setQ] = useState(params.get("q") ?? "");
  const query = useDebounced(q.trim());
  const adding = params.get("new") === "1";

  const patch = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setParams(next, { replace: true });
  };
  useEffect(() => {
    if (query !== (params.get("q") ?? "")) patch({ q: query });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const list = useOffsetList<Course>(["admin", "courses", status, access, query], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/courses", { params: { query: { limit, offset, ...(status ? { status } : {}), ...(access ? { access: access as "free" } : {}), ...(query ? { q: query } : {}) } } })),
  );
  const requests = useQuery({ queryKey: ["admin", "course-requests", "pending"], queryFn: () => unwrap(api.GET("/api/v1/admin/course-requests", { params: { query: { status: "pending", limit: 1 } } })) });
  const all = useQuery({ queryKey: ["admin", "courses", "tiles"], queryFn: () => unwrap(api.GET("/api/v1/admin/courses", { params: { query: { limit: 100 } } })) });
  const tiles = all.data?.results ?? [];
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "courses"] });

  const duplicate = async (c: Course) => {
    await guard(() => unwrap(api.POST("/api/v1/admin/courses/{course_id}/duplicate", { params: { path: { course_id: c.id } } })));
    toast.show("Copy created as a draft");
    await refresh();
  };

  return (
    <>
      <PageHeader
        eyebrow="Content"
        title="Courses"
        lead="Build learning for the community."
        actions={
          <>
            <Link className="wo-btn wo-btn--secondary" to="/admin/course-requests">
              Enrolment requests{requests.data?.count ? ` (${requests.data.count})` : ""}
            </Link>
            <Button onClick={() => patch({ new: "1" })}>
              <Plus size={16} strokeWidth={1.5} aria-hidden="true" /> Add course
            </Button>
          </>
        }
      />
      <StatStrip
        loading={all.isPending}
        items={[
          { label: "Courses", value: String(all.data?.count ?? 0) },
          { label: "Published", value: String(tiles.filter((c) => c.status === "published").length) },
          { label: "Drafts", value: String(tiles.filter((c) => c.status === "draft").length) },
          { label: "Learners", value: String(tiles.reduce((n, c) => n + c.learners_count, 0)) },
          { label: "Requests waiting", value: String(requests.data?.count ?? 0) },
        ]}
      />
      <div className="app-cluster" style={{ margin: "var(--space-6) 0", alignItems: "flex-end" }}>
        <Segmented label="Status" idPrefix="courses-status" controls={false} value={status} onChange={(v) => patch({ status: v })} options={TABS} />
        <div style={{ minWidth: 220, flex: "1 1 220px", maxWidth: 360 }}>
          <Input label="Search courses" type="search" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div style={{ width: 160 }}>
          <Select label="Price" options={[{ value: "", label: "Any" }, { value: "free", label: "Free" }, { value: "paid", label: "Paid" }]} value={access} onChange={(e) => patch({ access: e.target.value })} />
        </div>
      </div>
      {list.query.isPending ? (
        <SkeletonRows />
      ) : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title={status || access || query ? "No courses match" : "No courses yet"} action={<Button onClick={() => patch({ new: "1" })}>Add course</Button>}>
          {status || access || query ? "Try a different filter." : "Courses you add are listed here."}
        </EmptyState>
      ) : (
        <>
          <TableScroll label="Courses">
            <table className="app-table">
              <thead>
                <tr>
                  <th scope="col">Course</th>
                  <th scope="col">Status</th>
                  <th scope="col">Price</th>
                  <th scope="col">Lectures</th>
                  <th scope="col">Learners</th>
                  <th scope="col">Rating</th>
                  <th scope="col">Edited</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.items.map((c) => (
                  <tr key={c.id}>
                    <th scope="row">
                      <Link to={`/admin/courses/${c.id}`} className="wo-linkbtn">
                        {c.title}
                      </Link>
                      <div className="caption app-muted">{[c.instructor, c.category].filter(Boolean).join(" · ")}</div>
                    </th>
                    <td>
                      <StatusChip tone={c.status === "published" ? "success" : c.status === "unlisted" ? "info" : "neutral"}>{humanise(c.status)}</StatusChip>
                      {c.pending_requests ? <div className="caption">{c.pending_requests} waiting</div> : null}
                    </td>
                    <td>{c.price ? formatMoney(c.price.amount_minor, c.price.currency) : "Free"}</td>
                    <td>{c.lesson_count}</td>
                    <td>{c.learners_count}</td>
                    <td>{c.rating.average === null ? "None yet" : `${c.rating.average.toFixed(1)} (${c.rating.count})`}</td>
                    <td>{formatDate(c.edited_at ?? c.created_at)}</td>
                    <td>
                      <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
                        <Link className="wo-btn wo-btn--secondary wo-btn--sm" to={`/admin/courses/${c.id}`} aria-label={`Manage ${c.title}`}>
                          Manage
                        </Link>
                        <Button size="sm" variant="ghost" onClick={() => void duplicate(c)} aria-label={`Copy ${c.title}`}>
                          Copy
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
      {adding ? (
        <AddCourse
          onClose={() => patch({ new: "" })}
          onCreated={(id) => {
            void refresh();
            navigate(`/admin/courses/${id}`);
          }}
        />
      ) : null}
    </>
  );
}
