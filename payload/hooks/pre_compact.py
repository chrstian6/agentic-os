#!/usr/bin/env python3
"""PreCompact: tell the compaction summary what must survive.

Claude Code uses this hook's stdout as instructions for the summary. Without it the
summary keeps the narrative and drops the parts work depends on: the exact request, what
was proven by running it, and what is still unproven. SessionStart(source=compact)
re-injects the plan from disk afterwards; this keeps the reasoning that disk lacks.
"""
import sys

import _boot

KEEP = """When summarising, keep these verbatim or near-verbatim, in this order:
1. The user's request(s) in their own words, and every constraint or decision they stated.
2. Acceptance criteria and the done-condition.
3. Files changed, each with a one-line reason.
4. PROOF: each command run that verified behaviour, with its exit code and the decisive output line (test counts, HTTP status, error text). Keep failures, not only successes.
5. UNPROVEN: every claim not yet backed by a run - label it unproven. Code that was read but never executed is unproven.
6. Open errors, the current hypothesis, approaches already ruled out, and the next step.
Drop: full file contents, long tool output already summarised above, and exploration that led nowhere."""


def main():
    root = _boot.load()
    data = _boot.payload()
    sid = data.get("session_id")
    out = [KEEP]
    turn = _boot.read_turn(root, sid)
    if turn:
        if not turn.get("gate_only"):
            out.append('\nTurn in progress (from Agentic OS state): "%s" - level %s, risk %s.'
                       % (turn.get("prompt", ""), turn.get("level"), turn.get("risk")))
        ev = _boot.session_events(root, sid, since=turn.get("started", 0))
        files = sorted({e["path"] for e in ev if e.get("path")})[-15:]
        runs = ["%s%s" % (e["cmd"], "" if e.get("ok", True) else " [FAILED]")
                for e in ev if e.get("cmd")][-10:]
        if files:
            out.append("Files touched: " + ", ".join(files))
        if runs:
            out.append("Commands run (most recent last): " + " | ".join(runs))
    sys.stdout.write("\n".join(out)[:9500])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
