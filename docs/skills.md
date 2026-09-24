# Skills

51 skills live in `.claude/agentic-os/skills/<agent>/<skill>/SKILL.md`. They are *installed*,
not loaded: the router selects a minimum sufficient set per task, typically three to six.

```
shared/          evidence, verification, unlazy, uncertainty, safe-tool-use,
                 context-minimization, artifact-handoff, failure-recovery
orchestrator/    decomposition, delegation-economics
analyst/         requirements-analysis, codebase-analysis, specification
researcher/      technical-research, documentation-analysis, source-evaluation,
                 uncertainty-reduction
builder/         frontend-engineering, backend-engineering, component-architecture,
                 accessibility, responsive-design, performance, security, design-taste,
                 anti-ai-slop, interaction-design, motion, frontend-testing,
                 existing-project-redesign
design-critic/   visual-critique
tester/          test-driven-development, test-design, unit-testing, integration-testing,
                 e2e-testing, regression-testing, edge-case-analysis, failure-analysis,
                 verification
repairer/        systematic-debugging, root-cause-analysis, regression-repair,
                 failure-analysis, verification
reviewer/        code-review, requirements-review, adversarial-review, security-review,
                 completion-audit, quality-review
```

## Frontmatter (the registry source)

```yaml
---
name: builder/design-taste          # must equal the folder path
description: one line
agents: [builder, design-critic]    # which agents may load it
domains: [frontend, visual, design]
triggers: [design, redesign, landing page, ui]
dependencies: [builder/anti-ai-slop, builder/accessibility]
conflicts: []
priority: 9                         # 1-10, breaks ties and resolves conflicts
version: 1.0.0
---
```

`aos registry build` regenerates `skills/registry.json` from the frontmatter;
`aos registry validate` checks that dependencies resolve and that there are no cycles.

## Executable skills

Two skills ship with runnable logic and tests:

- `builder/anti-ai-slop/check.py` — scores HTML/JSX/copy against twelve visual, six copy and
  six code tells, citing lines. `python3 check.py page.tsx`
- `builder/design-taste/check.py` — counts font families, sizes, hues, shadows, radii and
  off-scale spacing against the budget in the skill. `python3 check.py styles.css`

Both have test suites under `tests/` in their own folders, run as part of `tests/run.py`.

## Adding a skill

1. `mkdir -p skills/<agent>/<name>` and write `SKILL.md` with the frontmatter above.
2. The body must cover: what it is, when it applies, when it does not, how to use it,
   common mistakes, verification, and an example. Under ~200 words fails validation.
3. `aos registry build` then `aos registry validate`.
4. `python3 tests/run.py registry` — the distribution validator rejects placeholders.
