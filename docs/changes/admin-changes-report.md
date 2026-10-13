# Admin side changes: final report

## What was built

| # | Change | Where to look |
|---|--------|---------------|
| 1 | Audit log page, API, CSV export (up to 50,000 rows), dashboard recent activity, wider action coverage, no personal data in labels | `apps/audit`, `apps/adminconsole/audit_views.py`, `frontend/src/admin/AuditLog.tsx`, [guide](../admin-guide/audit-log.md) |
| 2 | Certificates: no QR code or verify link, signatory name only (default "Onyeka Akumah", set in settings) | `apps/learning/pdf.py`, `docs/changes/certificates.md` |
| 3 | Member drawer from a name click, `/admin/members/:id`, resend verification | `apps/adminconsole/member_detail.py`, `MemberDrawer.tsx` |
| 4 | Invitations: email chips, per address check, merge of repeats, batch send with idempotency | `apps/accounts/invitations.py`, `EmailChips.tsx` |
| 5 | Team posts: post as the team, pin with a lapse date, comments off, audience, schedule, moderate any post with a reason, author notified | `apps/feed`, `TeamPostForm.tsx` |
| 6 | Dashboard banner: moving ticker, dates, types, dismiss, reduced motion, ETag, End now | `apps/editorial`, `ui/BannerTicker.tsx` |
| 7 | Jobs: members and admins post, admin posts go live, member posts wait; apply by https link or email only. **On platform applications removed, as the brief says.** Admin tabs, bulk approve, 30 day default | `apps/jobs`, `AdminJobs.tsx` |
| 8 | Approval alert emails (first at once, 15 minute summary, daily summary, per admin switches), email health with SPF/DKIM/DMARC checks, suppression list, warm up limit, 19 branded templates with editor, preview, test send, history, restore, reset; newsletters use the same layout and show the audience size before sending | `apps/notifications`, `apps/integrations/dns.py`, [deliverability](../email-deliverability.md) |

Admin guides for each are in `docs/admin-guide/`.

## Migrations

audit 0002, learning 0008, feed 0007, editorial 0003, jobs 0003 (drops job applications, ignored by the
migration lint on purpose), jobs 0004, notifications 0004 and 0005. All applied to the dev database.

## Decisions

- The audit permission keeps its name, `audit.read`.
- The audit log shows the network address as a short reference (the raw address is not stored).
- The CSV export is made in one request, capped at 50,000 rows.
- `campaigns.send` is the broadcast permission.
- Audit labels never hold names or emails; people are named when the log is read.
- No password change audit entry, because there is no change password endpoint yet.
- The daily "still waiting" summary covers the kinds that have a queue count.
- The paid session access alert was not built.

## Verification

- Backend: 3661 passed outside adminconsole, notifications and campaigns, and 1178 passed there. One
  test, `test_a_rewritten_day_no_longer_matches_its_anchor`, failed once in the full run and passes alone
  and with the audit and integrations tests, so it looks order dependent; not investigated further.
- `ruff`, `black`, `mypy`, import-linter, `tsc`, `eslint` clean. 119 frontend unit tests pass.
- Browser (Edge): `admin-changes.spec.ts` 10 of 10. The 360px accessibility check passes.
- The browser run found and fixed three real bugs: the audit export sent no sign in token, a confirm
  dialog opened from a drawer sat under the drawer and could not be clicked, and the new feed badges
  made the feed scroll sideways on phones.
- All 19 email templates render with no unfilled variable, the sign off in both parts, https links only
  (apart from the local dev logo address), a subject under 79 characters, an unsubscribe link on
  newsletters, and no spam trigger words (a simple word check, not SpamAssassin).

## Not verified

- Some older browser tests could not run because the dev data they rely on was used up by earlier runs:
  "a report is acted on", "approved from the keyboard", "books a mentor", and the editor two step
  sign in. Reseed the dev database to run them again.
- Full screenshots in light and dark on desktop and phone were not captured (the app is light only), and
  the axe scan was run by the existing accessibility spec at 360px only in the last run.
- Real delivery, SPF, DKIM and DMARC results cannot be seen from here.

## Steps only the owner can do

1. Publish SPF, DKIM, DMARC and the return path DNS records for the sending domains.
2. Verify the domain with the email provider.
3. Create the provider API key and webhook secret and set them.
4. Host the logo PNG over https and set `EMAIL_LOGO_URL`.
5. Set `CAMPAIGN_FOOTER` to the organisation name and postal line.
6. Set `EMAIL_WARMUP_START` and raise the hourly limit as the domain warms up.
7. Watch the DMARC reports and move DMARC from `p=none` to a stricter policy.
