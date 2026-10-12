import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Award, CheckCircle2, Circle, ListVideo, Lock, PlayCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import type { components } from "../api/schema";
import { isTyping } from "../admin/shell/prefs";
import { Alert, Button, Checkbox, Tabs } from "../components";
import { formatDuration, plural } from "../lib/format";
import { Accordion } from "../ui/Accordion";
import { Drawer } from "../ui/Drawer";
import { ProgressRing } from "../ui/ProgressRing";
import { ErrorState, RichText, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { Announcements, lectureLink } from "./Landing";
import { Notes, Questions } from "./PlayerTabs";
import { Reviews } from "./Reviews";
import { YouTubePlayer, type PlayerHandle } from "./YouTubePlayer";
import "../styles/learn.css";

type Page = components["schemas"]["CoursePageDetail"];

const AUTO_KEY = "wo.learn.autonext";
const readAuto = () => {
  try {
    return localStorage.getItem(AUTO_KEY) !== "off";
  } catch {
    return true;
  }
};

/** The course content beside (or, on a phone, under) the video, with where you are marked. */
function Curriculum({ course, currentId }: { course: Page; currentId: string }) {
  return (
    <nav className="wo-curriculum" aria-label="Course content">
      <div className="wo-curriculum__top">
        {course.progress.enrolled ? <ProgressRing percent={course.progress.percent} label="Course progress" /> : null}
        <div>
          <h2 className="wo-learn__h3" style={{ margin: 0 }}>
            Course content
          </h2>
          <p className="wo-learn__sub" style={{ margin: 0 }}>
            {course.progress.enrolled
              ? `${course.progress.completed_lessons ?? 0} of ${course.progress.total_lessons ?? course.lesson_count} done${course.progress.time_remaining_seconds ? ` · ${formatDuration(course.progress.time_remaining_seconds)} left` : ""}`
              : plural(course.lesson_count, "lecture")}
          </p>
        </div>
      </div>
      <Accordion
        defaultOpen={course.modules.filter((m) => m.lessons.some((l) => l.id === currentId)).map((m) => m.id)}
        items={course.modules.map((m, i) => ({
          id: m.id,
          title: `${i + 1}. ${m.title}`,
          meta: `${m.lessons.filter((l) => l.completed).length}/${m.lessons.length}`,
          content: (
            <ol className="wo-curriculum__list">
              {m.lessons.map((l) => {
                const Icon = l.locked ? Lock : l.completed ? CheckCircle2 : l.id === currentId ? PlayCircle : Circle;
                const row = (
                  <>
                    <Icon size={18} strokeWidth={1.5} aria-hidden="true" />
                    <span className="wo-curriculum__title">{l.title}</span>
                    <span className="wo-curriculum__time">{formatDuration(l.duration_seconds)}</span>
                  </>
                );
                return (
                  <li key={l.id}>
                    {l.locked ? (
                      <span className="wo-curriculum__row" data-locked="true">
                        {row}
                      </span>
                    ) : (
                      <Link className="wo-curriculum__row" to={lectureLink(course.slug, l.id)} aria-current={l.id === currentId ? "step" : undefined} data-done={l.completed}>
                        {row}
                        {l.completed ? <span className="wo-visually-hidden"> (done)</span> : null}
                      </Link>
                    )}
                  </li>
                );
              })}
            </ol>
          ),
        }))}
      />
    </nav>
  );
}

/** The lecture page: the video (or the reading), the way to move on, and the tabs under it. */
export default function Player() {
  const { ref = "", lessonId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast();
  const video = useRef<PlayerHandle>(null);
  const [auto, setAuto] = useState(readAuto);
  const [sheet, setSheet] = useState(false);
  const [finished, setFinished] = useState(false);
  const tab = params.get("tab") ?? "overview";

  const courseQuery = useQuery({ queryKey: ["course", ref], queryFn: () => unwrap(api.GET("/api/v1/courses/page/{ref}", { params: { path: { ref } } })) });
  const lessonQuery = useQuery({ queryKey: ["lesson", lessonId], queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: lessonId } } })), retry: false });
  const course = courseQuery.data;
  const lesson = lessonQuery.data;
  useDocumentTitle(lesson ? `${lesson.title}: ${lesson.course.title}` : "Lecture");
  const enrolled = Boolean(lesson?.progress);

  const refresh = useCallback(
    () => Promise.all([client.invalidateQueries({ queryKey: ["course"] }), client.invalidateQueries({ queryKey: ["lesson", lessonId] }), client.invalidateQueries({ queryKey: ["courses"] })]),
    [client, lessonId],
  );
  const position = useMutation({ mutationFn: (seconds: number) => unwrap(api.PUT("/api/v1/lessons/{lesson_id}/progress", { params: { path: { lesson_id: lessonId } }, body: { position_seconds: seconds } })) });
  const complete = useMutation({
    mutationFn: (done: boolean) => unwrap(api.PUT("/api/v1/lessons/{lesson_id}/progress", { params: { path: { lesson_id: lessonId } }, body: { completed: done } })),
    onSuccess: async (result, done) => {
      await refresh();
      if (done && result.course_completed) {
        setFinished(true);
        toast.show("Course complete. Your certificate is ready.");
      }
    },
  });

  const next = lesson?.next_lesson_id ?? null;
  const previous = lesson?.previous_lesson_id ?? null;
  const go = useCallback((id: string | null) => id && course && navigate(lectureLink(course.slug, id)), [course, navigate]);

  // A new lecture starts at the top, with no stale "finished" banner.
  useEffect(() => {
    window.scrollTo({ top: 0 });
    setFinished(false);
  }, [lessonId]);

  // N and P move between lectures, as long as nobody is typing.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key.toLowerCase() === "n" && next) go(next);
      else if (event.key.toLowerCase() === "p" && previous) go(previous);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, next, previous]);

  const onEnded = () => {
    if (!enrolled) return;
    complete.mutate(true, {
      onSuccess: (result) => {
        if (auto && next && !result.course_completed) go(next);
      },
    });
  };
  const toggleAuto = (on: boolean) => {
    setAuto(on);
    try {
      localStorage.setItem(AUTO_KEY, on ? "on" : "off");
    } catch {
      /* the choice is just not remembered */
    }
  };
  const setTab = (id: string) => setParams((p) => { const n = new URLSearchParams(p); if (id === "overview") n.delete("tab"); else n.set("tab", id); return n; }, { replace: true });

  const start = useMemo(() => (lesson?.progress && !lesson.progress.completed && lesson.progress.position_seconds > 5 ? lesson.progress.position_seconds : 0), [lesson?.progress]);

  if (courseQuery.isPending || lessonQuery.isPending) return <SkeletonRows />;
  if (courseQuery.isError || !course) return <ErrorState error={courseQuery.error} onRetry={() => void courseQuery.refetch()} />;
  if (lessonQuery.isError || !lesson) {
    return (
      <div className="wo-locked">
        <Alert tone="info" title="This lecture is part of the course">
          {messageOf(lessonQuery.error)} Enrol in the course to watch it.
        </Alert>
        <Link className="wo-btn wo-btn--primary" to={`/app/learn/courses/${course.slug}`}>
          Go to the course
        </Link>
      </div>
    );
  }
  const done = Boolean(lesson.progress?.completed);

  const openResource = async () => {
    if (lesson.resource?.kind === "file") {
      const link = await unwrap(api.GET("/api/v1/lessons/{lesson_id}/file", { params: { path: { lesson_id: lessonId } } }));
      window.open(link.url, "_blank", "noopener,noreferrer");
    } else if (lesson.resource?.url) {
      window.open(lesson.resource.url, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <div className="wo-player">
      <header className="wo-player__bar">
        <Link className="wo-linkbtn" to={`/app/learn/courses/${course.slug}`}>
          <ArrowLeft size={16} strokeWidth={1.5} aria-hidden="true" /> {course.title}
        </Link>
        {enrolled ? <ProgressRing percent={course.progress.percent} size={44} label="Course progress" /> : null}
      </header>

      <div className="wo-player__grid">
        <div className="wo-player__main">
          <h1 className="wo-player__title">{lesson.title}</h1>
          <p className="wo-learn__sub">
            {lesson.module.title}
            {lesson.duration_seconds ? ` · ${formatDuration(lesson.duration_seconds)}` : ""}
            {lesson.preview && !enrolled ? " · Free preview" : ""}
          </p>

          {lesson.video ? (
            <YouTubePlayer
              key={lesson.id}
              ref={video}
              videoId={lesson.video.video_id}
              title={lesson.title}
              start={start}
              onPosition={enrolled ? (s) => position.mutate(s) : undefined}
              onEnded={onEnded}
            />
          ) : null}
          {lesson.body ? (
            <div className="wo-box">
              <RichText html={lesson.body} />
            </div>
          ) : null}
          {lesson.resource ? (
            <div className="wo-box">
              <Button variant="secondary" onClick={() => void openResource()}>
                {lesson.resource.name || "Open the resource"}
              </Button>
            </div>
          ) : null}

          {finished ? (
            <Alert tone="success" title="You finished the course">
              <Link className="wo-linkbtn" to="/app/learn/certificates">
                <Award size={16} strokeWidth={1.5} aria-hidden="true" /> View your certificate
              </Link>
            </Alert>
          ) : null}
          {complete.isError ? (
            <Alert tone="danger" title="We could not save your progress">
              {messageOf(complete.error)}
            </Alert>
          ) : null}

          <div className="wo-player__controls">
            <Button variant="secondary" icon={<ArrowLeft size={16} strokeWidth={1.5} />} disabled={!previous} onClick={() => go(previous)} aria-keyshortcuts="P">
              Previous
            </Button>
            {enrolled ? (
              <Button variant={done ? "secondary" : "primary"} loading={complete.isPending} onClick={() => complete.mutate(!done)} aria-pressed={done}>
                {done ? "Completed. Mark as not done" : "Mark complete"}
              </Button>
            ) : null}
            <Button variant="secondary" disabled={!next} onClick={() => go(next)} aria-keyshortcuts="N">
              Next <ArrowRight size={16} strokeWidth={1.5} aria-hidden="true" />
            </Button>
            <Checkbox label="Play the next lecture when this ends" checked={auto} onChange={(e) => toggleAuto(e.target.checked)} />
            <button type="button" className="wo-linkbtn wo-player__sheetbtn" onClick={() => setSheet(true)}>
              <ListVideo size={16} strokeWidth={1.5} aria-hidden="true" /> Course content
            </button>
          </div>
          <p className="wo-learn__sub">Shortcuts: N for the next lecture, P for the previous.</p>

          <div className="app-tabs-scroll">
            <Tabs
              label="About this lecture"
              value={tab}
              onChange={setTab}
              items={[
                { id: "overview", label: "Overview" },
                { id: "qa", label: "Q&A" },
                { id: "notes", label: "Notes" },
                { id: "reviews", label: "Reviews" },
                { id: "announcements", label: "Announcements" },
              ]}
            />
          </div>
          <div className="wo-player__panel">
            {tab === "overview" ? (
              <section aria-label="Overview">
                <h2 className="wo-learn__h3">About this lecture</h2>
                <p>{lesson.description || "No description for this lecture."}</p>
                <h2 className="wo-learn__h3">About the course</h2>
                <p>{course.subtitle || course.excerpt}</p>
              </section>
            ) : null}
            {tab === "qa" ? (enrolled ? <Questions lessonId={lesson.id} /> : <Alert tone="info" title="Enrol to ask questions">Questions are for people who are enrolled.</Alert>) : null}
            {tab === "notes" ? (enrolled ? <Notes lessonId={lesson.id} getTime={() => video.current?.time() ?? 0} onSeek={(s) => video.current?.seek(s)} /> : <Alert tone="info" title="Enrol to keep notes">Your notes are private and saved at the moment you are watching.</Alert>) : null}
            {tab === "reviews" ? (
              <Reviews courseId={course.id} average={course.rating.average} count={course.rating.count} distribution={course.rating_distribution} enrolled={enrolled} canReview={course.can_review} mine={course.my_rating} />
            ) : null}
            {tab === "announcements" ? (enrolled ? <Announcements courseId={course.id} /> : <Alert tone="info" title="Enrol to read announcements">Announcements are sent to the people on the course.</Alert>) : null}
          </div>
        </div>

        <aside className="wo-player__side">
          <Curriculum course={course} currentId={lesson.id} />
        </aside>
      </div>

      <Drawer open={sheet} onOpenChange={setSheet} placement="bottom" title="Course content">
        <Curriculum course={course} currentId={lesson.id} />
      </Drawer>
    </div>
  );
}
