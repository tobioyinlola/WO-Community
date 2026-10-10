# 0020. Reports and the moderation queue

Status: accepted (Stage 2)

## Decisions

- **Who can report what.** Any active member can report a post or comment they can see, other than
  their own. Hidden, removed or invisible content answers 404, so a report cannot be used to probe
  for it. One report per member per item (a repeat returns the existing report), at most 20 reports
  a day. Details are stored as plain text.
- **Statuses** are Open, Reviewed and Actioned, as specified. *Reviewed* means a moderator looked
  and no action was needed; it applies to that one report. *Actioned* means the content was hidden
  or removed; it closes every report about the same item that is not already actioned, so the same
  complaint is never handled twice. An actioned report cannot be reviewed again (409).
- **Acting through a report** requires `reports.handle` and applies `hide` or `remove` using the
  same code and audit entries as direct moderation, plus a `feed.report_actioned` entry. If the item
  was already removed by someone else, the reports are still closed.
- **The queue** is oldest first so the longest wait is handled first, with offset paging because an
  admin queue is bounded. Each entry shows the reason, details, reporter, a 200 character excerpt
  of the content, whether it is currently visible, hidden or removed, its author, and how many open
  reports the item has. The entry reads the content from the database rather than a stored copy, so
  an item edited after being reported shows its current text.
- **Counts.** `GET /admin/queues` now includes `open_reports`.
- **Comments can be moderated directly** (`feed.moderate`): hide, unhide, remove. Hiding or removing
  a comment hides its replies as well, because replies are only shown under their parent. The post's
  comment count is recalculated from the comments readers can actually see, rather than adjusted by
  arithmetic, so hide, unhide and remove always leave it exact.
- **Reporters are not told the outcome yet.** That arrives with the notification centre. Reporter
  identity is visible to moderators only.

## Consequences

Repeat offenders, automatic hiding after several reports, and appeals are not built. The queue is
by report; grouping by item is possible later from the target columns without a data change.
