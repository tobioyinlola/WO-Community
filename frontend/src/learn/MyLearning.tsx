import { useQuery } from "@tanstack/react-query";
import { Award } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { useCursorList } from "../api/hooks";
import { messageOf } from "../api/errors";
import type { components } from "../api/schema";
import { Alert, Card, CardText, CardTitle, Tabs } from "../components";
import { formatDate } from "../lib/format";
import { EmptyState, Loaded, LoadMore, PageHeader, SkeletonCards, useDocumentTitle } from "../ui/blocks";
import { DownloadButton } from "../ui/DownloadButton";
import { CourseCard, type CourseSummary } from "./CourseCard";
import "../styles/learn.css";

type State = "all" | "in_progress" | "completed" | "wishlist";
type Page = components["schemas"]["CoursePage"];

const TABS: Array<{ id: State; label: string }> = [
  { id: "all", label: "All courses" },
  { id: "in_progress", label: "In progress" },
  { id: "completed", label: "Completed" },
  { id: "wishlist", label: "Saved" },
];

const EMPTY: Record<State, [string, string]> = {
  all: ["You have not started a course", "Enrol in a course from the catalogue and your progress appears here."],
  in_progress: ["Nothing in progress", "Courses you have started and not finished appear here."],
  completed: ["No finished courses yet", "When you finish a course it moves here, with your certificate."],
  wishlist: ["Nothing saved", "Use Save for later on a course to keep it here."],
};

export function Certificates() {
  useDocumentTitle("Your certificates");
  const query = useQuery({ queryKey: ["certificates"], queryFn: () => unwrap(api.GET("/api/v1/certificates")) });
  return (
    <>
      <PageHeader eyebrow="Learn" title="Your certificates" lead="Earned by finishing a course. Each has a code anyone can check." />
      <Loaded query={query} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No certificates yet">Finish a course that offers one and it appears here.</EmptyState>}>
        {(items) => (
          <div className="app-grid">
            {items.map((c) => (
              <Card key={c.id} variant="white">
                <Award size={28} strokeWidth={1.5} aria-hidden="true" />
                <CardTitle style={{ marginTop: "var(--space-3)" }}>{c.course_title}</CardTitle>
                <CardText>
                  {c.holder_name} · {formatDate(c.issued_at)}
                </CardText>
                <p className="mono" style={{ margin: "var(--space-3) 0" }}>
                  {c.code}
                </p>
                <DownloadButton variant="secondary" size="sm" path={`/api/v1/certificates/${c.id}/pdf`} filename={`certificate-${c.code}.pdf`}>
                  Download PDF
                </DownloadButton>
              </Card>
            ))}
          </div>
        )}
      </Loaded>
    </>
  );
}

/** Everything the member has started, finished or saved, with progress and a way back in. */
export default function MyLearning() {
  useDocumentTitle("My learning");
  const [state, setState] = useState<State>("all");
  const list = useCursorList<CourseSummary, Page>(["courses", "shelf", state], (cursor) =>
    unwrap(api.GET("/api/v1/me/learning", { params: { query: { state, limit: 12, ...(cursor ? { cursor } : {}) } } })),
  );
  const [title, text] = EMPTY[state];
  return (
    <>
      <PageHeader
        eyebrow="Learn"
        title="My learning"
        lead="Pick up where you left off."
        actions={
          <Link className="wo-btn wo-btn--secondary" to="/app/learn">
            Browse courses
          </Link>
        }
      />
      <div className="app-tabs-scroll">
        <Tabs label="Which courses" variant="segment" value={state} onChange={(id) => setState(id as State)} items={TABS} />
      </div>
      {list.query.isPending ? <SkeletonCards /> : null}
      {list.query.isError ? (
        <Alert tone="danger" title="We could not load your courses">
          {messageOf(list.query.error)}
        </Alert>
      ) : null}
      {list.isEmpty ? <EmptyState title={title}>{text}</EmptyState> : null}
      <ul className="wo-courses" aria-label="Your courses">
        {list.items.map((c) => (
          <li key={c.id}>
            <CourseCard course={c} />
          </li>
        ))}
      </ul>
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
      <p>
        <Link className="wo-linkbtn" to="/app/learn/certificates">
          <Award size={16} strokeWidth={1.5} aria-hidden="true" /> Your certificates
        </Link>
      </p>
    </>
  );
}
