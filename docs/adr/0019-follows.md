# 0019. Follows and the Following feed

Status: accepted (Stage 2)

## Decisions

- **One `Follow` table** with a type (`member` or `startup`) and the target's id, unique per
  follower, type and target, as in the design. The target is not a foreign key because it points at
  two different tables; the service checks it instead.
- **What can be followed.** An active member other than yourself whose profile basics you can see, or
  a startup whose basics you can see and whose owner is active. Anything else is a 404, which does
  not reveal whether the person exists but hides from you. A member may follow up to 500 targets.
- **Following is private.** Nobody is told who follows them and there are no follower lists or
  counts. These can be added later without changing the data.
- **A follow outlives its target's visibility but does nothing.** If the target is suspended, removed
  or hides their basics, the follow stays on record but their posts leave the Following feed and they
  drop off `GET /me/following`; they come back if they become visible again.
- **The Following feed** is the ordinary feed with `scope=following`: posts whose author is a
  followed member, or which were made for a followed startup (whoever on the team wrote them). It
  has the same filters, sorting, cursors and visibility rules as the shared feed, and has no pinned
  list.
- **`following` flag** on author and startup cards in posts and comments, so a client can show a
  Follow or Following button without a second request.
- **Member cards** now distinguish "profile hidden from you" from "no profile filled in yet": only
  the first blocks following and shows an anonymous author.

## Consequences

Notifying someone when they gain a follower, and suggestions of whom to follow, are not built.
Following feeds are a query, not a stored timeline; at the planned scale that is fast enough, and a
stored fan-out can replace it behind the same endpoint if it is not.
