# 0028. The learning hub

Status: accepted (Stage 3, first slice)

## Decisions

- **Structure.** A course has ordered modules, and a module has ordered lessons of three types:
  `video`, `reading` and `resource`. Positions are unique per parent but the constraint is deferred,
  so a reorder rewrites positions inside one transaction without tripping over itself. Deleting
  closes the gap. Reordering requires every item to be listed once, so two admins cannot silently
  lose a lesson.
- **Video is YouTube, validated and nothing else.** An admin enters a link; the backend accepts only
  `https` addresses on `youtube.com`, `www.youtube.com`, `m.youtube.com` or `youtu.be`, with no
  credentials or odd port, that point at a single video (watch, embed, shorts, live, `youtu.be/ID`)
  with a real 11-character id. It stores the id and a normalised address, and the API returns the id
  and a privacy-enhanced `youtube-nocookie.com` embed address. Playlists, channels, other hosts,
  lookalike hosts and malformed ids are refused. The check is a pure function with no network use.
  `video_provider` is stored so a later move to a protected host needs no data migration.
- **Reading lessons** hold rich text cleaned by the same allow list as posts. **Resource lessons**
  hold an https link and a display name. The design also mentions downloadable files stored by us;
  that needs document uploads (type sniffing, virus scanning, private signed downloads) beyond the
  current image-only upload pipeline, so resource files are links for now. This is a deliberate
  gap, not an oversight.
- **Free and paid.** Free courses are open to any active member with one idempotent enrol action.
  Paid courses show price (whole minor units plus an ISO currency, checked by a database constraint)
  and are locked: enrolling answers 402 until purchasing exists (Stage 4). Meanwhile an admin can
  **grant** access, which creates an enrolment with source `grant`; purchases will create source
  `purchase`. Either gives the same entitlement, so Stage 4 only adds a new way to create one.
- **The video id is not sent to anyone without access.** Lesson detail answers 403 for a member who
  is not enrolled, and the course outline never includes video ids, so a paid lesson's address is
  not exposed through the API. (As the design warns, a video link that has leaked can still be
  watched; the decision on a protected host for paid video remains for before paid courses launch.)
- **Visitors.** Per course, a free course can be opened to visitors. Then `GET /lessons/{id}`
  works without logging in, under a stricter rate limit than members, and `GET /public/courses`
  lists these courses with their outline. Paid courses can never be opened to visitors.
- **Progress.** `PUT /lessons/{id}/progress` stores the latest position and a completion flag
  (the player sends it about every 15 seconds and on pause). Progress is limited to 60 calls a
  minute. The course shows percent complete and a resume point: the last lesson touched if
  unfinished, otherwise the next unfinished one. Finishing the last lesson completes the course
  once; adding a lesson later does not undo a completion.
- **Certificates.** Completion publishes an event; a worker creates the certificate (a random 12
  character code without look-alike letters, the member's name and the course title as they were
  that day) and notifies the member. Issuing is idempotent. The PDF is generated on request from
  those stored facts by a small built-in writer (one page, standard fonts, so non-Western
  characters in a name show as `?`), so no file containing a person's name is stored publicly.
  Anyone can verify a code at `GET /public/certificates/{code}`, which shows the holder, course and
  date and nothing else. A course can switch certificates off.
- **Unpublishing** hides a course from the catalogue but people already enrolled keep access and
  progress. Removing hides it from everyone.
- **Ratings** are one per enrolled member (changeable), 1 to 5 with optional feedback; the course
  keeps a count and total so the average needs no scan. Feedback is visible to admins.
- **Admin** (`courses.manage`: content editors and above, with MFA): create and edit courses (ETag),
  modules and lessons, reorder, duplicate (structure only; no enrolments, ratings or cover), publish
  and unpublish, set the cover, see enrolments with percent complete, per-lesson completion, rating
  summary and written feedback, and grant access. Everything is audited.
- **Elsewhere.** The dashboard's learning section now reports courses, enrolments, completions and
  certificates; segments gained the `learner_free`, `learner_paid` and `course_completed` tags; and
  the analytics events `course_enrolled`, `lesson_started`, `lesson_completed` and
  `course_completed` are recorded.

## Consequences

Quizzes, drip release, course prerequisites, learning paths, per-lesson comments and downloadable
files stored by us are not built. Purchasing, receipts and the paid-video decision belong to Stage 4.
