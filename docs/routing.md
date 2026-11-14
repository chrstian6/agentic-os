# Routing

Three routers run per task. They run **automatically on every prompt** via the
`UserPromptSubmit` hook, which injects the result as context; `aos plan "<task>"` runs the
same thing by hand.

## Difficulty (levels 1-5)

`config/classifier.json` scores nine weighted dimensions — reasoning, scope, uncertainty,
integration, state, testing, risk, visual, automation — from signal phrases in the task text,
plus points for the number of files involved. A signal matches where a word starts, so stems
like `optimi` still match `optimize`, but `ui` no longer fires inside `build`. The automation
dimension covers agentic work: agents, scheduled and event-driven jobs, document extraction
and LLM features. Thresholds map the total to a level. Everything is
configurable; edit the weights, signals, or thresholds and the classifier changes.

## Risk (normal / elevated / high / critical)

`config/risk.json` scores ten factors: security, privacy, financial, production, data loss,
destructive operations, irreversibility, external systems, credentials, infrastructure. Risk
sets a *workflow floor*: a one-line change to a payment webhook still gets a level-3 workflow.
Risk can raise depth; nothing lowers a risk floor.

## Reclassification

`classify.reclassify(previous, reason, task)` escalates a task mid-flight (a simple bug turns
out to have a hidden dependency). It only ever escalates, and the transition — old depth,
reason — is persisted with the task.

## Model tiers

`config/models.json` maps levels to FAST / BALANCED / DEEP, then applies the risk floor and
the agent's preferred tier. Tiers resolve to real model ids at runtime; `aos models` reports
whether the environment confirmed each one or whether it is an unverified assumption. No
model id is hard-coded anywhere else.

## Skill routing

`aos route "<task>" --agent builder` scores every skill: +3 per trigger match, +1.5 per
domain match, + priority/10, plus small bonuses from the project adapter (a frontend project
biases frontend domains). Skills not compatible with the acting agent are excluded. The top
N (N = the depth's skill budget) above a score floor are selected, then dependencies are
pulled in and conflicts resolved by priority.

Typical result: 3 of 58 skills for a CSS tweak, 8 for a redesign. That gap is the point.

## Delegation

`workflow.plan` decides whether delegation is worth its cost. Level 1 returns
`delegate: false` with the reason. See `orchestrator/delegation-economics`.
