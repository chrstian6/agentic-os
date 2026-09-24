# Agents

Nine native Claude Code subagents, installed as `.claude/agents/aos-*.md`. Delegate with the
Task tool using the agent name.

| Agent | Tier | Use for |
|---|---|---|
| `aos-orchestrator` | DEEP | level 4-5 or high-risk work spanning several agents |
| `aos-analyst` | BALANCED | turning a request into a spec with acceptance criteria |
| `aos-researcher` | BALANCED | unknowns: library behaviour, version differences, API semantics |
| `aos-builder` | BALANCED | the implementation itself, frontend or backend |
| `aos-design-critic` | BALANCED | UI that works but looks templated |
| `aos-tester` | BALANCED | test design and execution, real output |
| `aos-repairer` | BALANCED | a failing test or regression that survived the first fix |
| `aos-reviewer` | DEEP | adversarial final gate: correctness, coverage, security, completion |
| `aos-router` | FAST | cheap classification and delegation decision |

Every agent definition contains role, mission, method, boundaries, decision rules, an output
contract, failure behaviour, escalation rules, and its skill domains. They do not carry the
skill content — the router loads that per task.

## Output contract

All agents return the same structured artifact:

```json
{"status": "ok|partial|failed|blocked|needs_review", "summary": "...",
 "files_changed": [], "tests_run": 0, "tests_passed": 0, "tests_failed": 0,
 "evidence": [], "risks": [], "remaining_work": [], "uncertainties": [],
 "next_action": null}
```

The runtime validates it: `status: ok` with failing tests or non-empty `remaining_work` is
rejected. Write with `aos artifact write <task> <agent> --json '...'`, read the previous
stage with `aos artifact read <task>`.

## Delegation

The existence of nine agents does not mean nine agents run. `aos plan` decides:

| Level | Shape |
|---|---|
| 1 | direct, no delegation |
| 2 | builder (+ tester if behaviour changed) |
| 3 | analyst → builder → tester → reviewer |
| 4-5 | orchestrator over the full workflow, researcher for unknowns, review passes |

Risk raises the shape; it never lowers it.

## Adding an agent

Add `payload/agents/aos-<name>.md` with `name`, `description` and `model` frontmatter, add
the agent to `payload/config/workflow.json` under `agents_by_depth` and
`payload/config/models.json` under `agent_preferred_tier`, and list it in the `agents:`
field of the skills it should be able to load. Then `agentic-os validate`.

**Write the bare role in the configs, not the `aos-` filename.** Every config keyed on an
agent — `agents_by_depth`, `agent_preferred_tier`, a skill's `agent:` frontmatter — uses the
bare role as its lookup key. The `aos-` prefix is added once, at the presentation boundary,
by `runtime/classify.py`'s `dispatch_name()`.

Both spellings are load bearing, so neither is redundant: the bare role is the key, and the
prefixed name is the only thing a `Task` call accepts — a host guard that reads
`.claude/agents/` refuses anything with no definition there. `aos plan` reports both, as
`stages[].agent` and `stages[].dispatch`; `aos classify` reports `agents` and `dispatch`.
Script against `dispatch`.

They drifted once: the hook prefixed `aos-` inline while `aos plan` emitted the bare role, so
the JSON named agents that do not exist on disk. `tests/test_workflow.py` now pins it.
