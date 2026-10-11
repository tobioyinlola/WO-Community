# 0042. Share links

Status: accepted (toolkit stage T3, sharing)

## Decisions

- **A link is a capability, so it is treated like a secret.** The token is 192 random bits shown
  once; only its SHA-256 is stored, so a database leak does not hand out working links. It never
  appears in a log line by design: the public route logs its pattern, not the token.
- **Read only and narrow.** A link points at one deck, prototype, plan summary or score summary.
  Speaker notes, profile fields, unfinished sections and evidence detail are not part of what is
  shown. Content is built from the same services as the owner's screens, so a shared view cannot
  differ from what the owner sees.
- **Every failure is one 404.** Unknown, revoked, expired, deleted-subject and deleted-venture
  links are indistinguishable, and a wrong password is also a 404, so a token or a password cannot
  be probed for state. A password link answers 401 `password_required` to a plain GET so a client
  can ask.
- **Brute force is slowed twice.** A scoped per-address rate limit on the whole route, and a
  failed-password counter per link and address (10 in 15 minutes, then 429).
- **Search engines and caches are told to stay away.** `X-Robots-Tag: noindex, nofollow,
  noarchive`, `Cache-Control: private, no-store` and `Referrer-Policy: no-referrer` on every
  shared page.
- **The owner is in control.** Links can have a password (4 to 72 characters, hashed with the
  platform's password hasher) and an expiry up to a year, are listed with view counts, and are
  revoked at once. Creating and revoking are audited.
- **The page address is the front end's.** The API returns `FRONTEND_BASE_URL/share/{token}`; the
  front end calls `GET /public/share/{token}`.
