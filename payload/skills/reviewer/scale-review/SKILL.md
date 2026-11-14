---
name: reviewer/scale-review
description: Review a change for what breaks under many concurrent users - per-viewer load, work inside locks, fan-out, connection use, and limits that only show at volume.
agents: [reviewer]
domains: [review, performance, scale]
triggers: [scale, scaling, concurrency, concurrent users, load, performance, realtime, polling, lock, hot path, throughput, capacity, fan-out]
dependencies: [reviewer/code-review]
conflicts: []
priority: 9
version: 1.0.0
---

# Scale review

Correctness review asks "is the answer right?". This asks "is it still right, fast and
affordable when 1,000 people do it at once?". Code that passes every test can still take
production down, because the damage is in the multiplication, not the line.

## Scope trigger

Do a full pass whenever the diff touches any hot path:

- anything that runs **per viewer or per tab**: polling, `setInterval`, `router.refresh()`,
  revalidation, subscriptions, refetch-on-event, session/token refresh, middleware/proxy
- anything that runs **per write on a hot row**: bid/order/booking paths, triggers,
  counters, lock-holding functions, outbox/notification inserts
- **fan-out**: broadcasts, notifications, emails, "notify every other participant"
- **schema**: new indexes on hot tables, new triggers, migrations that lock tables
- **background jobs**: queue loops, schedulers, batch closers, sweeps
- **capacity config**: pool sizes, timeouts, rate limits, compute or plan caps

If none apply, write "scale: not on a hot path" and move on.

## The checklist

**1. Do the multiplication.** For every new or changed call, write the formula and
evaluate it at 1,000 concurrent users (and at the project's stated peak if one exists):

- calls/sec = viewers ÷ interval (a 5 s poll × 1,000 viewers = 200 req/s idle)
- per event = subscribers × work-per-message (1 bid → N refetches is a thundering herd)
- per write = DB statements, index updates and trigger runs inside the transaction

State the number in the finding. "Could be slow" is not a finding; "≈200 req/s per hot
lot before any bid" is.

**2. Push should replace pull, not add to it.** If a realtime message arrives, does the
client use its payload, or does every receiver call the server back? Does polling slow
down while the push channel is healthy? Refetch-on-every-event is blocking at scale.

**3. Work inside the lock.** For any `FOR UPDATE`, advisory lock or serializable
transaction: list everything that runs before the lock is released (reads, triggers,
inserts, fan-out loops). Anything that does not need the lock moves before it or after
commit. Cost that grows with participant count inside a lock is blocking.

**4. Waiting holds resources.** A lock or queue wait holds a DB connection the whole
time. `lock_timeout` × concurrent waiters must fit inside the pool and the compute's
connection limit, or one hot item starves everyone else.

**5. Hot-row writes and indexes.** Each extra UPDATE of a hot row, and each index on a
column that changes per write, multiplies write cost (non-HOT updates touch every index).
New index on a hot table: is it needed, is an existing one redundant, is it built
`CONCURRENTLY`?

**6. Limits keyed wrongly.** Per-IP rate limits break many users behind one NAT, venue
Wi-Fi or mobile carrier. Signed-in traffic should be limited per user. A limit that
fails silently (error swallowed, stale UI) is worse than one that fails visibly.

**7. Synchronized stampedes.** Events everyone sees at the same moment (item closes,
deploy, reconnect after an outage, top of the minute cron) must not make every client
reload at once. Look for missing jitter, full-page refreshes, and reconnect storms.

**8. Serial background work.** Loops that process items one at a time, a single global
lock, an unbounded scan with no LIMIT, or one queue blocked behind another. Ask: what
happens when 500 items are due in the same minute?

**9. Unbounded growth.** New tables or rows written per event with no retention, purge
or partitioning plan.

**10. Platform limits.** Realtime connection/message caps, DB compute and connection
caps, email provider send rate, serverless concurrency. If the change pushes against a
plan limit, say which one and that it needs checking in the dashboard.

## Findings bar (scale)

A scale finding replaces "given input X, returns Y" with a **load scenario**:
"with N users doing A, this causes B (show the arithmetic), expected C". If you cannot
produce the arithmetic, drop it.

Severity:

- **blocking**: cost per request or per lock grows with the number of users or
  participants on a hot path; a silent failure under load (frozen UI, lost write);
  a table-locking migration on a hot table
- **major**: a fixed but large multiplier on a hot path (e.g. a full page render per
  viewer per event); serial processing of work that arrives in bursts
- **minor**: redundant index, missing retention, a limit that is fine today but has no
  documented trigger for revisiting

## Deferred is fine, forgotten is not

If the team deliberately accepts a scale cost for now, that is a valid decision — but the
change must record the trigger that reopens it (e.g. "revisit when a lot exceeds 50
concurrent viewers") in the task tracker. A known scale cost with no recorded trigger is
a minor finding.

## Do not

- Do not demand premature optimization off the hot path. Admin pages used by five
  people are not a scale finding.
- Do not guess load numbers you cannot ground; use the project's stated peak, or
  1,000 concurrent users as the default and say so.
- Do not accept "it passed the load test" unless the load test exercises the same layer
  (a DB-only bench says nothing about per-viewer HTTP polling).
