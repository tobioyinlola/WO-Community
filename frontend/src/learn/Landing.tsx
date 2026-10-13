import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Award, Bell, Check, CircleCheck, Heart, Infinity as InfinityIcon, Lock, PlayCircle, Share2, FileText, Video } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import type { components } from "../api/schema";
import { Alert, Button, Modal, Textarea } from "../components";
import { formatDate, formatDuration, humanise, plural } from "../lib/format";
import { Accordion } from "../ui/Accordion";
import { ErrorState, RichText, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { Stars } from "../ui/Rating";
import { useToast } from "../ui/Toast";
import { CourseCard, Price } from "./CourseCard";
import { Reviews } from "./Reviews";
import "../styles/learn.css";

type Page = components["schemas"]["CoursePageDetail"];
type Announcement = components["schemas"]["Announcement"];

export const lectureLink = (slug: string, lessonId: string) => `/app/learn/courses/${slug}/lecture/${lessonId}`;

export function Announcements({ courseId }: { courseId: string }) {
  const list = useQuery({
    queryKey: ["courses", "announcements", courseId],
    queryFn: () => unwrap(api.GET("/api/v1/courses/{course_id}/announcements", { params: { path: { course_id: courseId } } })),
  });
  const items: Announcement[] = list.data ?? [];
  if (items.length === 0) return null;
  return (
    <section aria-labelledby="ann-title" id="announcements">
      <h2 id="ann-title" className="wo-learn__h2">
        Announcements
      </h2>
      <ul className="wo-announcements">
        {items.map((a) => (
          <li key={a.id} className="wo-announcement">
            <h3 className="wo-learn__h3">{a.title}</h3>
            <time dateTime={a.created_at}>{formatDate(a.created_at)}</time>
            <RichText html={a.body} />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** A course's landing page: what it is, what is in it, what it costs, and the way in. */
type ActionCourse = Pick<Page, "slug" | "access" | "enrolment_active" | "access_request" | "resume"> & { progress: Pick<Page["progress"], "enrolled" | "completed_at"> };

/** The one button that moves a person forward on a course, whatever state they and the course are in. */
export function CourseAction({ course, target, enrolling = false, onEnrol, onAsk, onLeave }: { course: ActionCourse; target?: string; enrolling?: boolean; onEnrol: () => void; onAsk: () => void; onLeave?: () => void }) {
  if (course.progress.enrolled)
    return target ? (
      <>
        <Link className="wo-btn wo-btn--primary wo-btn--lg" to={lectureLink(course.slug, target)}>
          {course.progress.completed_at ? "Review the course" : course.resume ? "Continue learning" : "Start learning"}
        </Link>
        {onLeave ? (
          <Button variant="ghost" onClick={onLeave}>
            Leave course
          </Button>
        ) : null}
      </>
    ) : null;
  if (!course.enrolment_active)
    return (
      <Button size="lg" disabled>
        Enrolment is closed
      </Button>
    );
  if (course.access === "free")
    return (
      <Button size="lg" loading={enrolling} onClick={onEnrol}>
        Enrol for free
      </Button>
    );
  if (course.access_request === "pending")
    return (
      <Button size="lg" disabled icon={<Check size={18} strokeWidth={1.5} />}>
        Request sent
      </Button>
    );
  return (
    <Button size="lg" onClick={onAsk}>
      Request access
    </Button>
  );
}

export default function Landing() {
  const { ref = "" } = useParams();
  const [params] = useSearchParams();
  const client = useQueryClient();
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const [message, setMessage] = useState("");

  const query = useQuery({
    queryKey: ["course", ref],
    queryFn: () => unwrap(api.GET("/api/v1/courses/page/{ref}", { params: { path: { ref } } })),
  });
  const refresh = () => Promise.all([client.invalidateQueries({ queryKey: ["course"] }), client.invalidateQueries({ queryKey: ["courses"] })]);
  const course: Page | undefined = query.data;
  useDocumentTitle(course?.title ?? "Course");
  // A link from an announcement notification lands on the announcements.
  const wantsAnnouncements = params.get("tab") === "announcements" && Boolean(course?.progress.enrolled);
  useEffect(() => {
    if (wantsAnnouncements) document.getElementById("announcements")?.scrollIntoView({ behavior: "smooth" });
  }, [wantsAnnouncements]);

  const enrol = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/courses/{course_id}/enrol", { params: { path: { course_id: course?.id ?? "" } } })),
    onSuccess: async () => {
      toast.show("You are enrolled");
      await refresh();
    },
  });
  const leave = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/courses/{course_id}/unenrol", { params: { path: { course_id: course?.id ?? "" } } })),
    onSuccess: async () => {
      toast.show("You left the course. Your progress is kept.");
      await refresh();
    },
  });
  const request = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/courses/{course_id}/request-access", { params: { path: { course_id: course?.id ?? "" } }, body: { message } })),
    onSuccess: async () => {
      setAsking(false);
      setMessage("");
      toast.show("Your request was sent. We will tell you when it is decided.");
      await refresh();
    },
  });
  const save = useMutation({
    mutationFn: (on: boolean) =>
      on
        ? unwrap(api.PUT("/api/v1/courses/{course_id}/wishlist", { params: { path: { course_id: course?.id ?? "" } } }))
        : unwrap(api.DELETE("/api/v1/courses/{course_id}/wishlist", { params: { path: { course_id: course?.id ?? "" } } })),
    onSuccess: async (_d, on) => {
      toast.show(on ? "Saved for later" : "Removed from your saved courses");
      await refresh();
    },
  });

  if (query.isPending) return <SkeletonRows />;
  if (query.isError || !course) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;

  const enrolled = course.progress.enrolled;
  const lectures = course.modules.flatMap((m) => m.lessons);
  const firstOpen = lectures.find((l) => !l.locked);
  const target = course.resume?.lesson_id ?? firstOpen?.id;
  const share = async () => {
    const link = `${window.location.origin}/app/learn/courses/${course.slug}`;
    try {
      if (navigator.share) await navigator.share({ title: course.title, url: link });
      else {
        await navigator.clipboard.writeText(link);
        toast.show("Link copied");
      }
    } catch {
      /* a closed share sheet is not an error */
    }
  };

  const cta = <CourseAction course={course} target={target} enrolling={enrol.isPending} onEnrol={() => enrol.mutate()} onAsk={() => setAsking(true)} onLeave={() => { if (window.confirm("Leave this course? Your progress is kept if you join again.")) leave.mutate(); }} />;

  return (
    <>
      <section className="wo-landing__hero" aria-labelledby="course-title">
        <span className="wo-eyebrow">{humanise(course.category)}</span>
        <h1 id="course-title" className="wo-landing__title">
          {course.title}
        </h1>
        {course.subtitle ? <p className="wo-landing__subtitle">{course.subtitle}</p> : null}
        <ul className="wo-landing__facts">
          <li>
            <Stars value={course.rating.average} count={course.rating.count} />
          </li>
          <li>{plural(course.learners_count, "learner")}</li>
          <li>Taught by {course.instructor}</li>
          <li>Updated {formatDate(course.last_updated)}</li>
          <li>{course.language_label}</li>
        </ul>
      </section>

      <div className="wo-landing">
        <div className="wo-landing__main">
          {enrol.isError ? (
            <Alert tone="danger" title="We could not enrol you">
              {messageOf(enrol.error)}
            </Alert>
          ) : null}
          {course.learn_bullets.length > 0 ? (
            <section className="wo-box" aria-labelledby="learn-title">
              <h2 id="learn-title" className="wo-learn__h2">
                What you will learn
              </h2>
              <ul className="wo-checks">
                {course.learn_bullets.map((b) => (
                  <li key={b}>
                    <CircleCheck size={18} strokeWidth={1.5} aria-hidden="true" />
                    {b}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section aria-labelledby="content-title">
            <h2 id="content-title" className="wo-learn__h2">
              Course content
            </h2>
            <p className="wo-learn__sub">
              {plural(course.section_count, "section")} · {plural(course.lesson_count, "lecture")}
              {course.duration_seconds ? ` · ${formatDuration(course.duration_seconds)} in all` : ""}
            </p>
            <Accordion
              defaultOpen={course.modules.slice(0, 1).map((m) => m.id)}
              items={course.modules.map((m, i) => ({
                id: m.id,
                title: `Section ${i + 1}: ${m.title}`,
                meta: `${plural(m.lessons.length, "lecture")}${formatDuration(m.lessons.reduce((n, l) => n + (l.duration_seconds ?? 0), 0)) ? ` · ${formatDuration(m.lessons.reduce((n, l) => n + (l.duration_seconds ?? 0), 0))}` : ""}`,
                content: (
                  <ul className="wo-lectures">
                    {m.lessons.map((l) => {
                      const Icon = l.type === "video" ? PlayCircle : FileText;
                      const row = (
                        <>
                          {l.locked ? <Lock size={16} strokeWidth={1.5} aria-hidden="true" /> : l.completed ? <CircleCheck size={16} strokeWidth={1.5} aria-hidden="true" /> : <Icon size={16} strokeWidth={1.5} aria-hidden="true" />}
                          <span className="wo-lectures__title">{l.title}</span>
                          {l.preview && !enrolled ? <span className="wo-lectures__preview">Preview</span> : null}
                          <span className="wo-lectures__time">{formatDuration(l.duration_seconds)}</span>
                        </>
                      );
                      return (
                        <li key={l.id}>
                          {l.locked ? (
                            <span className="wo-lectures__row" data-locked="true">
                              {row}
                            </span>
                          ) : (
                            <Link className="wo-lectures__row" to={lectureLink(course.slug, l.id)}>
                              {row}
                            </Link>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                ),
              }))}
            />
          </section>

          {course.requirements.length > 0 ? (
            <section aria-labelledby="req-title">
              <h2 id="req-title" className="wo-learn__h2">
                Requirements
              </h2>
              <ul className="wo-bullets">
                {course.requirements.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section aria-labelledby="desc-title">
            <h2 id="desc-title" className="wo-learn__h2">
              Description
            </h2>
            <RichText html={course.description} />
            {course.audience ? (
              <>
                <h3 className="wo-learn__h3">Who this course is for</h3>
                <p>{course.audience}</p>
              </>
            ) : null}
          </section>

          <section aria-labelledby="inst-title">
            <h2 id="inst-title" className="wo-learn__h2">
              Your instructor
            </h2>
            <p className="wo-instructor">{course.instructor}</p>
          </section>

          {enrolled ? <Announcements courseId={course.id} /> : null}

          <Reviews
            courseId={course.id}
            average={course.rating.average}
            count={course.rating.count}
            distribution={course.rating_distribution}
            enrolled={enrolled}
            canReview={course.can_review}
            mine={course.my_rating}
          />

          {course.related.length > 0 ? (
            <section aria-labelledby="rel-title">
              <h2 id="rel-title" className="wo-learn__h2">
                More like this
              </h2>
              <ul className="wo-courses">
                {course.related.map((c) => (
                  <li key={c.id}>
                    <CourseCard course={c} />
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>

        <aside className="wo-landing__side" aria-label="Enrol">
          <div className="wo-buy">
            <div className="wo-buy__media">
              {course.promo_video ? (
                <iframe title={`${course.title}: preview`} src={course.promo_video.embed_url} loading="lazy" allow="encrypted-media; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" />
              ) : course.cover ? (
                <img src={course.cover.large} alt="" />
              ) : (
                <span aria-hidden="true">{course.title.slice(0, 1).toUpperCase()}</span>
              )}
            </div>
            <div className="wo-buy__body">
              <p className="wo-buy__price" data-free={course.access === "free"}>
                <Price course={course} />
              </p>
              {course.price?.original_minor && course.price.promo_ends_at ? <p className="wo-buy__promo">Offer ends {formatDate(course.price.promo_ends_at)}</p> : null}
              {enrolled && !course.progress.completed_at ? (
                <p className="wo-buy__progress">{course.progress.percent}% complete</p>
              ) : null}
              {cta}
              {course.access === "paid" && !enrolled ? <p className="wo-buy__note">Payment is not taken yet. An admin reviews each request and gives you access.</p> : null}
              <div className="wo-buy__actions">
                <Button variant="secondary" size="sm" icon={<Heart size={16} strokeWidth={1.5} fill={course.wishlisted ? "currentColor" : "none"} />} aria-pressed={course.wishlisted} loading={save.isPending} onClick={() => save.mutate(!course.wishlisted)}>
                  {course.wishlisted ? "Saved" : "Save for later"}
                </Button>
                <Button variant="secondary" size="sm" icon={<Share2 size={16} strokeWidth={1.5} />} onClick={() => void share()}>
                  Share
                </Button>
              </div>
              <h2 className="wo-learn__h3">This course includes</h2>
              <ul className="wo-includes">
                {course.duration_seconds ? (
                  <li>
                    <Video size={16} strokeWidth={1.5} aria-hidden="true" />
                    {formatDuration(course.duration_seconds)} of video
                  </li>
                ) : null}
                <li>
                  <FileText size={16} strokeWidth={1.5} aria-hidden="true" />
                  {plural(course.lesson_count, "lecture")}
                </li>
                {course.certificate_enabled ? (
                  <li>
                    <Award size={16} strokeWidth={1.5} aria-hidden="true" />
                    Certificate of completion
                  </li>
                ) : null}
                <li>
                  <InfinityIcon size={16} strokeWidth={1.5} aria-hidden="true" />
                  Lifetime access
                </li>
                {course.announcement_count > 0 && enrolled ? (
                  <li>
                    <Bell size={16} strokeWidth={1.5} aria-hidden="true" />
                    {plural(course.announcement_count, "announcement")}
                  </li>
                ) : null}
              </ul>
            </div>
          </div>
        </aside>
      </div>

      <Modal
        open={asking}
        onClose={() => setAsking(false)}
        eyebrow="Paid course"
        title="Request access"
        actions={
          <>
            <Button variant="secondary" onClick={() => setAsking(false)}>
              Cancel
            </Button>
            <Button loading={request.isPending} onClick={() => request.mutate()}>
              Send request
            </Button>
          </>
        }
      >
        <p>An admin will read your request and give you access. You will be told in the app and by email.</p>
        <Textarea label="Anything you would like us to know? (optional)" rows={3} maxLength={500} value={message} onChange={(e) => setMessage(e.target.value)} />
        {request.isError ? (
          <Alert tone="danger" title="We could not send your request">
            {messageOf(request.error)}
          </Alert>
        ) : null}
      </Modal>
    </>
  );
}
