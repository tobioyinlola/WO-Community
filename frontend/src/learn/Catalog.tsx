import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { compact, useCursorList } from "../api/hooks";
import { messageOf } from "../api/errors";
import { Alert, Input, Select } from "../components";
import { humanise } from "../lib/format";
import { useDebounced } from "../lib/useDebounced";
import { EmptyState, LoadMore, PageHeader, SkeletonCards, useDocumentTitle } from "../ui/blocks";
import { CourseCard, type CourseSummary } from "./CourseCard";
import "../styles/learn.css";
import "../styles/shared-ui.css";

const LEVELS = ["beginner", "intermediate", "advanced", "all"];
const LANGUAGES: Array<[string, string]> = [
  ["en", "English"],
  ["fr", "French"],
  ["pt", "Portuguese"],
  ["ar", "Arabic"],
  ["sw", "Swahili"],
  ["ha", "Hausa"],
  ["yo", "Yoruba"],
  ["ig", "Igbo"],
  ["am", "Amharic"],
];

/** The course catalogue: search, a chip for each category, filters and a sort. Kept in the address. */
export default function Catalog() {
  useDocumentTitle("Courses");
  const [params, setParams] = useSearchParams();
  const get = (k: string) => params.get(k) ?? "";
  const set = (patch: Record<string, string>) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [k, v] of Object.entries(patch)) {
          if (v) next.set(k, v);
          else next.delete(k);
        }
        return next;
      },
      { replace: true },
    );

  const [typed, setTyped] = useState(get("q"));
  const q = useDebounced(typed.trim());
  useEffect(() => {
    if (get("q") !== q) set({ q });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const category = get("category");
  const price = get("price");
  const level = get("level");
  const language = get("language");
  const rating = get("rating");
  const duration = get("duration");
  const sort = get("sort") || "newest";

  const categories = useQuery({ queryKey: ["courses", "categories"], queryFn: () => unwrap(api.GET("/api/v1/courses/categories")) });
  const list = useCursorList<CourseSummary>(["courses", "catalog", q, category, price, level, language, rating, duration, sort], (cursor) =>
    unwrap(
      api.GET("/api/v1/courses", {
        params: {
          query: {
            limit: 12,
            sort: sort as "newest",
            ...(cursor ? { cursor } : {}),
            ...compact({
              q,
              category,
              access: (price === "free" || price === "paid" ? price : undefined) as "free" | undefined,
              level: level as "beginner",
              language,
              rating_min: rating ? Number(rating) : undefined,
              duration: duration as "short",
            }),
          },
        },
      }),
    ),
  );
  const filtered = Boolean(q || category || price || level || language || rating || duration);

  return (
    <>
      <PageHeader
        eyebrow="Learn"
        title="Courses"
        lead="Practical lessons from people who have done it."
        actions={
          <Link className="wo-btn wo-btn--secondary" to="/app/learn/my">
            My learning
          </Link>
        }
      />

      <div className="wo-catalog__chips" role="group" aria-label="Category">
        <button type="button" className="wo-chip" aria-pressed={category === ""} onClick={() => set({ category: "" })}>
          All
        </button>
        {(categories.data?.categories ?? []).map((c) => (
          <button key={c} type="button" className="wo-chip" aria-pressed={category === c} onClick={() => set({ category: c })}>
            {humanise(c)}
          </button>
        ))}
      </div>

      <form className="wo-catalog__filters" role="search" aria-label="Filter courses" onSubmit={(e) => e.preventDefault()}>
        <Input label="Search" type="search" placeholder="Topic, title or instructor" value={typed} onChange={(e) => setTyped(e.target.value)} />
        <Select label="Price" value={price} onChange={(e) => set({ price: e.target.value })} options={[{ value: "", label: "Free and paid" }, { value: "free", label: "Free" }, { value: "paid", label: "Paid" }]} />
        <Select label="Level" value={level} onChange={(e) => set({ level: e.target.value })} options={[{ value: "", label: "Any level" }, ...LEVELS.map((l) => ({ value: l, label: l === "all" ? "All levels" : humanise(l) }))]} />
        <Select label="Language" value={language} onChange={(e) => set({ language: e.target.value })} options={[{ value: "", label: "Any language" }, ...LANGUAGES.map(([value, label]) => ({ value, label }))]} />
        <Select label="Rating" value={rating} onChange={(e) => set({ rating: e.target.value })} options={[{ value: "", label: "Any rating" }, { value: "4", label: "4 stars and up" }, { value: "3", label: "3 stars and up" }]} />
        <Select label="Length" value={duration} onChange={(e) => set({ duration: e.target.value })} options={[{ value: "", label: "Any length" }, { value: "short", label: "Under 2 hours" }, { value: "medium", label: "2 to 6 hours" }, { value: "long", label: "Over 6 hours" }]} />
        <Select label="Sort by" value={sort} onChange={(e) => set({ sort: e.target.value === "newest" ? "" : e.target.value })} options={[{ value: "newest", label: "Newest" }, { value: "popular", label: "Most popular" }, { value: "rating", label: "Highest rated" }]} />
      </form>

      {list.query.isPending ? <SkeletonCards /> : null}
      {list.query.isError ? (
        <Alert tone="danger" title="We could not load courses">
          {messageOf(list.query.error)}
        </Alert>
      ) : null}
      {list.isEmpty ? (
        <EmptyState title={filtered ? "No courses match" : "No courses yet"}>{filtered ? "Try fewer filters or a different word." : "New courses appear here as they are published."}</EmptyState>
      ) : null}
      <ul className="wo-courses" aria-label="Courses">
        {list.items.map((course) => (
          <li key={course.id}>
            <CourseCard course={course} />
          </li>
        ))}
      </ul>
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
    </>
  );
}
