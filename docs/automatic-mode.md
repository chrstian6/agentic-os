# Automatic mode

The Agentic OS runs on every prompt without anyone invoking it.

## How

The installer registers five hooks in `.claude/settings.json`:

| Hook | Script | Effect |
|---|---|---|
| `UserPromptSubmit` | `hooks/user_prompt_submit.py` | classifies the prompt, routes the skills, injects the plan as context |
| `PreToolUse` | `hooks/pre_tool_use.py` | guards every Bash command and file write |
| `PostToolUse` | `hooks/post_tool_use.py` | appends an event log used by self-evaluation |
| `SessionStart` | `hooks/session_start.py` | injects verified installation state, queue counts, active policies |
| `Stop` | `hooks/stop.py` | turns the finished turn into a metrics row and learning observations |

Hooks are read when a session starts — **restart Claude Code after installing**.

## What gets injected

```
[Agentic OS] level 3/5, risk normal, workflow depth 3.
Workflow: UNDERSTAND -> SPECIFY -> PLAN -> RED -> GREEN -> REFACTOR -> VERIFY -> REVIEW -> ...
Delegate with the Task tool to: aos-analyst (BALANCED), aos-builder (BALANCED), ...

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
