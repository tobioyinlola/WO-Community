# 0034. Paid course video stays on YouTube, behind the application lock

Status: accepted (Stage 3 close; revisit if paid video becomes a revenue line of its own)

## Question

ADR 0028 left one decision for before paid courses launch (Stage 4): is an embedded YouTube video
plus the application's own access lock enough for paid lessons, or must paid video move to a host
that protects the stream (signed, expiring addresses, domain-restricted playback, DRM)?

## Decision

Paid lessons keep using YouTube embeds, with the application lock in front of them. Paid videos
are uploaded to YouTube as **unlisted**.

## Why

- **What the lock does.** The lesson endpoint answers 403 without an enrolment or purchase, and
  neither the course outline nor any list includes video ids, so the address of a paid video is
  never in an API response a non-buyer can obtain. Nobody can find the video by browsing the
  platform or by searching YouTube (unlisted videos are not searchable or suggested).
- **What it does not do.** A buyer can copy the video address and share it, and anyone holding an
  unlisted address can watch. YouTube offers no signed or expiring links. This is the same
  exposure as sharing a login, a course PDF or a screen recording, and none of those are prevented
  by a protected host either (a determined buyer can still record the screen).
- **Cost against benefit.** A protected host (Mux, Vimeo, Bunny Stream and similar) adds a
  monthly bill that grows with viewing, an upload and transcoding workflow for authors, another
  adapter and another set of failure modes, for protection that stops casual sharing but not
  recording. YouTube is free, handles bandwidth and devices, is already validated in the lesson
  authoring (ADR 0028), and needs no new infrastructure.
- **Choice not foreclosed.** `Lesson.video_provider` is stored, and the player contract returns
  the provider with the id and an embed address, so a second provider is a new value and a new
  adapter, not a data migration. A course can move over lesson by lesson.

## Conditions that would reopen it

Any of: paid video becomes a large share of revenue; a course is licensed to us on terms that
require protected delivery; leaked addresses appear in practice (watch for links to paid lesson
videos in support requests or reports); or authors ask for downloads disabled, watermarking or
per-viewer analytics. Document files in paid courses (ADR 0033) are in the same position: short
lived signed links and an enrolment check, no more.

## Consequences

Authors of paid courses must set videos to unlisted (not private, which cannot be embedded for
members, and not public, which makes the video searchable). The authoring screen and the course
author guide should say so; the backend cannot check it.
