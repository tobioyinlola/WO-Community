import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { useCursorList } from "../api/hooks";
import { messageOf } from "../api/errors";
import type { components } from "../api/schema";
import { Alert, Button, Textarea } from "../components";
import { formatDate } from "../lib/format";
import { LoadMore } from "../ui/blocks";
import { RatingInput, Stars } from "../ui/Rating";
import { useToast } from "../ui/Toast";
import "../styles/learn.css";

type Review = components["schemas"]["Review"];
type Page = components["schemas"]["ReviewPage"];

interface Props {
  courseId: string;
  average: number | null;
  count: number;
  distribution: { [key: string]: number };
  enrolled: boolean;
  canReview: boolean;
  mine: { stars: number; feedback: string } | null;
}

/** Ratings at a glance, the written reviews, and (once a quarter is done) a form to add yours. */
export function Reviews({ courseId, average, count, distribution, enrolled, canReview, mine }: Props) {
  const client = useQueryClient();
  const toast = useToast();
  const [stars, setStars] = useState(mine?.stars ?? 0);
  const [feedback, setFeedback] = useState(mine?.feedback ?? "");
  const list = useCursorList<Review, Page>(["courses", "reviews", courseId], (cursor) =>
    unwrap(api.GET("/api/v1/courses/{course_id}/reviews", { params: { path: { course_id: courseId }, query: { limit: 10, ...(cursor ? { cursor } : {}) } } })),
  );
  const save = useMutation({
    mutationFn: () => unwrap(api.PUT("/api/v1/courses/{course_id}/rating", { params: { path: { course_id: courseId } }, body: { stars, feedback } })),
    onSuccess: async () => {
      toast.show(mine ? "Your review is updated" : "Thank you for your review");
      await client.invalidateQueries({ queryKey: ["courses"] });
      await client.invalidateQueries({ queryKey: ["course"] });
    },
  });
  const biggest = Math.max(1, ...Object.values(distribution));

  return (
    <section className="wo-reviews" aria-labelledby="reviews-title">
      <h2 id="reviews-title" className="wo-learn__h2">
        Reviews
      </h2>
      <div className="wo-reviews__summary">
        <div className="wo-reviews__score">
          <span className="wo-reviews__number">{average === null ? "New" : average.toFixed(1)}</span>
          <Stars value={average} count={count} showNumber={false} size={18} />
          <span className="wo-reviews__count">{count === 0 ? "No reviews yet" : `${count} ${count === 1 ? "review" : "reviews"}`}</span>
        </div>
        <ul className="wo-reviews__bars" aria-label="Reviews by number of stars">
          {[5, 4, 3, 2, 1].map((n) => {
            const total = distribution[String(n)] ?? 0;
            return (
              <li key={n} className="wo-reviews__bar">
                <span>{n} stars</span>
                <span className="wo-progressbar" aria-hidden="true">
                  <span style={{ width: `${(total / biggest) * 100}%` }} />
                </span>
                <span className="wo-reviews__n">{total}</span>
              </li>
            );
          })}
        </ul>
      </div>

      {enrolled ? (
        canReview ? (
          <form
            className="wo-reviews__form"
            onSubmit={(event) => {
              event.preventDefault();
              if (stars > 0) save.mutate();
            }}
          >
            <h3 className="wo-learn__h3">{mine ? "Your review" : "Review this course"}</h3>
            <RatingInput value={stars} onChange={setStars} />
            <Textarea label="Tell others what you thought (optional)" rows={3} maxLength={1000} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
            {save.isError ? (
              <Alert tone="danger" title="We could not save your review">
                {messageOf(save.error)}
              </Alert>
            ) : null}
            <div>
              <Button type="submit" loading={save.isPending} disabled={stars === 0}>
                {mine ? "Update review" : "Send review"}
              </Button>
            </div>
          </form>
        ) : (
          <p className="wo-reviews__note">You can review this course once you have finished a quarter of it.</p>
        )
      ) : null}

      {list.items.length > 0 ? (
        <ul className="wo-reviews__list">
          {list.items.map((r) => (
            <li key={r.id} className="wo-review">
              <div className="wo-review__head">
                <strong>{r.reviewer}</strong>
                <Stars value={r.stars} showNumber={false} size={14} />
                <time dateTime={r.created_at}>{formatDate(r.created_at)}</time>
              </div>
              {r.feedback ? <p className="wo-review__body">{r.feedback}</p> : null}
            </li>
          ))}
        </ul>
      ) : null}
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
    </section>
  );
}
