# 0029. Mentor applications and mentor profiles

Status: accepted (Stage 3, second slice)

## Decisions

- **Applying never grants anything.** Any active member can apply (`POST /mentor-applications`)
  after accepting the mentor conduct policy. The application captures expertise tags, years of
  experience, current role and company, a LinkedIn link (https on linkedin.com only), industries and
  stages from the managed reference lists, languages, a time zone (checked against the IANA
  database), weekly hours and a motivation of 50 to 1500 characters. All free text is stripped of
  markup. Real availability slots are a separate step (next slice); the application only records
  how many hours a week the person can give.
- **One open application per person**, enforced by a partial unique index, so a double submit is
  settled by the database. A member who is already a mentor cannot apply; after a decline they wait
  30 days. An applicant can edit or withdraw while the application is open.
- **The admin decides** (`mentors.decide`, community admin and above, with MFA): approve, decline
  or request more information. Declining and requesting information both need a reason, which the
  applicant sees and is told about. Answering a request for information (by editing the
  application) puts it back in the queue. Every decision is audited. Decisions are made under a row
  lock, so two admins cannot both act.
- **Approval** creates the mentor profile and gives the member the `mentor` role in one
  transaction. The Mentor badge comes from the role, so it appears wherever badges already do. The
  mentor section of a profile is `GET /mentors/{member id}`; the profiles module cannot import
  mentorship (it sits below it), so the front end asks for the section separately.
- **Invited mentors** already have the role but no profile; their first save of
  `PUT /me/mentor-profile` creates it and then needs every descriptive field. Nobody else can
  create a profile.
- **The directory** (`GET /mentors`) lists approved, non-paused mentors whose account is active,
  filtered by text, expertise tag, industry, stage, country and language, newest approval first with
  keyset paging. Contact details and the LinkedIn link are never returned; the link is visible to
  admins only. A mentor sees their own section while paused. Pausing hides the mentor from the
  directory and (later) recommendations without touching anything already agreed.
- **Revoking** (`POST /admin/mentors/{id}/revoke`, reason and a recent MFA check) removes the role,
  badge and listing, keeps the history and tells the mentor. Restoring needs no step-up. A revoked
  mentor can also apply again. Roles are read on every request, so revocation takes effect
  immediately. A `MentorRevoked` event is published so booking (next slice) can cancel future
  sessions.
- **Elsewhere.** The dashboard mentorship section reports pending applications and mentor counts;
  segments gained `mentor_applicant` and `mentor_approved`; analytics records
  `mentor_application_submitted`, `_approved` and `_declined`; admins are notified of each new
  application, applicants of each outcome.

## Consequences

Availability, matching, requests, booking, calendar integrations, reminders and feedback follow in
later slices. The mentor rating fields exist (count and total) but nothing writes them until
feedback exists. The registration option "I am also a mentor" is a front-end step that calls the
application endpoint after the account exists.
