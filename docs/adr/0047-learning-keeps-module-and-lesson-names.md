# 0047. Learning keeps `Module` and `Lesson` as storage names; the screens say "section" and "lecture"

Status: accepted

## Context

The change request describes courses made of sections and lectures. The learning app already stores
`Module` and `Lesson` rows, and the API, the tests, the analytics events, the notification payloads and
every link already use those words (`/lessons/{id}`, `lesson_id`, `LessonProgress`).

## Decision

Keep `Module` and `Lesson` in the database, the Python code and the URLs. The interface, the OpenAPI
descriptions that a person reads and the documentation say **section** and **lecture**. The new tables
that sit beside them (`LectureQuestion`, `LectureAnswer`, `LectureNote`) use the interface word, because
they are new and read better in the code; they point at `Lesson`.

## Consequences

- No rename migration, no breaking change to links that already exist, and no second vocabulary inside
  one module's code.
- A reader of the code has to know that a lesson is shown as a lecture. `docs/changes/learning.md`
  says so at the top.
- If the names are ever unified it is a mechanical rename, and it can be done without a data change by
  renaming the tables in one migration.
