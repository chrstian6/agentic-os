# Self-evaluation and learning

## Memory tiers

| Tier | Where |
|---|---|
| WORKING | the queue's in-flight task rows |
| EPISODIC | `observations` — what happened, per task |
| SEMANTIC | `patterns` — recurring generalisations with counts |
| POLICY | `policies` — versioned behaviour that actually changes decisions |

## Metrics

`state/metrics.db` records per run: success, first-pass success, repairs, tests run/failed,
review rejections, regressions, latency, tokens, agents used, skills loaded, delegation
overhead. `aos metrics` aggregates by arm.

## It runs itself

You do not have to record anything by hand. Two hooks close the loop:

- `UserPromptSubmit` writes `state/current_turn.json` — the level, risk, depth, routed
  skills, and which experiment **arm** this turn runs (challenger sampling is 50/50 whenever
  a candidate policy is pending).
- `Stop` reads that file plus the turn's tool events and writes **one metrics row** and any
  observations the evidence supports: `underclassified` (level 1 that edited four files),
  `missing_skill` (backend files touched, no backend skill routed), `unused_skill`,
  `repair_loop` (three or more failed tool calls), `no_verification` (files changed, no test
  run). Only measurable facts — `success` is the explicit proxy "no tool call errored".

Then one command decides:

```bash
aos learn cycle              # mine -> propose -> compare -> promote/reject
aos learn cycle --dry-run    # same, without promoting
```

It reports what it proposed, what the safety floor rejected, what was promoted or rejected,
and what is still waiting for runs. Run it whenever you want; it is idempotent.

## The loop, by hand

```bash
aos learn observe 12 missing_skill "css|builder/design-taste"
aos learn hypothesize            # patterns above threshold -> candidate policies
aos learn propose --json '{"kind":"skill_boost","key":"builder/design-taste",
                           "scope":"css","value":4.0,"reason":"..."}'
aos learn record-metric 12 --json '{"arm":"challenger","policy_id":3,"success":1.0}'
aos learn compare 3              # champion vs challenger
aos learn promote 3              # only if the comparison says promote
aos learn rollback 3             # reverse it, restoring the previous champion
aos learn active | challengers | history
```

Promotion requires at least three challenger runs, a champion baseline, better quality, and
cost within 20% — otherwise the decision is `reject` or `insufficient_evidence`.

## What learning can change

`skill_boost`, `skill_suppress`, `level_bump`, `depth_floor`, `tier_pref`. A promoted policy
immediately changes what `aos route`, `aos classify` and `aos plan` return — this is
verified by a test that routes the same task before and after promotion and asserts the
skill set differs, then rolls back and asserts it reverts.

## What learning can never change

The safety floor (`runtime/policy.py`) rejects any candidate that touches guards, approvals,
required tests, failure visibility, privacy, credentials, or destructive capability — and
re-checks at promotion time, so tampering with a stored policy still fails. Safety-relevant
skills cannot be suppressed. `depth_floor` cannot go below 1 and `level_bump` cannot be
negative: learning may raise scrutiny, never lower it.

## Rollback record

Every policy row stores kind, key, scope, value, status, version, reason, evidence, source
task, its predecessor, and both timestamps. Nothing is irreversible.
