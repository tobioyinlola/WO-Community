# 0010. Profiles, startups and field visibility

Status: accepted (Stage 1)

## Decisions

- **One visibility rule, in `core`.** Every field group has a level (`private`, `members`,
  `public`). The viewer is the owner, a member, or the public. `core/visibility.py` decides, and the
  profile and startup selectors call it before anything is serialised, so there is no endpoint that
  can forget it. Pending accounts count as the public: they are not members yet.
- **Hidden means absent.** A group the viewer may not see is left out of the response, not blanked.
  If the viewer cannot see the *basics* group, the profile or startup answers 404 as if it did not
  exist. Serializers declare hidden-capable fields as optional so an omitted key is never filled in.
- **Field groups.** Founder profile: basics (name, headline), bio, location, skills, links,
  open_to. Startup: basics (name, pitch, sector, stage, location, year), description, website,
  team. Each traction entry carries its own level. Defaults: members see the essentials; personal
  links and traction start private.
- **Stored as JSON, not a table.** The requirements sketch a `VisibilitySetting` table. Each
  profile and startup instead keeps a `visibility` JSON object holding only the groups the member
  changed; the rest use code defaults. One row per owner is atomic with the record it governs and
  needs no join. Unknown groups and levels are rejected on write and ignored on read.
- **Directory opt-in.** `directory_opt_in` (owner only) makes the startup's basics public, and while
  listed they cannot be hidden (409 `listed_in_directory`). The public directory itself, its read
  model and search come in the next slice.
- **Registration details.** The profile and startup typed at registration travel in a
  `SignupDetailsSubmitted` event; `profiles` and `startups` consume it (idempotently) to create
  their rows. `accounts` therefore never depends on them. The event holds names and cities, so a
  daily job deletes published outbox events older than 14 days.
- **Reference data in its own level-0 module** (`reference`): sectors, stages and skills are
  seeded by migration and served from public, cacheable endpoints; countries are the ISO 3166-1
  list in code. Registration can validate against them without importing higher modules.
- **Concurrent edits.** Profiles and startups return an ETag. Updates need it in `If-Match`: 428 if
  absent, 412 if stale. Two simultaneous edits from one version cannot both succeed.
- **Teams.** The owner adds people by email. The response is identical whether or not the address
  belongs to a member, and the owner's team list shows addresses as typed with no account status.
  Someone who is not an active member yet is attached automatically when approved. Founders on the
  team can edit; every team member reads the startup as its owner; members may remove themselves;
  the owner cannot be removed. Outsiders get 404 on write attempts, so existence is not revealed.
- **Plain text only.** Names, pitches, descriptions, bios and milestones have markup stripped on
  write; links must be https, on a real hostname, and on the right domain for LinkedIn and X.
  Clients must still escape text when rendering.
- **Ranges, not figures.** Revenue and funding are bands, so members can share them without
  exposing accounts.

## Consequences

Photos and logos are not part of this slice: they need the upload pipeline (pre-signed URLs,
malware scan), so the model holds a `photo_key` and `logo_key` that no API writes yet. A startup
can currently have a single owner; transfer of ownership is not provided. Team members cannot decline
being added, only leave afterwards.
