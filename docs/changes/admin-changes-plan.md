# Admin changes: plan

Findings from reading the repository, per section, and what will be added or changed. Work follows
the order in the brief; each step is finished and checked before the next.

## 1. Audit log

Exists: `apps/audit` with a monthly partitioned, append only table (UPDATE and DELETE rejected by a
trigger), a hash chain per day, `audit.record(...)`, and about 120 action keys already written from
the service layer. Permission `audit.read`. Nav entry is marked "coming soon". No way to read it.

Decisions:
- Keep the permission name `audit.read` (the brief says `audit.view`); renaming would break the roles
  already assigned. Super admin only by default.
- Raw IP addresses and user agents stay unstored (an existing privacy test requires it). The page
  shows a short reference of the IP hash, which still lets an admin see that two entries came from
  the same address.
- New columns by an additive migration: `outcome`, `request_id`, `target_label`, `actor_label`.
  They are not part of the hash chain, so every existing row still verifies.
- Cursor pagination on `(created_at, seq)`, filters in the URL, CSV export, redaction of secrets.
- The log starts at deployment; earlier history is not invented (stated on the page).

Adds: list, detail and export endpoints, the page with filters and drawer, the dashboard card, tests.
Then: fill action gaps (sign out, password change, news, certificates issued, settings, exports).

## 2. Certificates

Exists: certificate model with `holder_name` and `course_title` already snapshotted, PDF drawing in
`apps/learning/pdf.py`, a QR code and verification URL, a signatory name and title in
`CertificateSettings`. Change: remove QR and URL, print the signatory as a name only (default
Onyeka Akumah), keep the ID, fit long text, test two members and two courses.

## 3. Member drawer

Admin members list exists. Adds the name link, `/admin/members/:id` drawer route and
`GET /admin/members/:id/` with the sections in the brief.

## 4. Invitations

Invitation APIs and bulk import exist. Adds the chip input, per email results and idempotency key.

## 5. Admin posting, 6. News banner

Feed and editorial apps exist. Adds admin post options, scheduling, the banner fields and endpoint.

## 7. Jobs

Jobs already have status, approval, expiry and external apply methods.

**Conflict to settle with the product owner:** earlier in this project the brief asked for job
applications to be received and managed on the platform, and they were built (`JobApplication`, an
apply form, an applicants list, an admin page). Section 7.2 now says applications must never be
received on the platform and any such feature must be removed. Removing it deletes data and the
admin page just built, so it waits for a yes.

## 8. Email

Exists: provider adapters under `apps/integrations/email`, a suppression list, delivery events,
campaigns and segments. Adds templates, deliverability checks, admin approval emails and the docs.
Several parts need DNS and provider access that only the owner has.

## 9 to 11

Permissions, documentation, and the full verification run come last.
