# Extending

Everything below is data or a small module; none of it requires touching the rest of the OS.

**New skill** — `skills/<agent>/<name>/SKILL.md` with valid frontmatter, then
`aos registry build`. See `docs/skills.md`.

**New agent** — `agents/aos-<name>.md`, plus entries in `config/workflow.json`
(`agents_by_depth`) and `config/models.json` (`agent_preferred_tier`). See `docs/agents.md`.

**New model or tier mapping** — `config/models.json`. Tiers are logical; candidates are tried
in order and `aos models` reports what the environment actually confirms.

**New guard** — append a rule to `config/guards.json`:
`{"id": "...", "action": "BLOCK|REVIEW_REQUIRED|CONFIRM", "why": "...", "regex": "..."}`,
then add a case to `tests/test_guards.py`.

**New project adapter signal** — `runtime/adapter.py`: add to `SIGNS` (marker file →
language, package manager, test and build commands), `FRAMEWORK_DEPS`, or `DB_HINTS`, then
add a fixture to `tests/test_fixtures.py`.

**New workflow depth or stage list** — `config/workflow.json` (`depths`, `agents_by_depth`,
`skill_budget_by_depth`, `max_repair_attempts`).

**New classifier signal** — `config/classifier.json` (`signals`, `dimensions` weights,
`level_thresholds`) or `config/risk.json` (`factors`, `level_thresholds`, `workflow_floor`).

**New evaluation metric** — add the field to `runtime/metrics.py:FIELDS` and, if it should
affect promotion, to `learning._quality`.

**New learnable policy kind** — add it to `policy.ALLOWED_KINDS`, implement its application
in the router/classifier, and add a safety-floor test. Any kind not in that list is rejected.

After any change: `agentic-os validate` (distribution) and `python3 tests/run.py`.
