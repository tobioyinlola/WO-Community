import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Award, CheckCircle2, Circle, Lock, PlayCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { compact, useCursorList } from "../../api/hooks";
import { messageOf } from "../../api/errors";
import type { components } from "../../api/schema";
import { Alert, Badge, Button, Card, CardText, CardTitle, CardTo, Input, Select, Tabs } from "../../components";
import { formatMoney, humanise, plural } from "../../lib/format";
import { EmptyState, LoadMore, Loaded, PageHeader, RichText, SkeletonCards, SkeletonRows } from "../../ui/blocks";
import { DownloadButton } from "../../ui/DownloadButton";
import { useToast } from "../../ui/Toast";

type Course = components["schemas"]["CourseSummary"];
type Level = "beginner" | "intermediate" | "advanced";
const LEVELS: Level[] = ["beginner", "intermediate", "advanced"];

function minutes(seconds: number | null): string {
  return seconds ? `${Math.max(1, Math.round(seconds / 60))} min` : "";
}

function Progress({ percent }: { percent: number }) {
  return (
    <div className="app-meter" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label="Course progress">
      <span style={{ width: `${percent}%` }} />
    </div>
  );
}

function CourseCard({ course }: { course: Course }) {
  return (
    <CardTo to={`/app/learn/${course.id}`}>
      <div className="app-cluster" style={{ marginBottom: "var(--space-3)" }}>
        <Badge variant="mentor">{humanise(course.level)}</Badge>
        <Badge>{course.category}</Badge>
        {course.access === "paid" && course.price ? <Badge variant="pro">{formatMoney(course.price.amount_minor, course.price.currency)}</Badge> : null}
      </div>
      <CardTitle>{course.title}</CardTitle>
      <CardText>{course.excerpt}</CardText>
      <ul className="app-meta" style={{ marginTop: "var(--space-3)" }}>
        <li>{course.instructor}</li>
        <li>{plural(course.lesson_count, "lesson")}</li>
        {course.rating.average ? <li>{course.rating.average.toFixed(1)} stars</li> : null}
      </ul>
      {course.progress.enrolled ? (
        <div style={{ marginTop: "var(--space-4)" }}>
          <Progress percent={course.progress.percent} />
          <p className="caption app-muted" style={{ margin: "var(--space-1) 0 0" }}>
            {course.progress.completed_at ? "Completed" : `${course.progress.percent}% done`}
          </p>
        </div>
      ) : null}
    </CardTo>
  );
}

export default function LearnPage() {
  const [mine, setMine] = useState<"all" | "mine">("all");
  const [q, setQ] = useState("");
  const [level, setLevel] = useState("");
  const [category, setCategory] = useState("");
  const categories = useQuery({
    queryKey: ["courses", "categories"],
    queryFn: () => unwrap(api.GET("/api/v1/courses/categories")),
  });
  const list = useCursorList<Course>(["courses", mine, q, level, category], (cursor) => {
    const paging = { limit: 12, ...(cursor ? { cursor } : {}) };
    if (mine === "mine") return unwrap(api.GET("/api/v1/me/courses", { params: { query: paging } }));
    return unwrap(api.GET("/api/v1/courses", { params: { query: { ...paging, ...compact({ q: q.trim(), level: level as Level, category }) } } }));
  });
  return (
    <>
      <PageHeader eyebrow="Learn" title="Courses" lead="Practical lessons from people who have done it." />
      <div className="app-tabs-scroll">
        <Tabs label="Which courses" value={mine} onChange={(id) => setMine(id as "all" | "mine")} items={[{ id: "all", label: "Catalogue" }, { id: "mine", label: "My learning" }]} />
      </div>
      {mine === "all" ? (
        <div className="app-filterbar" role="search" aria-label="Filter courses">
          <div className="app-filterbar__grow">
            <Input label="Search" placeholder="Topic or instructor" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Select label="Level" value={level} onChange={(e) => setLevel(e.target.value)} options={[{ value: "", label: "Any level" }, ...LEVELS.map((l) => ({ value: l, label: humanise(l) }))]} />
          <Select label="Category" value={category} onChange={(e) => setCategory(e.target.value)} options={[{ value: "", label: "All categories" }, ...(categories.data?.categories ?? []).map((c) => ({ value: c, label: c }))]} />
        </div>
      ) : null}
      {list.query.isPending ? <SkeletonCards /> : null}
      {list.query.isError ? <Alert tone="danger" title="We could not load courses">{messageOf(list.query.error)}</Alert> : null}
      {list.isEmpty ? (
        <EmptyState title={mine === "mine" ? "You have not started a course" : "No courses match"}>
          {mine === "mine" ? "Enrol in a course from the catalogue and your progress appears here." : "Try changing the filters."}
        </EmptyState>
      ) : null}
      <div className="app-grid">{list.items.map((c) => <CourseCard key={c.id} course={c} />)}</div>
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
    </>
  );
}

export function CourseDetail() {
  const { id = "" } = useParams();
  const client = useQueryClient();
  const toast = useToast();
  const query = useQuery({
    queryKey: ["courses", "one", id],
    queryFn: () => unwrap(api.GET("/api/v1/courses/{course_id}", { params: { path: { course_id: id } } })),
  });
  const enrol = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/courses/{course_id}/enrol", { params: { path: { course_id: id } } })),
    onSuccess: async () => {
      toast.show("You are enrolled");
      await client.invalidateQueries({ queryKey: ["courses"] });
    },
  });

  return (
    <Loaded query={query} skeleton={<SkeletonRows />}>
      {(course) => {
        const first = course.modules.flatMap((m) => m.lessons).find((l) => !l.locked);
        const target = course.resume?.lesson_id ?? first?.id;
        return (
          <>
            <PageHeader eyebrow={course.category} title={course.title} lead={`${course.instructor} · ${humanise(course.level)} · ${plural(course.lesson_count, "lesson")}`} />
            <div className="app-split">
              <div className="app-stack app-stack--lg">
                <Card><RichText html={course.description} /></Card>
                {course.modules.map((module) => (
                  <section key={module.id} aria-label={module.title}>
                    <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>{module.title}</h2>
                    <ul className="app-list">
                      {module.lessons.map((lesson) => {
                        const Icon = lesson.locked ? Lock : lesson.completed ? CheckCircle2 : lesson.type === "video" ? PlayCircle : Circle;
                        const body = (
                          <>
                            <Icon size={20} strokeWidth={1.5} aria-hidden="true" />
                            <div className="app-list__main">
                              <p className="app-list__title">{lesson.title}</p>
                            </div>
                            <span className="caption app-muted">{humanise(lesson.type)} {minutes(lesson.duration_seconds)}</span>
                          </>
                        );
                        return lesson.locked ? (
                          <li key={lesson.id} className="app-list__item" style={{ opacity: "var(--opacity-disabled)" }}>{body}</li>
                        ) : (
                          <li key={lesson.id}>
                            <Link className="app-list__item" to={`/app/learn/lesson/${lesson.id}`}>{body}</Link>
                          </li>
                        );
                      })}
                    </ul>
                  </section>
                ))}
              </div>
              <aside className="app-stack">
                <Card>
                  {course.progress.enrolled ? (
                    <div className="app-stack">
                      <Progress percent={course.progress.percent} />
                      <p className="body-sm" style={{ margin: 0 }}>
                        {course.progress.completed_at ? "You have completed this course." : `${course.progress.percent}% complete`}
                      </p>
                      {target ? <Link className="wo-btn wo-btn--primary wo-btn--lg" to={`/app/learn/lesson/${target}`}>{course.resume ? "Continue" : "Start"}</Link> : null}
                      {course.certificate_enabled ? (
                        <Link className="wo-btn wo-btn--secondary" to="/app/learn/certificates"><Award size={18} strokeWidth={1.5} aria-hidden="true" />Certificates</Link>
                      ) : null}
                    </div>
                  ) : course.access === "paid" ? (
                    <Alert tone="info" title={course.price ? formatMoney(course.price.amount_minor, course.price.currency) : "Paid course"}>
                      Paid courses are not open for enrolment yet.
                    </Alert>
                  ) : (
                    <div className="app-stack">
                      {enrol.isError ? <Alert tone="danger" title="Could not enrol">{messageOf(enrol.error)}</Alert> : null}
                      <Button size="lg" loading={enrol.isPending} onClick={() => enrol.mutate()}>Enrol for free</Button>
                    </div>
                  )}
                </Card>
                {course.progress.enrolled ? <Rate courseId={course.id} current={course.my_rating} /> : null}
              </aside>
            </div>
          </>
        );
      }}
    </Loaded>
  );
}

function Rate({ courseId, current }: { courseId: string; current: components["schemas"]["MyRating"] | null }) {
  const client = useQueryClient();
  const toast = useToast();
  const [stars, setStars] = useState(current?.stars ?? 0);
  const save = useMutation({
    mutationFn: (value: number) => unwrap(api.PUT("/api/v1/courses/{course_id}/rating", { params: { path: { course_id: courseId } }, body: { stars: value, feedback: current?.feedback ?? "" } })),
    onSuccess: async () => { toast.show("Thanks for rating this course"); await client.invalidateQueries({ queryKey: ["courses"] }); },
  });
  return (
    <Card>
      <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Rate this course</h2>
      <div className="app-cluster" role="group" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" className="app-react" aria-pressed={stars === n} aria-label={`${n} star${n > 1 ? "s" : ""}`} onClick={() => { setStars(n); save.mutate(n); }}>
            {n}
          </button>
        ))}
      </div>
    </Card>
  );
}

/** Every module and lesson of the course, with the current one marked, beside the lesson. */
function LessonOutline({ courseId, currentId }: { courseId: string; currentId: string }) {
  const query = useQuery({
    queryKey: ["courses", "one", courseId],
    queryFn: () => unwrap(api.GET("/api/v1/courses/{course_id}", { params: { path: { course_id: courseId } } })),
  });
  if (!query.data) return null;
  const course = query.data;
  return (
    <nav className="app-outline" aria-label="Course outline">
      <h2 className="h4" style={{ margin: "0 0 var(--space-1)" }}>Course outline</h2>
      <p className="caption app-muted" style={{ margin: "0 0 var(--space-4)" }}>
        {course.progress.enrolled ? `${course.progress.percent}% complete` : plural(course.lesson_count, "lesson")}
      </p>
      {course.modules.map((module, index) => (
        <section key={module.id} aria-label={module.title}>
          <h3 className="app-outline__module">{index + 1}. {module.title}</h3>
          <ol className="app-outline__lessons">
            {module.lessons.map((lesson) => {
              const Icon = lesson.locked ? Lock : lesson.completed ? CheckCircle2 : lesson.type === "video" ? PlayCircle : Circle;
              const row = (
                <>
                  <Icon size={18} strokeWidth={1.5} aria-hidden="true" />
                  <span>{lesson.title}</span>
                </>
              );
              return (
                <li key={lesson.id}>
                  {lesson.locked ? (
                    <span className="app-outline__item" style={{ opacity: "var(--opacity-disabled)" }}>{row}</span>
                  ) : (
                    <Link className="app-outline__item" to={`/app/learn/lesson/${lesson.id}`} aria-current={lesson.id === currentId ? "step" : undefined}>{row}</Link>
                  )}
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </nav>
  );
}

export function LessonPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast();
  const query = useQuery({
    queryKey: ["lessons", id],
    queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: id } } })),
  });
  const done = useMutation({
    mutationFn: () => unwrap(api.PUT("/api/v1/lessons/{lesson_id}/progress", { params: { path: { lesson_id: id } }, body: { completed: true } })),
    onSuccess: async (result) => {
      await client.invalidateQueries({ queryKey: ["courses"] });
      await client.invalidateQueries({ queryKey: ["lessons"] });
      if (result.course_completed) toast.show("Course complete. Your certificate is ready.");
      const next = query.data?.next_lesson_id;
      if (next) navigate(`/app/learn/lesson/${next}`);
    },
  });
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [id]);

  return (
    <Loaded query={query} skeleton={<SkeletonRows />}>
      {(lesson) => (
        <>
          <PageHeader eyebrow={lesson.module.title} title={lesson.title} lead={lesson.course.title} />
          <div className="app-lesson">
          <div className="app-stack app-stack--lg" style={{ minWidth: 0 }}>
            {lesson.video ? (
              <div className="wo-frame" style={{ aspectRatio: "16 / 9" }}>
                <iframe
                  title={lesson.title}
                  src={lesson.video.embed_url}
                  loading="lazy"
                  allow="encrypted-media; picture-in-picture"
                  allowFullScreen
                  referrerPolicy="strict-origin-when-cross-origin"
                  style={{ width: "100%", height: "100%", border: 0 }}
                />
              </div>
            ) : null}
            {lesson.body ? <Card><RichText html={lesson.body} /></Card> : null}
            {lesson.resource ? (
              <a className="wo-btn wo-btn--secondary" href={lesson.resource.url} target="_blank" rel="noopener noreferrer">
                {lesson.resource.name || "Open the resource"}
              </a>
            ) : null}
            {done.isError ? <Alert tone="danger" title="Could not save progress">{messageOf(done.error)}</Alert> : null}
            <div className="app-cluster" style={{ justifyContent: "space-between" }}>
              {lesson.previous_lesson_id ? <Link className="wo-btn wo-btn--ghost" to={`/app/learn/lesson/${lesson.previous_lesson_id}`}>Previous</Link> : <span />}
              <div className="app-cluster">
                <Link className="wo-btn wo-btn--secondary" to={`/app/learn/${lesson.course.id}`}>Course outline</Link>
                <Button loading={done.isPending} onClick={() => done.mutate()}>
                  {lesson.progress?.completed ? "Completed. Continue" : lesson.next_lesson_id ? "Mark done and continue" : "Mark as done"}
                </Button>
              </div>
            </div>
          </div>
          <LessonOutline courseId={lesson.course.id} currentId={id} />
          </div>
        </>
      )}
    </Loaded>
  );
}

export function Certificates() {
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
                <CardText>{c.holder_name}</CardText>
                <p className="mono" style={{ margin: "var(--space-3) 0" }}>{c.code}</p>
                <DownloadButton variant="secondary" size="sm" path={`/api/v1/certificates/${c.id}/pdf`} filename={`certificate-${c.code}.pdf`}>Download PDF</DownloadButton>
              </Card>
            ))}
          </div>
        )}
      </Loaded>
    </>
  );
}
