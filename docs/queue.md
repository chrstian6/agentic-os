# Task queue

SQLite at `.claude/agentic-os/state/queue.db`. Tasks survive context loss, session end, and
restarts.

```bash
aos queue add "Build the CSV serializer"
aos queue add "Test the CSV serializer" --depends-on 1
aos queue ready              # what may run right now
aos queue list [STATUS]
aos queue get 1
aos queue set 1 COMPLETED
aos queue stats
```

`add` classifies the task automatically and stores the depth, risk and full classification.

## Statuses

`QUEUED · CLASSIFYING · PLANNED · READY · RUNNING · TESTING · REPAIRING · REVIEWING ·
FINAL_VALIDATION · COMPLETED · PARTIAL · WAITING_DEPENDENCY · WAITING_APPROVAL · BLOCKED ·
PAUSED · FAILED · ESCALATED · CANCELLED`

## Dependencies

Explicit via `--depends-on`, and inferred: a task titled "test X" automatically waits on an
open "build X" that shares significant words. Check with `aos queue ready` — never assume.

## Failure isolation

When a task fails, its dependents move to `WAITING_DEPENDENCY` and everything unrelated keeps
running. Completing a task automatically releases the dependents it was blocking.

## Execution model — an honest note

The queue is state, not a scheduler. Claude Code has no persistent background worker, so the
Agentic OS does not claim one: tasks are executed by agents in a session, and the queue is
what makes that resumable across sessions. `aos queue ready` tells the next session exactly
where to pick up.
