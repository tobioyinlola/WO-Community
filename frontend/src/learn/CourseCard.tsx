import { Link } from "react-router-dom";
import type { components } from "../api/schema";
import { formatDuration, formatMoney, humanise, plural } from "../lib/format";
import { Stars } from "../ui/Rating";
import "../styles/learn.css";

export type CourseSummary = components["schemas"]["CourseSummary"];

/** What a course costs, with the usual price struck out while a promotion runs. */
export function Price({ course }: { course: Pick<CourseSummary, "price" | "access"> }) {
  if (course.access === "free" || !course.price) return <span className="wo-free">Free</span>;
  const { amount_minor: now, original_minor: before, currency } = course.price;
  return (
    <span className="wo-price">
      <span>{formatMoney(now, currency)}</span>
      {before ? (
        <s>
          <span className="wo-visually-hidden">Usual price </span>
          {formatMoney(before, currency)}
        </s>
      ) : null}
    </span>
  );
}

export function Thumb({ course }: { course: Pick<CourseSummary, "cover" | "title"> }) {
  return (
    <span className="wo-course__thumb" aria-hidden="true">
      {course.cover ? <img src={course.cover.large} alt="" loading="lazy" /> : course.title.slice(0, 1).toUpperCase()}
    </span>
  );
}

/** A course in a grid: picture, title, who teaches it, how good it is, how long, and the price. */
export function CourseCard({ course }: { course: CourseSummary }) {
  const enrolled = course.progress.enrolled;
  const done = Boolean(course.progress.completed_at);
  return (
    <Link to={`/app/learn/courses/${course.slug}`} className="wo-course">
      <span className="wo-course__thumb-wrap">
        <Thumb course={course} />
      </span>
      <span className="wo-course__body">
        {enrolled ? <span className="wo-course__badge-line">{done ? "Completed" : "Enrolled"}</span> : null}
        <span className="wo-course__title">{course.title}</span>
        <span className="wo-course__by">{course.instructor}</span>
        <Stars value={course.rating.average} count={course.rating.count} size={14} />
        <ul className="wo-course__facts">
          {course.duration_seconds ? <li>{formatDuration(course.duration_seconds)}</li> : null}
          <li>{plural(course.lesson_count, "lecture")}</li>
          <li>{humanise(course.level === "all" ? "all levels" : course.level)}</li>
        </ul>
        {enrolled ? (
          <span>
            <span className="wo-progressbar" role="progressbar" aria-label="Your progress" aria-valuenow={course.progress.percent} aria-valuemin={0} aria-valuemax={100}>
              <span style={{ width: `${course.progress.percent}%` }} />
            </span>
            <span className="wo-course__by">{done ? "You finished this course" : `${course.progress.percent}% complete`}</span>
          </span>
        ) : (
          <span className="wo-course__foot">
            <Price course={course} />
            {course.wishlisted ? <span className="wo-course__by">Saved</span> : null}
          </span>
        )}
      </span>
    </Link>
  );
}
