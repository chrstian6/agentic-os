---
name: shared/github-workflow
description: Run branches, pull requests, CI, reviews and merges the way a senior engineer does - small PRs, never merge red, verify the pushed state, and never leave a PR to go stale.
agents: [orchestrator, builder, repairer, reviewer]
domains: [git, github, delivery]
triggers: [pull request, pr, merge, branch, github, gh, ci, rebase, conflict, review comment, push, stale pr, checks]
dependencies: []
conflicts: []
priority: 7
version: 1.0.0
---

# GitHub workflow

Repo rules win over this file: required reviews, protected branches, who may run git.
Read `CLAUDE.md` and the repo's contributing rules before the first git command.

## Before new work

1. `gh pr list --author @me --state open` - finish, merge or close what is open first.
   A new PR on top of a stale one doubles the merge debt.
2. `git status` - a dirty tree is someone's work. Do not stash, reset or switch over it.
3. Branch from the up-to-date base: `git fetch origin && git switch -c <type>/<topic> origin/<base>`.
   One branch per task. Resolve the base with
   `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name` when unsure.

## While working

- Small PRs: one concern, reviewable in one sitting. Split unrelated changes.
- Stage by path (`git add <files>`), never `git add -A` on a tree you did not fully write.
- Commit messages say why, not what. Follow the repo's attribution lines.
- Never force-push a shared branch. On your own branch use `--force-with-lease`, never `--force`.
- Rebase or merge the base when it moves; resolve each conflict by reading both sides,
  never by taking one side wholesale.

## Before merge

1. `gh pr checks <n>` - every required check green. Never merge red. Never `--admin` past a
   rule; a failed rule is the guard working.
2. A red check is a lead, not a verdict: open the log (`gh run view <id> --log-failed`),
   find the failing line, rerun once to rule out a flake before changing code.
3. Read every review comment. Fix it or answer why not, then resolve the thread.
4. Required reviews: the author never counts as an independent reviewer.

## Self-approval (agent merges its own PR)

The owner wants PRs merged without waiting on a human. GitHub never lets the author approve
their own PR, and a change reviewed only by its author is never merged. So the agent approves
through independent reviewers, then merges.

1. Dispatch two independent `aos-reviewer` passes in ONE message, each on a different lens
   (correctness plus the change's risk lens: security, data or interface). Give them the
   diff, not your conclusion.
2. Fix every blocking finding, or rebut it with evidence (see False positives in
   `shared/senior-engineer`). A fix that changes code gets one more review pass.
3. Post the outcome on the PR: `gh pr comment <n> --body "<reviewers, lenses, findings, fixed/waived>"`.
4. Once `gh pr checks <n>` is green, merge with `gh pr merge <n> --squash --delete-branch`.
   If a required check is still pending, arm `gh pr merge <n> --auto --squash --delete-branch`
   instead of waiting.
5. Never `--admin`. If a ruleset requires a human review, arm auto-merge, report the PR link,
   and stop.

## After merge

- Delete the branch (`gh pr merge <n> --squash --delete-branch`, or the repo's merge style).
- Verify by reading the result, not the exit code:
  `git fetch origin && git log origin/<base> --oneline -3`, or `gh pr view <n> --json state,mergedAt`.
- A pushed branch is verified with `git ls-remote origin <branch>` against the local SHA.

## Stale PRs

A PR idle more than a day gets one of: merged, rebased and re-reviewed, or closed with a
reason (`gh pr close <n> --comment "<why>"`). Never leave one open without saying why.
Report the PR link and its blocker when work ends with it still open.
