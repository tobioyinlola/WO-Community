# Course creator fix

Reported: the admin course creator is not working. This note records the cause, the change and what was checked.

## Root cause

The creator did save a draft, but a course made in it could not be published, so it never reached members. Two rules in
`apps/learning/lms.py` (`publish_checklist`) blocked it:

1. A course needed at least **three** lectures (`MIN_LECTURES_TO_PUBLISH = 3`). A single video course, or a course
   with one or two videos, could never go live.
2. A course needed a **thumbnail image**. The wizard offered the upload as optional on its first step, so the usual
   path (details, links, create) ended on a page that said "Before this can be published" with the Publish button
   disabled.

Found by running the wizard in a browser as an admin: details, two YouTube links, Create draft. The course page listed
"A thumbnail image" and "At least one section and 3 lectures" as missing.

Two smaller faults were found in the same walk:

- The drawer never imported `learn.css`, so its step indicator rendered as a plain numbered list ("1Basics") unless a
  learner page had been opened first in the same session.
- A line that was not a YouTube link was counted as a lesson ("2 lectures will be added") and only failed at the end,
  as a server error.

## What changed

Back end:

- A course publishes with **one module and one lesson**; a cover image is welcome but no longer required.
- `unenrol` (`DELETE /api/v1/courses/{id}/unenrol`): a member can leave a course. The enrolment row stays with
  `ended_at` set, so its lesson progress is kept; enrolling again clears it and picks up where they were. Migration
  `learning.0009_enrolment_ended_at` (reversible). The default `Enrolment.objects` manager hides ended rows;
  `Enrolment.everything` shows them.
- `archive` action on a course (`POST /api/v1/admin/courses/{id}/archive`, audited as `courses.archived`). Learners
  keep their access and progress.
- Deleting a course that has enrolled members is refused with a 409 (`has_learners`) that says to archive it.
- OpenAPI and the generated client are regenerated.

Front end:

- The Add course drawer has four steps: Details, Modules and videos, Pricing, Review.
  - Modules and videos starts with one module and **Add module** adds more. Each module has a title and one YouTube
    link per line. Delete module (with a confirm) and Up/Down buttons keep the numbering right.
  - Each line is checked as it is typed (youtube.com/watch, youtu.be, embed and shorts; every other host is refused);
    the bad line numbers are named and **Continue** stays off until they are fixed.
  - Pricing shows **Free** (chosen) and **Paid** with a **Coming soon** badge, disabled. The model and the price
    fields stay in the data, so paid courses can be switched on later.
  - Review lists modules, lessons and a checklist, and offers **Create and publish**.
  - Outcomes ("What members will learn") can be entered on the first step.
- The course page has **Archive**, **Unpublish** and **Delete course** (drafts and courses nobody joined).
- The learner's course page has **Leave course**.
- The admin and member dashboards greet the signed-in person by name, with an emoji.

## Decisions and limits

- The earlier wizard already created modules, lessons from links, reorder, cover upload, and the access rules: video ids are
  only sent to enrolled members (and visitors on courses opened to them), and lesson endpoints answer 403 or 404 to
  everyone else. These were kept.
- Modules in the drawer can be dragged into order by their handle, and the Up and Down buttons do the same without a
  mouse. A move is announced to screen readers.
- The drawer saves what has been typed on this device (browser storage) as it changes, so closing it or reloading loses
  nothing; it says so, and reopening offers the saved draft with a Start over button. A thumbnail file cannot be kept,
  so it is asked for again. Nothing is created on the server until the last step. If the browser refuses storage, closing
  asks before discarding, as before. After creation, everything is edited on the course page and saved as you go.
- `backend/scripts/seed_sample_courses.py` adds three local samples: one video, three modules, and a draft.
- Lesson notes and per-lesson durations are edited on the course page, not in the drawer.
- Existing names stay: the screens say "lecture" and "section" in places, and the code says module and lesson.
- YouTube links can still be shared by anyone who has one. Use unlisted videos on YouTube for anything you do not want
  passed around.
- Unenrolling hides the enrolment but a certificate already issued stays valid.

## Checks

- Regression test: `test_a_course_with_one_video_and_no_cover_can_be_published` (`apps/learning/tests/test_lms.py`).
- New tests: leaving a course keeps progress and re-enrolling resumes it; unenrolling needs sign in; a course with
  learners cannot be deleted but can be archived.
- Browser: `frontend/e2e/course-creator.spec.ts` (an admin builds a three module course, an invalid link is refused,
  a module is deleted and one moved, Free is kept and Paid is disabled, publish; a one video course with no cover
  publishes; a member finds it, sees no video links before joining, enrols, watches through the
  `youtube-nocookie.com` player, completes it and gets the certificate; leaving and rejoining resumes; a draft is not
  visible to members; live courses with learners are archived).
- Unit tests for the link parser: `frontend/src/admin/youtubeId.test.ts`.
