import { useQuery } from "@tanstack/react-query";
import { Navigate, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { ErrorState, SkeletonRows } from "../ui/blocks";

/** Old course links (`/app/learn/<id>`) open the course page. */
export function CourseRedirect() {
  const { id = "" } = useParams();
  return <Navigate to={`/app/learn/courses/${id}`} replace />;
}

/** Old lesson links (`/app/learn/lesson/<id>`) find the course and open the lecture. */
export function LessonRedirect() {
  const { id = "" } = useParams();
  const lesson = useQuery({ queryKey: ["lesson", id], queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: id } } })), retry: false });
  if (lesson.isPending) return <SkeletonRows />;
  if (lesson.isError || !lesson.data) return <ErrorState error={lesson.error} onRetry={() => void lesson.refetch()} />;
  return <Navigate to={`/app/learn/courses/${lesson.data.course.slug}/lecture/${id}`} replace />;
}
