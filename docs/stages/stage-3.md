# Stage 3: Learning and mentorship

Scope from the brief: courses, progress, certificates, YouTube URL validation, lesson progress, then
mentor applications and approval, mentor profile, availability, matching, requests, booking with
exclusion constraints, Google and Zoom adapters, reminders and feedback.

## Slice 1: the learning hub (done)

Design and trade-offs are in ADR 0028.

| Endpoint | What it does |
|---|---|
| `GET /courses`, `GET /courses/categories`, `GET /courses/{id}` | Catalogue (filter text, category, level, access, `enrolled`), and a course with its outline, locks, progress, resume point and your rating. |
| `POST /courses/{id}/enrol` | One action for free courses; 402 for paid ones until purchasing exists. |
| `GET /me/courses` | Your courses with percent complete. |
| `GET /lessons/{id}` | Open a lesson (video id and privacy-enhanced embed address, reading text, or resource link). Visitors allowed on courses opened to them. |
| `PUT /lessons/{id}/progress` | Save position and completion; finishing the last lesson completes the course. |
| `PUT /courses/{id}/rating` | Rate 1 to 5 with optional feedback (enrolled members). |
| `GET /certificates`, `/certificates/{id}`, `/certificates/{id}/pdf` | Your certificates and the PDF download. |
| `GET /public/courses`, `/public/courses/{slug}`, `/public/certificates/{code}` | Courses open to visitors, and certificate verification. |
| `/admin/courses...`, `/admin/modules...`, `/admin/lessons...` | Author, reorder, duplicate, publish, cover, stats, enrolments, ratings, grant access. |

Notices: certificate ready, access granted. Segments: `learner_free`, `learner_paid`,
`course_completed`. The dashboard has a live learning section.

## Slice 2: mentor applications and profiles (done)

Design in ADR 0029. Endpoints: `POST /mentor-applications`, `GET /me/mentor-application`,
`PATCH` and `DELETE /mentor-applications/{id}`, `GET /mentors`, `GET /mentors/{member id}`,
`GET` and `PUT /me/mentor-profile`; admin: `GET /admin/mentor-applications`, `.../{id}`,
`POST .../{id}/decision`, `GET /admin/mentors`, `POST /admin/mentors/{id}/revoke` and `/restore`.

## Still to do in Stage 3

1. Mentorship, remaining: availability, matching and
   recommendations, requests, booking with exclusion constraints, Google Meet and Zoom adapters,
   reminders, rescheduling and cancelling, feedback.
2. Downloadable course files stored by us (needs document uploads).
3. Decision before paid courses launch (Stage 4): whether embedded YouTube plus the application
   lock is enough for paid video.
4. The CDN purger (provider decision still pending).
