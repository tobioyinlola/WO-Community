# Audit log

**Where:** Admin > Audit log. **Who:** super admins (permission `audit.read`).

Every sensitive action is written to the log in the same step as the action: sign in and out,
failed sign ins, member decisions, role changes, invitations, posts, news, jobs, events, courses,
certificates, mentor decisions, support replies, settings, email template edits and exports. Entries
cannot be edited or deleted: the database refuses it, and each day's entries are chained so tampering
shows. The log starts on the day it was switched on; earlier history is not invented.

- **Filters:** date (today, 7 days, 30 days, or two dates), who did it (name or email), area
  (members, content, jobs, events, courses, certificates, settings, security), result, and text.
  Filters live in the address, so you can share a view.
- **Open an entry** for the full details, what changed (before and after) and the raw record with a
  copy button.
- **Export CSV** downloads what the filters show (up to 50,000 rows). The export is itself logged.
- People are named when you read the log, never stored in it. Passwords, tokens and secrets are
  masked before they are saved. Addresses are not stored; a short reference of each hashed address
  is shown so you can tell two entries came from the same one.
- The dashboard shows the last ten entries under Recent activity.
