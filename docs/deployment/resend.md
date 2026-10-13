# Email with Resend

Resend sends the mail. The API sends through it with the adapter `ResendEmailAdapter`, and Resend
reports bounces and complaints back to a webhook. Only you can do these steps (they need your Resend
account and your DNS).

## How mail is sent

- **Account mail** (verification, password reset, approvals, notices) is sent from
  `EMAIL_FROM_TRANSACTIONAL`, on its own subdomain, for example `no-reply@mail.<your domain>`.
- **Newsletters** are sent from `EMAIL_FROM_MARKETING`, on a different subdomain, for example
  `community@news.<your domain>`, so a complaint about a newsletter cannot hurt password resets.
- Every message has a plain text part and a branded HTML part. Newsletters carry one click unsubscribe
  headers that point at `API_BASE_URL`.
- An address that bounces or complains is added to the **suppression list** (kept as a hash) and gets no
  more newsletters. The list is on the admin Email health page, which can also check SPF, DKIM and
  DMARC for both subdomains.
- In development and in tests the fake adapter keeps messages in memory and sends nothing.

## Steps

1. Create a Resend account and add **two domains**: `mail.<your domain>` and `news.<your domain>`
   (Resend, Domains, Add Domain, and pick a region close to your members).
2. Resend shows the DNS records for each. Publish them exactly as shown; see [dns.md](dns.md). Wait
   until both domains read **Verified**.
3. **API key**: Resend, API Keys, create one with the **Sending access** permission, limited to these
   domains. Copy it (it starts with `re_`). It is shown once.
4. **Webhook**: Resend, Webhooks, Add Endpoint:
   - Endpoint URL: `https://api.<your domain>/api/v1/webhooks/email/resend`
   - Events: all of `email.sent`, `email.delivered`, `email.delivery_delayed`, `email.bounced`,
     `email.complained`, `email.failed` (opened and clicked are optional).
   - Copy the **Signing Secret** (it starts with `whsec_`).
   The API checks the signature (Svix style: `svix-id`, `svix-timestamp`, `svix-signature`) over the
   exact bytes it received and answers 401 to anything else, so the URL is safe to leave open.
5. Set on the API and the worker:

   ```
   EMAIL_ADAPTER=apps.integrations.email.resend.ResendEmailAdapter
   RESEND_API_KEY=re_...
   RESEND_WEBHOOK_SECRET=whsec_...
   EMAIL_FROM_TRANSACTIONAL=WO Community <no-reply@mail.<your domain>>
   EMAIL_FROM_MARKETING=WO Community <community@news.<your domain>>
   EMAIL_REPLY_TO=hello@<your domain>
   CAMPAIGN_FOOTER=WO Community, <postal address>
   ```

   The API refuses to start with Resend selected if the key, the secret or either from address is
   missing.
6. Send a test: in the admin console, Email templates, pick one, **Send test**.

## Warming up a new domain

A new sending domain has no reputation. Set `EMAIL_WARMUP_START` to the first sending day
(`YYYY-MM-DD`). Newsletters then send at a small hourly rate that grows each day, and the rest waits
for the next hour. Details and the DMARC steps are in [../email-deliverability.md](../email-deliverability.md).

## Check

- Resend shows both domains Verified.
- The admin Email health page shows SPF, DKIM and DMARC as Good for both domains.
- A test email arrives with a Verified sender and is not in spam.
- Send to a Resend test address that bounces (`bounced@resend.dev`) and confirm it appears on the
  suppression list after the webhook arrives.
