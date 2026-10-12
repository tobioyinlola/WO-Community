# 0046. Cloudflare for the CDN and cache purge

Status: accepted

## Decision

Public pages and media are served through Cloudflare. When content changes, the platform purges
the affected addresses through `apps.integrations.cdn.cloudflare.CloudflarePurger`
(`CDN_PURGER=apps.integrations.cdn.cloudflare.CloudflarePurger`).

- **Purge by URL**, one request per 30 addresses, with an API token scoped to *Cache Purge* on the
  one zone (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`). The token is read from the environment
  only and never appears in an error message.
- **`CDN_ORIGIN_URL`** is the public host behind Cloudflare. Callers pass API paths; the adapter
  makes full addresses.
- **Failure is not fatal.** A rejected or failed purge raises, callers log and carry on, and pages
  expire on their own five minute lifetime. Listing pages with query strings are not purged by
  address and rely on that lifetime; purging by prefix is an Enterprise feature and is not assumed.
- **Production refuses to start** with this purger selected and any of the three values missing.

## Still to do on the Cloudflare side

Create the zone token with only Cache Purge, set a cache rule that honours the origin's
`Cache-Control` (the public API sends `public, max-age=300, stale-while-revalidate=600`), and keep
authenticated routes and `/api/v1/toolkit/public/share/*` uncached (the origin already sends
`private, no-store`).
