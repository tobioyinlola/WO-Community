# 0044. The venture partner, change sets, weekly next steps and mentor access

Status: accepted (toolkit stage T4, partner)

## Decisions

- **Grounded, not general.** A reply is made from one venture's own data: the profile, the latest
  score gaps, the forecast headline, plan progress, the decision log and the last ten turns. Data
  goes to the model as delimited blocks, never as instructions, and no other venture or member's
  content is in the context. The model is told what it may not do, and code enforces it as well.
- **Declines happen in code.** Messages asking for legal, tax or investment advice, or for made up
  proof, get a fixed decline and a pointer to the right kind of professional without any model call
  (`ai/safety.py`). A reply that quotes an instruction block is replaced, and figures that appear in
  neither the venture data nor the founder's words are removed from the reply.
- **Replies are quick or a job.** The message is stored and a `partner.reply` job queued. The
  request waits up to `AI_PARTNER_REPLY_TIMEOUT_SECONDS` for it; if it is done the reply is
  returned (201), otherwise the job is returned (202) and the reply appears in the conversation.
  The same `Idempotency-Key` returns the same job, and a retried job does not answer twice.
- **Change sets, not edits.** The partner may propose profile changes. Each is validated against
  the profile schema, must differ from now, and is stored as a change set with the before and after
  values. Nothing is written until the founder applies it (all, or chosen fields); applied fields
  are recorded as accepted suggestions and mark dependent outputs out of date. Undo restores the
  previous values and leaves alone any field the founder has edited since.
- **A decision log** the founder keeps (500 entries) and the partner reads, so it stops
  suggesting what was ruled out.
- **Weekly next steps are rules, not a model.** Once a week (Monday 07:30 UTC) each active,
  recently used venture whose owner has not switched nudges off gets at most one step, chosen in a
  fixed order: complete required fields, run the score, start the forecast, write the plan, then the
  score's top action. One per venture per week is a database constraint, so the task is safe to
  run twice.
- **Mentor suggestions are ranked from the venture's weakest score areas** and topics the partner
  raised, against listed mentors' expertise and industries. Nobody is contacted.
- **Mentor access is a named, read only grant.** An owner can open a venture to a listed mentor,
  optionally for a number of days, and revoke at once. The mentor uses the same read endpoints and
  every write answers 404. Grants and revocations are audited. `can_comment` is stored but no
  comment feature exists yet.
