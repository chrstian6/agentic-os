# Installation

## Fresh install

```bash
cd target-project
/path/to/agentic-os/bin/agentic-os install
```

Steps performed, in order:

1. Detect the project (language, package manager, test runner, build, lint, frameworks,
   databases, monorepo, CI, VCS) and write `.claude/agentic-os/adapter.json`.
2. Copy the canonical payload into `.claude/agentic-os/` (runtime, config, skills, hooks, bin).
3. Install the nine agents into `.claude/agents/aos-*.md` and the entry skill into
   `.claude/skills/agentic-os/SKILL.md`.
4. Merge the constitution block into `.claude/CLAUDE.md` between
   `<!-- AGENTIC-OS:BEGIN -->` and `<!-- AGENTIC-OS:END -->` (a backup is written first).
5. Merge three hooks into `.claude/settings.json` (a backup is written first).
6. Build the skill registry and initialise the queue, learning and metrics databases.
7. Write the ownership manifest and run `doctor`.

`install` is idempotent: running it again reuses the install id, replaces owned files, and
never duplicates a hook, an agent, or the CLAUDE.md block.

## Clean install

```bash
agentic-os install --clean
```

Removes the entire `.claude/agentic-os` directory (which the installer owns in full,
including files an older version left behind) and the owned files outside it, then installs
fresh with empty state. It never touches your source, your git history, your `.env`, your
other agents and skills, or the rest of `.claude`.

## Update

```bash
agentic-os update
```

Replaces runtime, skills, agents, hooks and docs; preserves `state/` (queue, learning,
metrics, artifacts) and `adapter.json`. Config files you have edited are kept and the new
version is written alongside as `<name>.json.new` so you can merge deliberately.

## Uninstall

```bash
agentic-os uninstall
```

Removes only manifest-owned content: the installation directory, the `aos-*` agents, the
`agentic-os` entry skill, the CLAUDE.md block, and the three hook entries. Anything it
cannot prove it owns is reported as left behind rather than deleted.

## Ownership

`.claude/agentic-os/manifest.json` records the install id, version, schema versions, and a
SHA-256 for every file the installer created. `update`, `--clean`, `uninstall` and `doctor`
all work from it. Deletion is additionally constrained: only paths inside the installation
directory, `.claude/agents/aos-*`, and `.claude/skills/agentic-os/` can ever be removed.
