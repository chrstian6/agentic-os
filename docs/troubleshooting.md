# Troubleshooting

**`doctor` says "owned files unmodified: FAIL"** — you edited an installed file. That is
allowed; the message names which. `agentic-os update` keeps edited config files and writes
the new version as `<name>.json.new`. Edits to `runtime/` or `skills/` are overwritten by
update — make those in the canonical distribution instead.

**`doctor` says "registry matches disk: FAIL"** — a skill was added or removed without
rebuilding. `aos registry build`.

**Hooks are not firing** — check `.claude/settings.json` contains three entries whose command
path includes `.claude/agentic-os/hooks`, restart the session (hooks are read at start), and
run the hook by hand:
`echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | python3 .claude/agentic-os/hooks/pre_tool_use.py`
It should print a `deny` decision. Hooks fail open on internal errors by design, so a broken
runtime shows up as silence — run `agentic-os doctor`.

**A safe command is being blocked** — `aos guard '<command>'` shows which rule matched.
Narrow that rule's regex in `config/guards.json` and add a case to `tests/test_guards.py`.
Do not delete a rule to unblock one command.

**`aos: command not found`** — it is not on your PATH by design. Use
`.claude/agentic-os/bin/aos`, or alias it.

**Model tier reports "unconfirmed"** — the environment did not expose a model list, so the
configured candidate is used as an assumption. Set `AOS_AVAILABLE_MODELS=opus,sonnet,haiku`
to confirm explicitly.

**The queue is stuck: everything is WAITING_DEPENDENCY** — an inferred dependency is probably
wrong. `aos queue get <id>` shows the blockers; complete or cancel the blocker, or delete the
row from `deps` in `state/queue.db`.

**A learned policy is making bad decisions** — `aos learn active` to see what is in force,
`aos learn rollback <id>` to reverse it. Rollback restores the previous champion.

**Reinstalling from scratch** — `agentic-os install --clean`. It resets state and removes
stale files, and never touches anything it does not own.
