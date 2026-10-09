# 0001. Outbox and dead letter tables live in `core`

Status: accepted (Stage 0)

## Context

The design lists the outbox publisher under `notifications`, a level 3 module. Every module,
including level 0 and 1 ones, must write outbox events, and a module may only depend on lower
levels.

## Decision

`OutboxEvent`, `FailedTask`, the enqueue/dispatch functions and the handler registry live in
`apps.core`. Handlers register Celery task names by topic, so `core` never imports the modules that
consume events. `notifications` registers its own handlers in later stages.

## Consequences

Any module can publish events without breaking the dependency rules. Handlers are looked up by
task name, so a typo shows up at dispatch time; each stage that adds a topic should add a test asserting its handler is registered.
