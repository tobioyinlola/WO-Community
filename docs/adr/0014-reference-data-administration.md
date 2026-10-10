# 0014. Administering the reference lists

Status: accepted (Stage 1)

## Decisions

- **Scope.** Admins manage the three database lists: sectors, stages and skills
  (`/admin/reference/{sectors|stages|skills}`). Countries are the ISO 3166-1 list and stay in code,
  because the standard fixes them. Post and course categories will use the same service when those
  modules exist.
- **Permission.** `reference.manage`, held by community admins and super admins, with MFA. Nothing
  here needs step-up: no operation destroys data that is in use.
- **Slugs are permanent.** They appear in URLs, filters and the directory's stored rows. The API
  refuses a slug change; names, order and the active flag can change. Names are unique ignoring
  case, enforced by the database as well as the service.
- **Retire, do not break.** Setting `active = false` hides an entry from the public lists and from
  new choices (registration, startup and profile edits), but records that already use it keep it. A
  startup may keep a retired sector and still be edited; it just cannot move to a retired one. This
  fixed a latent bug where changing a startup's stage re-validated its current sector and would have
  failed once that sector was retired.
- **Deleting is for mistakes.** An entry can be deleted only when nothing uses it (409 `in_use`
  otherwise, with the advice to retire it). The database foreign keys use PROTECT as the last line
  of defence.
- **Usage counts without upward imports.** The reference module sits at the bottom of the stack and
  cannot see its users. Startups and profiles register small counters with it at start up
  (`reference.usage`), each answering one grouped query, so the admin list shows how many records use
  every entry in a fixed number of queries.
- **Changes reach the public pages.** Every change publishes `reference.changed`. The directory
  rebuilds exactly the pages that show the changed entry (a renamed sector refreshes that sector's
  startups; a renamed skill refreshes the founders who hold it) and purges the cached public list
  for that kind. A retired entry does not take listed startups down. Adding an entry rebuilds nothing.
- **Audit in the same transaction.** Each create, update, delete and reorder writes an audit record
  with before and after values. The audit write lives in the admin layer because the reference and
  audit modules are siblings and cannot import each other.
- **Ordering.** `PUT .../order` takes every entry's id once, in the order wanted (409 if the list
  changed since it was loaded). Lists are capped at 200 entries.

## Consequences

Renaming an entry is immediate for the API and eventual (seconds) for the directory's read model and
the CDN. Public reference lists are cached for an hour at the edge until the purge adapter is backed
by a real CDN; until then a change can take up to an hour to show on cached lists.
