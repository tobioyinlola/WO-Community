# 0011. Public directory

Status: accepted (Stage 1)

## Decisions

- **A read model, not live queries.** The `directory` module keeps `PublicStartup` and
  `PublicFounder` tables. Each row is built from the same projection every other reader uses
  (`core/visibility`, audience = public) and stores the finished `card` and `detail` JSON the API
  returns, plus indexed filter and search columns. Public search and ranking therefore only ever
  touch rows made of public data; a private field cannot be matched, scored or leaked through
  ordering. Serializers repeat the shape as an output allow-list.
- **Who appears.** A startup appears when its owner opted in (`directory_opt_in`), the owner is an
  active member, and its basics are public. A founder has a page when their *basics* group is
  public, whether or not they have a listed startup.
- **Founders and startups link only if both agree.** A founder's name shows on a startup card, and
  the startup shows on the founder's page, only when the founder's basics are public *and* the
  startup's team group is public. Neither side can reveal the other.
- **Refresh by event, safety net by schedule.** Changes publish outbox events (`StartupUpdated`,
  `ProfileUpdated`, member approved, reinstated, suspended, removed). Directory handlers rebuild
  exactly the affected rows (and the pages that link to them) and ask the CDN to purge the paths.
  Handlers are idempotent. An hourly `directory.reconcile` rebuilds everything and removes rows
  whose source no longer qualifies; `manage.py rebuild_directory` does the same by hand.
  Normal lag is seconds, inside the five minute requirement.
- **Takedown is immediate.** Reads also filter on the owner's *current* status through a
  subquery on active members, so a suspended or removed member's pages return 404 on the very next
  request, before any handler has run. The CDN purge follows; until it lands a cached copy can live
  for at most its five minute lifetime.
- **Cursors, not offsets.** Browsing uses keyset pagination. Every ordering ends in the unique id and
  all columns ascend (newest-first is stored as the negated timestamp, featured as rank 0), so
  "after this row" is an indexed lexicographic comparison. Cursors are opaque, carry their sort, and
  are validated strictly (400 on anything else). A reader is not disturbed by new listings.
- **Search.** Postgres full text (`simple` configuration, so names in any language work), weighted
  name > pitch and founder > sector, city and skills > description, combined with substring and
  trigram matching on the name so partial words and typos find the right startup. Quotes and `-term`
  exclusions switch to exact full-text rules. A search returns its best matches (up to 50) without a
  cursor because relevance order has no stable position; refine instead of paging. Filters:
  country, sector, stage, up to five founder skills (all must match), featured only. Searches have
  their own 60 per minute limit; browsing does not.
- **Caching.** Public GETs are anonymous (an Authorization header is ignored, no cookies are set) and
  carry `Cache-Control: public, max-age=300, stale-while-revalidate=600, stale-if-error=86400`,
  a content ETag and `304` on `If-None-Match`. The sitemap caches for an hour. A CDN purge adapter
  sits behind `CDN_PURGER` (a logging no-op until a CDN is chosen).
- **SEO.** Detail responses include a canonical `url` and schema.org JSON-LD (`Organization`,
  `Person`) built only from public fields. `GET /public/sitemap` lists every public page with its
  last change for the front end to turn into `sitemap.xml`.
- **Featuring.** `POST /admin/startups/{id}/feature` and `/unfeature` (permission
  `directory.feature`, MFA, audited). Only listed startups can be featured. Featured startups sort
  first in every order; `featured=true` lists only them for the home page.

## Consequences

Because founders' country only exists in the read model when they made their location public,
founder filtering by country finds only those who opted in. Startup cards show founders only when
the team is public, which is not the default; the sign-up and settings screens should explain this.
News, events and jobs under `/public` belong to later stages. Redis page caching was left out: the
read model is already one indexed query per request and the CDN absorbs repeat traffic.
