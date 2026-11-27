#!/usr/bin/env python3
"""Stop hook: turn a finished turn into measurements and observations.

Without this the OS observes everything and records nothing - the queue and metrics stay
empty and the learning loop never has an input. Here every turn produces one metrics row
(for whichever experiment arm the prompt hook picked) and any observations the evidence
actually supports.

Only measurable facts are recorded. `success` is an explicit proxy - "no tool call in this
turn returned an error" - not a judgement about whether the work was right.
"""
import json
import os
import re
import sys
import time

import _boot

FRONTEND_EXT = (".tsx", ".jsx", ".css", ".scss", ".vue", ".svelte", ".html")
BACKEND_HINT = re.compile(r"(/api/|route\.ts|server|handler|\.sql$|schema|migration|drizzle|prisma)", re.I)
TEST_HINT = re.compile(r"(test|spec)[./_-]|__tests__|\.test\.|\.spec\.", re.I)
TEST_CMD = re.compile(r"\b(pytest|vitest|jest|npm (run )?test|yarn test|pnpm test|go test|cargo test|mix test|rspec)\b", re.I)

DOMAIN_SKILL = [
    ("frontend", "builder/frontend-engineering"),
    ("backend", "builder/backend-engineering"),
    ("testing", "tester/test-design"),
]


def summarize(turn, events):
    paths = [e.get("path", "") for e in events if e.get("path")]
    cmds = [e.get("cmd", "") for e in events if e.get("cmd")]
    errors = [e for e in events if not e.get("ok", True)]
    return {
        "tool_calls": len(events),
        "errors": len(errors),
        "files_touched": sorted(set(paths)),
        "agents_used": len(set(e.get("agent") for e in events if e.get("agent"))),
        "test_runs": len([c for c in cmds if TEST_CMD.search(c)]),
        "domains": {
            "frontend": any(p.endswith(FRONTEND_EXT) for p in paths),
            "backend": any(BACKEND_HINT.search(p) for p in paths),
            "testing": any(TEST_HINT.search(p) for p in paths),
        },
    }


STOPWORDS = {"the", "this", "that", "with", "from", "into", "make", "made", "please",
             "should", "would", "could", "there", "these", "those", "your", "have"}


def scope_for(turn, s):
    """A policy scope that will actually match future prompts.

    The domain word ("frontend") rarely appears in what people type, so a policy scoped to
    it would never fire. Prefer a token the prompt and the touched files share - "dashboard",
    "repairs", "invoice" - which is exactly the recurring shape worth learning about.
    """
    words = [w.strip(".,;:()/-") for w in turn["prompt"].lower().split()]
    words = [w for w in words if len(w) > 4 and w not in STOPWORDS]
    blob = " ".join(s["files_touched"]).lower()
    for w in words:
        if w[:6] in blob or w.rstrip("s") in blob:
            return w
    return words[0] if words else ""


def observations(turn, s):
    """Only signals the evidence supports. Each becomes a learning pattern."""
    out = []
    tag = "-".join(turn["prompt"].lower().split()[:3])[:40] or "untitled"
    loaded = set(turn.get("skills", []))
    scope = scope_for(turn, s)

    if turn["level"] <= 1 and (len(s["files_touched"]) >= 3 or s["tool_calls"] >= 15):
        out.append(("underclassified", tag))
    if s["errors"] >= 3:
        out.append(("repair_loop", tag))
    for domain, skill in DOMAIN_SKILL:
        if s["domains"][domain] and skill not in loaded:
            out.append(("missing_skill", "%s|%s" % (scope, skill)))
        if skill in loaded and not s["domains"][domain] and s["files_touched"]:
            out.append(("unused_skill", "%s|%s" % (scope, skill)))
    if s["test_runs"] == 0 and s["files_touched"] and turn["depth"] >= 2:
        out.append(("no_verification", tag))
    if turn["depth"] >= 3 and s["agents_used"] == 0 and s["files_touched"]:
        out.append(("no_delegation", tag))
    return out


DOC_EXT = (".md", ".mdx", ".txt", ".rst", ".adoc")
CLAIM = re.compile(r"\b(tests? (now )?pass(es|ed|ing)?|all (tests )?(green|passing)|"
                   r"(it|this|everything) (now )?works|verified|confirmed working|"
                   r"fixed and tested|build (passes|succeeds))\b", re.I)


NEGATION = re.compile(r"(\b(not|never|no|without|yet to be)\b|n't)\W*(\w+\W+){0,2}$", re.I)


def _claim(text):
    """The first success claim that is not negated ("hasn't been verified" is honesty)."""
    for m in CLAIM.finditer(text):
        clause = re.split(r"[.;:!?\n]", text[max(0, m.start() - 40):m.start()])[-1]
        if not NEGATION.search(clause):
            return m.group(0)
    return None


def _cfg(root):
    try:
        with open(os.path.join(root, "config", "auto.json")) as fh:
            return json.load(fh)
    except (IOError, OSError, ValueError):
        return {}


def _trace(root, event, sid, agent_id, gap):
    """One line per gate decision, so a miss can be diagnosed and the gate measured."""
    try:
        path = os.path.join(root, "state", "gate.log")
        with open(path, "a") as fh:
            fh.write(json.dumps({"at": time.time(), "event": event, "session": sid,
                                 "agent_id": agent_id,
                                 "verdict": "block" if gap else "pass"}) + "\n")
        if os.path.getsize(path) > 200000:
            lines = open(path).readlines()[-500:]
            with open(path, "w") as fh:
                fh.writelines(lines)
    except (IOError, OSError):
        pass


def proof_gap(events, last_message=""):
    """Why this turn has not proven its work, or None.

    Reading code shows what the code says, not what it does. Two mechanical signals:
    a code edit with no command run after it, and a success claim with no command
    run at all. Docs-only edits need no run.
    """
    last_run, last_edit, edited = -1, -1, []
    for i, e in enumerate(events):
        if e.get("cmd"):
            last_run = i
        path = e.get("path") or ""
        if e.get("tool") in ("Edit", "Write", "MultiEdit", "NotebookEdit") and path \
                and not path.lower().endswith(DOC_EXT):
            last_edit = i
            if last_run < i:
                edited.append(path)
    if last_edit > last_run:
        unrun = sorted({p for p in edited})[-5:]
        return ("No proof: %s changed after the last command run. Run the narrowest real "
                "check (test, build, script, request) and report its command and output. "
                "If nothing can be run, say so explicitly and mark the change unverified."
                % ", ".join(unrun))
    claim = _claim(last_message) if last_run < 0 and last_message else None
    if claim:
        return ("No proof: the reply claims \"%s\" but nothing was run this turn. Run the "
                "check and quote its output, or restate the claim as unverified." % claim)
    return None


def handback_gap(reply, budget_tokens):
    """A subagent's reply lands in the lead's context; past the budget it costs more than it
    returns (Anthropic: condensed 1-2k token summaries). ~4 chars per token. 0 disables."""
    if budget_tokens <= 0 or len(reply) // 4 <= budget_tokens:
        return None
    return ("Hand-back is ~%d tokens, over the %d budget. Condense it: the answer first, then "
            "paths with line numbers, commands with exit codes, what is unverified. No pasted "
            "files or logs." % (len(reply) // 4, budget_tokens))


def main():
    root = _boot.load()
    data = _boot.payload()
    sid = data.get("session_id")
    sub = data.get("hook_event_name") == "SubagentStop"
    turn = _boot.read_turn(root, sid)
    if not turn and not sub:
        return 0
    since = (turn or {}).get("started", 0)
    gate = _cfg(root).get("proof_gate", "block")

    if sub:
        agent_id = data.get("agent_id")
        if not agent_id or gate == "off" or data.get("stop_hook_active"):
            return 0
        # agent_id is unique per subagent: no time window. A new prompt mid-run resets
        # the turn's start and hid a live subagent's edit from the gate.
        reply = data.get("last_assistant_message") or ""
        gap = proof_gap(_boot.session_events(root, sid, agent_id=agent_id), reply) \
            or handback_gap(reply, int(_cfg(root).get("handback_tokens", 2000)))
        _trace(root, "SubagentStop", sid, agent_id, gap)
        if gap:
            # Exit 2 + stderr, not JSON: measured live, a JSON block on SubagentStop was
            # logged here and the subagent stopped anyway.
            sys.stderr.write("[agentic-os proof gate] " + gap + "\n")
            return 2
        return 0

    main_events = _boot.session_events(root, sid, since=since, main_only=True)
    if gate != "off" and not data.get("stop_hook_active"):
        gap = proof_gap(main_events, data.get("last_assistant_message") or "")
        _trace(root, "Stop", sid, None, gap)
        if gap:
            # keep the turn: the stop that follows the proof is the one measured
            _boot.emit({"decision": "block", "reason": "[agentic-os proof gate] " + gap})
            return 0

    if turn.get("gate_only"):
        # no classification to measure against: a metrics row here would be noise
        _boot.drop_turn(root, sid)
        return 0
    try:
        from runtime import learning, metrics
    except Exception:
        return 0
    events = _boot.session_events(root, sid, since=since)
    if not events:
        _boot.drop_turn(root, sid)
        return 0
    s = summarize(turn, events)

    metrics.record(
        metrics.connect(), None,
        arm=turn.get("arm", "champion"), policy_id=turn.get("policy_id"),
        depth=turn.get("depth"), risk=turn.get("risk"),
        success=0.0 if s["errors"] else 1.0,
        first_pass_success=1.0 if not s["errors"] and s["tool_calls"] else 0.0,
        repairs=float(s["errors"]),
        tests_run=s["test_runs"], tests_failed=0,
        agents_used=s["agents_used"], skills_loaded=len(turn.get("skills", [])),
        latency_ms=int((time.time() - turn.get("started", time.time())) * 1000),
    )
    lcon = learning.connect()
    for kind, key in observations(turn, s):
        learning.observe(lcon, None, kind, key)
    _boot.drop_turn(root, sid)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
