# 0017. Onboarding checklist, notification preferences and member search

Status: accepted (Stage 1)

## Decisions

- **A new `memberarea` module** holds features that combine several modules for a signed-in member.
  It sits beside `directory` in the layer order, above profiles, startups and notifications, so it
  may read all of them and none of them may read it.
- **The checklist is calculated, not stored.** `GET /me/onboarding` looks at the member's real data:
  profile score of 80 or more, at least one startup (owned or on the team), at least one traction
  figure, and notification preferences saved. Nothing can drift out of step with the data. Only the
  moment of completion is remembered (`OnboardingState`), so `onboarding_completed` is recorded
  exactly once, with the hours taken, even if several requests notice it together. The event is
  recorded when the member next opens the checklist after the last step.
- **Notification preferences** (`GET/PUT /me/notification-preferences`) are a matrix of type
  (comments, mentions, mentorship, approvals, event reminders, newsletter) by channel (email, in
  app). Only departures from the defaults are stored, so adding a type later changes nothing for
  anyone. The newsletter starts off. Approval emails cannot be switched off. Saving, even with no
  changes, marks the preferences as set, which ticks the checklist. Senders ask
  `preferences.allows(user, type, channel)`; no sender uses it yet because those messages arrive
  with their modules.
- **Search** (`GET /search?q=&types=&limit=`) covers members and startups now and is built as a
  registry, so jobs, courses, posts, mentors and events register themselves as they are built. It
  matches only on the `basics` group of each item and then projects every hit exactly as the profile
  or startup page would, so a hidden item is absent and no hidden field can be probed by searching
  for it. Only active members' items appear, which also takes suspended and removed people out
  immediately. Typos are tolerated with trigram word similarity. Results are `private, no-store`,
  limited to 20 per type, and rate limited to 60 a minute.

## Consequences

Search is a database query per type, fine at this size. When the member base grows or more types
join, a dedicated index (a search table or a search service) can replace the registry entries
without changing the endpoint. The personalised member home summary needs jobs, events, mentors and
courses and arrives with them.
