# 0050. Search ranks by similarity inside what the searcher may see

Status: accepted

## Context

The top bar search has to find members, startups, jobs, mentors, events, news and courses, remember a
person's recent terms, and offer administrators a second set of groups. Search is where a privacy
mistake is most likely to leak: a hit proves that something exists, and a snippet shows what it says.

## Decision

- **Visibility first, ranking second.** Each searcher starts from the same selector or projection that
  the matching page uses. A member who hides their basics from members is never found, and nothing is
  matched on a field the searcher is not allowed to read. Hits hidden from the searcher are dropped
  after the query, so each query fetches a few more rows than it returns.
- **Ranking.** People and startups use trigram word similarity (`pg_trgm`) on the name, with the
  headline or pitch weighted at 0.8, tolerate small typing mistakes, and sort by that score, then name.
  A minimum similarity of 0.45 keeps loose matches out; a plain substring match is also accepted.
  Jobs, events, news and courses match on title and text and sort by newest.
- **Groups and limits.** Results come back grouped, a handful per group, and the full page for a term
  pages within one group. A group a person cannot use is absent, not empty.
- **Administrators.** The console has its own groups (approvals, members, courses, jobs, events,
  support requests, ventures). A group appears only for a role that holds its permission
  (`permissions_for`), and its links go to the console screen already filtered to the term.
- **Recent terms.** The latest eight terms per person and per area (member or admin) are kept in
  `SearchRecent`, one row per term ignoring case, newest first, removable one at a time or all at once.
  A term is stored only when the person runs a search.
- **Highlight.** The interface marks the matched text. The server returns plain text only and never
  markup built from stored content.

## Consequences

- A new searchable kind has to say who may see it before it can be added; there is no shortcut that
  skips the page's own rules.
- Ranking is simple and explainable. It is not a relevance engine, and results for a long query rely
  on the matching field being short.
- Trigram search scans an index per field, so adding a field means adding an index in the same change.
