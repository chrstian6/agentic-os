# Agentic OS

**An installable operating layer for Claude Code that plans, routes and guards every prompt.**

Install it into a project, or into your whole home directory. From then on, every prompt you
type is classified before Claude starts working: how hard it is, how risky it is, which
workflow it needs, which specialist agents should handle it, which model tier fits, and which
of 51 skills belong in context. Dangerous shell commands are intercepted on the way out. There
is nothing to call and nothing to remember: it runs from Claude Code's own hooks.

```text
you type ──► UserPromptSubmit hook ──► classify (difficulty 1–5, risk) ──► route skills + agents
                                                                            │
   Claude works with the plan in context ◄── inject plan ◄──────────────────┘
        │
        └─► every Bash command / file write ──► PreToolUse guard ──► ALLOW · CONFIRM · REVIEW_REQUIRED · BLOCK
```

- **Python 3.9+, standard library only.** No pip install, no third-party dependencies anywhere.
- **136 tests** covering the runtime, routing, queue, guard-bypass resistance, learning and the installer.
- **Reversible.** Ownership is tracked in a manifest. `uninstall` removes only what the installer put there, and backs up the files it merges into.

---

## Contents

- [Quick start](#quick-start)
- [What happens after you install](#what-happens-after-you-install)
- [What is in the box](#what-is-in-the-box)
- [The agents](#the-agents)
- [The skills](#the-skills)
- [Guards](#guards)
- [The `aos` command](#the-aos-command)
- [Installer commands](#installer-commands)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Development](#development)
- [License](#license)

---

## Quick start

**Requirements:** [Claude Code](https://claude.com/claude-code) and Python 3.9 or newer.

```bash
git clone https://github.com/chrstian6/agentic-os.git ~/agentic-os
```

### Option A: install into one project

```bash
cd /path/to/your-project
~/agentic-os/bin/agentic-os install
```

This writes the following:
- `.claude/agentic-os/`: runtime, skills, config, hooks and state
- the nine `.claude/agents/aos-*.md` subagents and the entry skill
- a marked block in the project's `CLAUDE.md`
- the hooks, in `.claude/settings.json`

### Option B: install globally (every project on your machine)

```bash
~/agentic-os/bin/agentic-os install --project ~
```

| Path | What |
|---|---|
| `~/.claude/agentic-os/` | runtime, 51 skills, config, hooks, state, and its own copy of the installer |
| `~/.claude/agents/aos-*.md` | 9 subagents |
| `~/.claude/skills/agentic-os/SKILL.md` | the entry skill |
| `~/.claude/CLAUDE.md` | a marked block appended (backup: `CLAUDE.md.aos-backup`) |
| `~/.claude/settings.json` | hooks merged in (backup: `settings.json.aos-backup`) |

Nothing else is touched. Your plugins, skills, agents, statusline, permissions and model
settings stay exactly as they are.

### Then

1. **Restart Claude Code.** Hooks are read at session start.
2. **Just work.** Every prompt is now classified and routed automatically.
3. **Check it any time** with `.claude/agentic-os/bin/agentic-os status`. For a global install, use `~/.claude/agentic-os/bin/agentic-os status`.

You can run the installer again safely. It discovers your stack (languages, frameworks,
package manager, and test, lint and build commands), deploys the distribution, wires the
hooks and initialises state. It finishes with `doctor`, which prints any health check that
failed.

---

## What happens after you install

A `UserPromptSubmit` hook classifies **every prompt** and adds the plan to Claude's context
before the turn starts. The plan covers:
- the difficulty level and the risk
- the workflow stages
- which agents to delegate to
- the model tier
- the full text of the routed skills

The depth of the plan scales with the task:

| You type | You get |
|---|---|
| "fix the typo in the nav label" | one line: level 1, do it directly, no ceremony |
| "add a graduation-year filter to the alumni list page" | level 2, builder + tester, frontend skills inlined |
| "redesign the pricing page" | level 3–4, several agents, design-taste + anti-ai-slop + redesign skills |
| "delete all users with no email in production mongo" | **risk critical**, a deeper workflow, an AUDIT stage, the safe-tool-use skill |

Dangerous commands are intercepted, no matter who typed them:

```text
rm -rf node_modules .next   → ask   (recursive force delete)
write to .env.local          → ask   (protected path)
git push --force             → ask   (force push rewrites remote history)
rm -rf /                     → deny
curl … | sh                  → deny
```

You can still plan by hand, for a sub-task or to re-plan in the middle of a turn:

```bash
.claude/agentic-os/bin/aos plan "add pagination to the users endpoint"
```

---

## What is in the box

| Layer | Where | What it does |
|---|---|---|
| Constitution | `payload/CLAUDE.block.md` | global invariants, merged into the project's `CLAUDE.md` |
| Agents | `payload/agents/*.md` | 9 native Claude Code subagents with real operating instructions |
| Skills | `payload/skills/**/SKILL.md` | 51 skills. Installed doesn't mean loaded: the router picks the minimum set per task |
| Runtime | `payload/runtime/*.py` | registry, router, classifier, model routing, queue, workflow, artifacts, guards, learning, metrics |
| Config | `payload/config/*.json` | classifier weights, risk factors, guard rules, model tiers, workflow depths, tool policy |
| Hooks | `payload/hooks/*.py` | UserPromptSubmit auto-plan, PreToolUse guard, PostToolUse log, Stop measurement, SessionStart context |
| Installer | `installer/installer.py` | manifest-based ownership: install, update, uninstall, doctor, status, drift |
| Tests | `tests/` | 136 tests: runtime, routing, queue, guard bypass, learning, installer, four ecosystem fixtures |

### The workflow

Work moves through stages chosen by difficulty and risk. A trivial task skips almost all of
them; a risky one gets all of them:

```text
UNDERSTAND → SPECIFY → PLAN → RED → GREEN → REFACTOR → VERIFY → REVIEW → REPAIR → REVERIFY → AUDIT → COMPLETE
```

Repair has a limit. If a fix fails again, the agent must change strategy rather than retry the
same fix. A task isn't complete until an audit maps each requirement to evidence.

---

## The agents

Delegate to them by name with Claude Code's Task tool. Each delegation gets one objective,
acceptance criteria and the routed skills. Agents hand back a structured result, not a
transcript.

| Agent | Role |
|---|---|
| `aos-router` | cheap first pass: classifies difficulty and risk, picks skills and model tier, decides whether delegating is worth its cost |
| `aos-orchestrator` | level 4–5 or high-risk work: decomposition, sequencing, delegation, holding the completion bar |
| `aos-analyst` | turns a vague request into a specification with acceptance criteria, affected files and explicit unknowns |
| `aos-researcher` | unblocks unknowns (an unfamiliar library, API semantics, version differences) with sourced findings |
| `aos-builder` | implements the change in the smallest correct diff, with the routed engineering skills loaded |
| `aos-design-critic` | reviews UI for taste, hierarchy and specificity, and catches interfaces that look templated |
| `aos-tester` | designs and runs the tests that would actually catch this change breaking |
| `aos-repairer` | takes a failing test or regression to its root cause, with a limited number of retries |
| `aos-reviewer` | adversarial final gate: correctness, requirement coverage, security, genuine completeness |

Agents exchange a typed, validated result (status, evidence, risks, remaining work) instead of
prose. A result that says `ok` while reporting failing tests or remaining work is rejected.

---

## The skills

There are 51 skills, grouped by the agent that uses them. Installing a skill doesn't load it.
The router scores the skills against each task and inlines only the minimum set needed, within
a character budget, so context stays small.

| Group | Skills |
|---|---|
| shared (8) | artifact-handoff, context-minimization, evidence, failure-recovery, safe-tool-use, uncertainty, unlazy, verification |
| analyst (3) | codebase-analysis, requirements-analysis, specification |
| researcher (4) | documentation-analysis, source-evaluation, technical-research, uncertainty-reduction |
| builder (13) | accessibility, anti-ai-slop, backend-engineering, component-architecture, design-taste, existing-project-redesign, frontend-engineering, frontend-testing, interaction-design, motion, performance, responsive-design, security |
| design-critic (1) | visual-critique |
| tester (9) | e2e-testing, edge-case-analysis, failure-analysis, integration-testing, regression-testing, test-design, test-driven-development, unit-testing, verification |
| repairer (5) | failure-analysis, regression-repair, root-cause-analysis, systematic-debugging, verification |
| reviewer (6) | adversarial-review, code-review, completion-audit, quality-review, requirements-review, security-review |
| orchestrator (2) | decomposition, delegation-economics |

Your project's own skills in `.claude/skills` are discovered too. To add your own, see
`docs/skills.md` and `docs/extending.md`.

```bash
aos skills list --agent builder              # what an agent may use
aos skills search database                   # find one by name or description
aos skills show frontend-engineering
aos route "add a date filter" --agent builder   # what the router would load for a task
```

---

## Guards

Every Bash command and every file write goes through the guard in the PreToolUse hook.

| Verdict | Effect |
|---|---|
| `ALLOW` | proceeds silently |
| `CONFIRM` | the user is asked, and shown the reason |
| `REVIEW_REQUIRED` | the user is asked; used for irreversible or outward-facing actions |
| `BLOCK` | denied |

**What it covers:**
- **Files and disks:** destructive filesystem operations, device writes, permission widening.
- **Git:** force push and history rewriting, hard reset and clean, remote branch deletion.
- **Databases:** `DROP`, `TRUNCATE` and unqualified `DELETE`, and database CLIs pointed at production.
- **Infrastructure:** deployments and cloud resource deletion.
- **Credentials and network:** reading or exfiltrating credentials, and piping network content into a shell.
- **System:** `sudo`, system configuration, package publishing, and destroying history to hide activity.

**Bypass resistance:**
- **Normalisation:** in-word quotes, backslash escapes and `${IFS}` are normalised away.
- **Splitting:** commands are split on `;` `|` `&&` `||` and newlines, and `$(...)` and backticks are inspected recursively.
- **Encoding:** base64 blobs are decoded and inspected again.
- **Verdict:** the strictest verdict across all fragments wins.
- **Tests:** the test suite tries eleven evasion techniques and requires each one to be caught.

Ordinary engineering is auto-approved via `config/tools.json`: read, search, edit, test, lint,
format, typecheck, build, git inspection, staging and committing. Agents don't ask for
permission on safe work.

To see what the guard would do before you run something:

```bash
aos guard 'git push --force origin main'
aos guard-path .env.local
```

---

## The `aos` command

It is installed at `.claude/agentic-os/bin/aos`, or `~/.claude/agentic-os/bin/aos` for a
global install.

```text
aos plan "<task>"                 full plan: classification, agents, models, skills
aos classify "<task>"             difficulty, risk and workflow depth only
aos route "<task>" --agent X      the skills that would be loaded
aos guard '<shell command>'       what the guards would do with a command
aos guard-path <path>             what the guards would do with a write
aos queue ...                     persistent task queue with dependencies
aos artifact write|read           structured handoff between agents
aos audit <task_id> --criteria    completion audit
aos learn ...                     observations, policies, champion/challenger
aos models                        model tier mapping and availability
aos skills list|search|show       browse the skill library
```

### The queue

The queue is a durable SQLite task list with dependencies, so work can be picked up again in
a later session:

```bash
aos queue add "Build the CSV serializer"
aos queue add "Test the CSV serializer" --depends-on 1
aos queue ready              # what may run right now
aos queue list
aos queue set 1 COMPLETED    # dependents are released automatically
```

When a task fails, the tasks that depend on it wait and everything unrelated keeps going. See
`docs/queue.md`.

### Learning

Every turn is measured at the Stop hook. Observations become candidate policies, which run as a
challenger against the current champion. A policy is promoted only after enough runs beat the
champion, and it can be rolled back. A safety floor rejects any policy that touches guards,
approvals, tests, privacy or destructive capability, both when it is proposed and again at
promotion. See `docs/learning.md`.

---

## Installer commands

Run these from the clone (`~/agentic-os/bin/agentic-os`) or from an installed copy
(`.claude/agentic-os/bin/agentic-os`).

```bash
agentic-os install                     # install or reinstall (safe to repeat)
agentic-os install --clean             # remove the old installation and its state first
agentic-os update                      # new version, keeping state and user-edited config
agentic-os uninstall                   # remove only what the installer owns
agentic-os doctor                      # verify the installation
agentic-os status                      # what is actually installed and running
agentic-os drift --projects ~/a ~/b    # which projects run an older version
agentic-os validate                    # check the distribution itself before shipping it
```

- `--project PATH` targets a directory other than the current one. Use `--project ~` for a global install.
- `--json` gives machine-readable output.

### Updating

```bash
cd ~/agentic-os && git pull
~/agentic-os/bin/agentic-os update --project /path/to/your-project
```

Your state and any config you edited survive the update.

---

## Configuration

Everything you can tune lives in `.claude/agentic-os/config/`, and your edits survive
updates.

| File | Controls |
|---|---|
| `auto.json` | the automatic prompt-time plan: `enabled`, `quiet_below_level`, `inline_skill_budget_chars` |
| `classifier.json` | difficulty signals and their weights |
| `risk.json` | risk factors and the workflow floors they force |
| `router.json` | skill scoring and the per-level skill budget |
| `workflow.json` | which stages each depth runs |
| `models.json` | model tiers per agent and level |
| `guards.json` | guard rules and protected paths |
| `tools.json` | auto-approved tools and command families |
| `memory.json` | memory and vault settings |

To turn off the automatic plan without uninstalling, set `"enabled": false` in `auto.json`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| No `[Agentic OS]` block appears on prompts | Restart Claude Code (hooks load at session start), then run `agentic-os doctor`. |
| `doctor` reports a failed check | Run `agentic-os install` again; it is safe to repeat. Add `--clean` if the state is corrupted. |
| A guard blocks something you really meant | Run it yourself in your terminal. Agents are told never to route around a guard. |
| The plan is too heavy for small tasks | Raise `quiet_below_level` in `config/auto.json`, or tune `classifier.json`. |
| An older version is still running in some project | Run `agentic-os drift --projects ~/proj-a ~/proj-b`, then `update` those projects. |

More in `docs/troubleshooting.md`.

---

## Limitations

These are stated plainly, because claiming capabilities that don't exist is the failure this
system is built to prevent:

- **No background execution.** Claude Code has no persistent worker. The queue makes work resumable, but an agent in a session does the work.
- **The runtime plans and records; the model reasons.** The classifiers and router produce decisions and context. Claude Code's Task tool runs the agents.
- **Classification is heuristic.** It works from phrase signals, not understanding, and it is deliberately conservative: risk floors only escalate.
- **Guards are pattern-based.** They are a safety net for an agent's mistakes, not a sandbox against a determined adversary.
- **Learning needs volume** before any policy is promoted.

The full list is in `docs/limitations.md`.

---

## Development

```bash
python3 tests/run.py            # all 136 tests
python3 tests/run.py guards     # one file
bin/agentic-os validate         # check the distribution before shipping
```

**Docs:** `docs/installation.md` · `docs/automatic-mode.md` · `docs/agents.md` ·
`docs/skills.md` · `docs/routing.md` · `docs/queue.md` · `docs/guards.md` ·
`docs/learning.md` · `docs/extending.md` · `docs/troubleshooting.md` · `docs/limitations.md`

## License

[MIT](LICENSE) © Hans Esgrina

If Agentic OS saves you from a `git push --force` or a bloated context window, a ⭐ helps other
people find it.
