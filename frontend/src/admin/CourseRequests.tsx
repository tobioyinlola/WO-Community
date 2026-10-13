import { PageHeader, useDocumentTitle } from "../ui/blocks";
import { Requests } from "./CourseEngage";

/** Requests for access to paid courses, across every course. */
export default function CourseRequests() {
  useDocumentTitle("Enrolment requests");
  return (
    <>
      <PageHeader eyebrow="Content" title="Enrolment requests" lead="Members asking for a paid course while payments are off." />
      <Requests courseId={null} />
    </>
  );
}
