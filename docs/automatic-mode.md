# Automatic mode

The Agentic OS runs on every prompt without anyone invoking it.

## How

The installer registers seven hooks in `.claude/settings.json`:

| Hook | Script | Effect |
|---|---|---|
| `UserPromptSubmit` | `hooks/user_prompt_submit.py` | classifies the prompt, routes the skills, injects the plan as context |
| `PreToolUse` | `hooks/pre_tool_use.py` | guards every Bash command and file write |
| `PostToolUse` | `hooks/post_tool_use.py` | appends an event log used by self-evaluation |
| `SessionStart` | `hooks/session_start.py` | injects verified installation state, queue counts, active policies |
| `Stop` | `hooks/stop.py` | proof gate (below), then turns the finished turn into a metrics row and learning observations |
| `SubagentStop` | `hooks/stop.py` | proof gate for each subagent, judged on that subagent's own tool calls |
| `PreCompact` | `hooks/pre_compact.py` | tells the compaction summary to keep the request, proof, and unproven claims |

`SessionStart` with `source: compact` re-injects the turn in progress from disk and clears the
session's sent-skills record, so the next prompt re-sends skill text that compaction dropped.
Turn state is per session (`state/turns/<session_id>.json`): concurrent sessions no longer
overwrite each other's plan or count each other's tool calls.

## Proof gate

Reading code shows what the code says, not what it does. At `Stop` and `SubagentStop` the
agent is sent back once (never in a loop: `stop_hook_active` is honoured) when:

- a code file was edited and no command ran after the last edit, or
- the final message claims success ("tests pass", "verified", "it works") and nothing ran.

Docs-only edits (`.md`, `.txt`, `.rst`) are exempt. Set `proof_gate: "off"` in
`config/auto.json` to disable. Ceiling: any command counts as a run - the gate forces a run,
the reviewer judges whether it proved anything.

Hooks are read when a session starts — **restart Claude Code after installing**.

## What gets injected

```
[Agentic OS] level 3/5, risk normal, workflow depth 3.
Workflow: UNDERSTAND -> SPECIFY -> PLAN -> RED -> GREEN -> REFACTOR -> VERIFY -> REVIEW -> ...
DISPATCH in phases: 1) specify: aos-analyst (model=sonnet); 2) build: aos-builder (model=opus) ...

Skills routed for this task (3 loaded, the rest of the library stays out of context):
<skill name="builder/design-taste"> ...full skill text... </skill>
<skill name="builder/anti-ai-slop"> ... </skill>
...
Guards run automatically on every command and write. Before reporting done, run the
completion audit.
```

Trivial prompts get one line instead, so a rename does not drag in the skill library:

```
[Agentic OS] level 1/5, risk normal, workflow depth 1. Trivial: do it directly, no
delegation, no ceremony. Still: evidence for any claim, and finish the whole request.
```

Measured on the shipped configuration: rename → 168 characters; endpoint + tests → ~8k;
landing-page redesign → ~15k; production payment change → level 5, risk critical, security
and review skills loaded.

## Configuration

`.claude/agentic-os/config/auto.json`:

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | set `false` to go back to calling `aos plan` by hand |
| `min_prompt_chars` | `12` | shorter prompts are ignored |
| `skip_prefixes` | `["/", "!", "#"]` | slash commands and shell passthrough are ignored |
| `quiet_below_level` | `2` | below this level (and normal risk) only the one-line note is injected |
| `inline_skill_budget_chars` | `14000` | cap on inlined skill text; the rest are listed as paths |
| `max_inlined_skills` | `5` | how many skills may be inlined |

## Failure behaviour

The hook fails open and silent: malformed input, a missing runtime, or any exception exits 0
with no output rather than blocking your prompt. That means a broken installation removes the
automation quietly — `agentic-os doctor` is the check for it.

## Verifying it

```bash
echo '{"prompt":"redesign the pricing page"}' | \
  python3 .claude/agentic-os/hooks/user_prompt_submit.py | head -c 400
```
