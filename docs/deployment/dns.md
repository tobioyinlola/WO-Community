# DNS

Everything lives on subdomains of one domain, written `<domain>` below. The records come from the
services, which show their own values; copy those exactly. Only you can publish DNS records.

If the domain's DNS is on Cloudflare, set every record to **DNS only** (grey cloud) unless a step says
otherwise. Railway, Vercel and Resend each check their own record and issue certificates themselves.

| Host | Type | Value | From |
|------|------|-------|------|
| `app` | CNAME | the target Vercel shows (usually `cname.vercel-dns.com`) | [vercel.md](vercel.md) |
| `api` | CNAME | the target Railway shows (`xxxx.up.railway.app`) | [railway.md](railway.md) |
| `_railway-verify.api` | TXT | the value Railway shows | [railway.md](railway.md) |
| `media` | CNAME | added for you when you connect the custom domain in R2, if the domain is on Cloudflare | [cloudflare-r2.md](cloudflare-r2.md) |
| `mail`, `send.mail`, `resend._domainkey.mail` | MX, TXT (SPF), TXT (DKIM) | the values Resend shows for `mail.<domain>` | [resend.md](resend.md) |
| `news`, `send.news`, `resend._domainkey.news` | MX, TXT (SPF), TXT (DKIM) | the values Resend shows for `news.<domain>` | [resend.md](resend.md) |
| `_dmarc` | TXT | `v=DMARC1; p=none; rua=mailto:dmarc@<domain>; adkim=s; aspf=s` | below |

## DMARC

Start with `p=none` so nothing is blocked while you watch the reports. After two to four weeks of clean
reports, change to `p=quarantine`, and later `p=reject`. Send the reports to a mailbox you read. The
admin Email health page shows DMARC on `p=none` as "Needs attention" until you tighten it.

## Order that avoids waiting

1. Publish the Resend records first (they take longest to verify).
2. Publish `api` and its TXT, then wait for Railway to show the domain as active.
3. Publish `app` for Vercel.
4. Publish `_dmarc`.

## Check

```
nslookup app.<domain>
nslookup api.<domain>
nslookup -type=TXT _dmarc.<domain>
```

Records can take from a few minutes to a day to appear. The first request over https works only after
the host has issued its certificate (a few minutes after the record is seen).
