---
name: shared/evidence
description: Ground every claim in something observable. Distinguishes what was run from what was assumed.
agents: [orchestrator, analyst, researcher, builder, design-critic, tester, repairer, reviewer]
domains: [quality, verification]
triggers: [evidence, verify, prove, confirm, claim]
dependencies: []
conflicts: []
priority: 9
version: 1.0.0
---

# Evidence

## What it is

A discipline for separating three things that agents routinely blur: what you observed,
what you inferred, and what you assumed.

## When it applies

Every report, every status claim, every "done". Always loaded.

## When it does not apply

Never unloaded, but it does not mean "run a command for every sentence". Reading a file
is evidence of what the code *says* - structure, callers, a config value. It is never
evidence of what the code *does*. Re-running the suite to confirm a comment is waste.

## How to use it

Label every claim you make in a report as one of:

- **Observed** — you ran it or read it. Cite the command and its output, or `path:line`.
- **Inferred** — it follows from something observed. State the observation it follows from.
- **Assumed** — you have not checked. Say so, and say what checking would cost.

**Proof, not codebase.** A claim about behaviour - it works, it is fixed, it renders, it
returns X, it is faster - needs a *run*: a test, a build, a script, an HTTP request, a DB
query, a screenshot or DOM assertion. Reading the diff and reasoning that it must work is
Inferred at best. The Stop/SubagentStop proof gate sends you back when you edit code and
run nothing after it, or claim success with nothing run.

Rules:

1. Never write "tests pass" without the command and its counts in the same report.
2. Never write "this function is only called here" without the grep that shows it.
3. Quote real output. Paraphrased output hides the detail that mattered.
4. When you correct yourself, state the new fact plainly; do not narrate the mistake.
5. A subagent's report is a claim, not a fact. Spot-check the load-bearing parts.
6. A check that cannot fail proves nothing. Prefer one you have seen fail (run it red
   first, or break the change and watch it go red).
7. If nothing can be run (no runtime, no credentials), say so and mark the claim
   unverified. Never upgrade it to Observed.

## Common mistakes

- "I've verified the fix works" after reading the diff, not running it.
- Reporting a test count from an earlier run after changing the code.
- Citing a file you did not open, from memory of a similar project.
- Treating the absence of an error message as proof of success.

## Verification

Before submitting a report, scan it for unhedged claims and ask for each: what did I run?
If the answer is nothing, downgrade the claim or go run something.

## Example

Bad: "Fixed the race condition; everything works now."
Good: "Observed: `pytest -q tests/test_pool.py` → 12 passed (was 11 passed, 1 failed).
Inferred: the lock now covers the check-then-act in `pool.py:88`. Assumed: no other
caller mutates `_slots` outside the lock — grep shows two callers, both inside it."

## Dependencies and conflicts

Pairs with shared/verification (which checks the *system*) and shared/uncertainty (which
handles what evidence cannot reach). No conflicts.
