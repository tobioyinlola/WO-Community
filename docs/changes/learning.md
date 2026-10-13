# Learning

The learning area is a small course platform: members browse a catalogue, open a course page, enrol, and
learn in a player. Editors build courses in the console.

## Members

| Route | What it is |
| --- | --- |
| `/app/learn` | Catalogue with search, category chips, filters (level, price, language, rating, duration) and sort |
| `/app/learn/courses/:ref` | Course page: what you will learn, curriculum, reviews, price and the way in |
| `/app/learn/courses/:ref/lecture/:lessonId` | Player: video, Previous / Mark complete / Next, tabs for Overview, Q&A, Notes, Reviews, Announcements |
| `/app/learn/my` | My learning: all, in progress, completed, saved |
| `/app/learn/certificates` | Certificates earned |

Old links (`/app/learn/:id`, `/app/learn/lesson/:id`) redirect to the new routes.

The button on a course page depends on the state: **Enrol for free**, **Request access** (paid, while
payments are off, see ADR 0048), **Request sent**, **Enrolment closed**, **Start learning** or
**Continue learning**.

Keyboard: `N` and `P` move to the next and previous lecture when focus is not in a field.

### Video

Lectures play YouTube videos through the privacy-enhanced domain (`youtube-nocookie.com`). The player loads
the YouTube IFrame API to report progress and falls back to a plain embedded frame if the script cannot
load. The content security policy must allow `https://www.youtube.com` for scripts and
`https://www.youtube-nocookie.com` for frames. Only YouTube video links are accepted; the server parses
the link and stores the video id, and a title and thumbnail are fetched through oEmbed when YouTube can be
asked.

## Console

| Route | What it is |
| --- | --- |
| `/admin/courses` | All courses with tiles, status tabs, search and a price filter. **Add course** opens a right-hand drawer |
| `/admin/courses/:id` | One course: Curriculum, Learners, Requests, Reviews, Q&A, Announcements, Settings |
| `/admin/course-requests` | Waiting requests across every course |

**Add course** is a four step wizard in the shared drawer: basics and thumbnail, lectures from pasted
YouTube links, price and access, review. It creates a draft and publishes only if asked. Publishing needs a
title, description, category, thumbnail, at least one section with lectures, a valid link on every video
lecture and a price or free; the course page lists whatever is missing and the Publish buttons wait for it.

Learners can be exported as CSV, removed (their certificate stays), and announcements are sent to every
enrolled learner in the app and by email. Reviews, questions and answers can be hidden and restored; a
hidden review leaves the average.
