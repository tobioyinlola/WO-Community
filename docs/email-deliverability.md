# Email deliverability

This is the checklist for making sure WO Community email reaches the inbox. The code does its half
(correct headers, separate streams, suppression, a warm up cap, plain text and HTML in every
message). The other half is DNS and the provider account, and only the owner can do it.

**What nobody can promise from code:** whether a message lands in the inbox depends on DNS being
published, the domain being verified with the provider, and the sender's reputation, which is
built by sending wanted mail over weeks. Admin > Email > Email health shows what can be checked
from here (the SPF, DKIM and DMARC records as public DNS shows them). It cannot see the provider's
verification or your reputation.

## 1. Choose two sending subdomains

Never send from the main website domain, and never from a personal mailbox.

| Stream | Used for | Example address | Setting |
| --- | --- | --- | --- |
| Account mail (transactional) | verification, approvals, invitations, password reset, notifications, approval alerts to admins | `WO Community <no-reply@mail.example.org>` | `EMAIL_FROM_TRANSACTIONAL` |
| Broadcast | newsletters, announcements, digests | `WO Community <community@news.example.org>` | `EMAIL_FROM_MARKETING` |

Two domains keep the streams apart: a complaint about a newsletter cannot damage the reputation of
the password reset email. Set `EMAIL_REPLY_TO` to a mailbox a person reads.

## 2. Publish the DNS records

Add each sending subdomain to the provider (Resend by default) and publish exactly the records it
shows. The shapes are:

**SPF**, a TXT record on each sending subdomain, one per name:

```
mail.example.org.   TXT   "v=spf1 include:<provider's include> ~all"
```

**DKIM**, 2048 bit, signed by the provider. It is a TXT (or CNAME) record the provider gives you at
`<selector>._domainkey.<subdomain>`. If the selector is not `resend`, set
`EMAIL_DKIM_SELECTORS=<selector>` so the health page looks in the right place.

**DMARC**, a TXT record at `_dmarc.<subdomain>`. Start by watching, then tighten:

```
_dmarc.mail.example.org.  TXT  "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.org; adkim=s; aspf=s"
```

1. Week 1 to 4: `p=none`. Read the reports. Everything legitimate should pass SPF or DKIM aligned.
2. Then `p=quarantine; pct=25`, raising `pct` to 100 over a few weeks.
3. Finally `p=reject`.

**Return path.** The provider will ask for a return path (a CNAME such as `send.mail.example.org`
or an MX). Publish it so bounces come back to the provider and the envelope sender matches your
domain.

After publishing, wait for DNS to spread (minutes to a day), press **Verify** at the provider, then
open Admin > Email health and press **Check again**. Each domain should show SPF Good, DKIM Good,
and DMARC Good (or "Needs attention" while still on `p=none`, which is expected at first).

## 3. Provider settings the app needs

| Setting | What it is |
| --- | --- |
| `EMAIL_ADAPTER` | `apps.integrations.email.resend.ResendEmailAdapter` in production (the default is a fake that sends nothing) |
| `RESEND_API_KEY` | A sending key for the verified domains |
| `RESEND_WEBHOOK_SECRET` | The signing secret of the webhook that reports delivered, bounced and complained. Point the webhook at `/api/v1/webhooks/email/resend` |
| `EMAIL_FROM_TRANSACTIONAL`, `EMAIL_FROM_MARKETING` | The two From addresses above |
| `EMAIL_REPLY_TO` | A monitored mailbox |
| `EMAIL_LOGO_URL` | A hosted https PNG of the logo (default `<site>/assets/email-logo.png`; the file must be uploaded there) |
| `EMAIL_SIGNOFF` | The closing lines of every email (default `Best regards,` and `The WO Community Team`) |
| `CAMPAIGN_FOOTER` | The organisation and postal address line shown in the footer of broadcasts |
| `EMAIL_DKIM_SELECTORS` | The DKIM selectors to check on the health page |
| `EMAIL_WARMUP_START`, `EMAIL_HOURLY_CAP` | The warm up limit, below |

Webhook signatures are verified; an unsigned or replayed delivery is rejected.

## 4. Warm up a new domain

A new domain that suddenly sends thousands of emails looks like spam. Set `EMAIL_WARMUP_START` to
the first day of broadcasting (`YYYY-MM-DD`). Broadcast mail per hour is then limited by this
schedule (account mail is never limited):

| Day | Broadcast emails per hour |
| --- | --- |
| 1 to 2 | 50 |
| 3 to 4 | 100 |
| 5 to 7 | 250 |
| 8 to 10 | 500 |
| 11 to 14 | 1,000 |
| 15 to 21 | 2,500 |
| 22 to 28 | 5,000 |
| 29 onwards | 10,000, and the limit lifts after another two weeks |

To use your own number instead, set `EMAIL_HOURLY_CAP` (for example `200`; `0` means no limit and
`-1`, the default, follows the schedule). A large newsletter simply takes longer to finish while the
limit is in force; nothing is lost. Start with your most engaged members.

## 5. What the code already does

- **Two streams** with separate From domains, and a health page that says if they share one.
- **Verified addresses only.** Broadcasts go to members who confirmed their email and agreed to
  hear from us. Account mail about a person's own account is always sent.
- **One click unsubscribe.** Every broadcast carries `List-Unsubscribe` and
  `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058) and a visible unsubscribe link.
- **Suppression.** Hard bounces and spam complaints reported by the provider's signed webhooks are
  suppressed automatically; unsubscribes too. Soft bounces are retried by the provider and then
  reported as bounces, which suppresses the address. The list is in Admin > Email health, and only
  a super admin can remove an entry (with a fresh two step check, recorded in the audit log).
- **Good content.** Every email has an HTML and a plain text part from the same words, a 600 pixel
  single column layout that adapts to phones, a real `From` name, alt text on the logo, absolute
  https links on our own domain, one button, no image only mail, and subjects checked on save
  for all capitals, `!!` and other spam patterns.
- **Idempotent sending** with a message id per email, retries with backoff, and a rate limited queue.
- **Admin approval alerts** are at most one email at once and then one summary every 15 minutes per
  kind, and each admin can switch each kind off.

## 6. Before the first broadcast

1. Send a test of each template (Admin > Email templates > Send me a test) to a Gmail, an Outlook
   and a work address. Check it is not in spam, the logo shows, and the button works.
2. Send the same to a throwaway address at a spam checker such as mail-tester.com and fix anything
   below 9 out of 10.
3. Confirm the footer shows your organisation and postal address (`CAMPAIGN_FOOTER`).
4. Confirm the unsubscribe link works and that unsubscribing adds the address to the suppression list.

## 7. Steps only the owner can complete

1. Buy or choose the domain and create the two sending subdomains.
2. Add them in the provider, publish the SPF, DKIM, DMARC and return path records, and press Verify.
3. Create the API key and the webhook, and set the environment values in section 3.
4. Upload the logo PNG to the address in `EMAIL_LOGO_URL`.
5. Set the warm up start date and follow it; watch complaints and bounces on the health page.
6. Read the DMARC reports and move the policy to `quarantine`, then `reject`.
