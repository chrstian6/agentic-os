#!/usr/bin/env python3
"""PreToolUse guard. Dangerous actions are stopped or escalated; ordinary work passes.

Fails open on internal errors (never breaks the session) but never fails open on a
matched BLOCK rule.
"""
import hashlib
import json
import os
import sys
import time

import _boot

WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

CONTRACT = """TASK:        <what you are about to do>      AGENT: aos-builder
MISSION:     <one sentence - what done looks like>
SKILLS:      <paste the output of: .claude/agentic-os/bin/aos brief "<MISSION>" --agent builder>
CONTEXT:     <the paths you were about to edit, and why>
SUCCESS:     <numbered, individually checkable>
FORBIDDEN:   test files you did not write; deploy, migrate, push, install, delete;
             anything outside the files this task names
EVIDENCE:    <the exact commands to run and the output to return>
ESCALATE IF: <the condition that means stop and report rather than improvise>"""


def _cfg(root):
    try:
        with open(os.path.join(root, "config", "auto.json")) as fh:
            return json.load(fh)
    except (IOError, OSError, ValueError):
        return {}


def _turn(root, sid=None):
    return _boot.read_turn(root, sid)


def _mark_enforced(root, turn, sig, sid=None):
    """Remember *which* call was intercepted, not merely that one was.

    The same tool call is evaluated more than once - this hook, plus any project
    auto-approval chain that runs it as a guard - and both must reach the same verdict or
    an `allow` from the other silently wins. A later, different edit in the same turn is
    still let through: the intent is one interception per turn, not a blockade.
    """
    turn["delegation_enforced"] = sig
    _boot.write_turn(root, sid, turn)


def _delegated_already(root, started, sid=None):
    """Did this turn dispatch a subagent before reaching for the file?"""
    return any(_boot.is_delegation(r.get("tool"))
               for r in _boot.session_events(root, sid, since=started))


def _signature(tool, tool_input):
    payload = json.dumps({"t": tool, "i": tool_input or {}}, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def delegation_check(root, tool, tool_input=None, sid=None):
    """At high levels, the first direct edit of a turn is intercepted.

    The injected plan is prose and prose loses to convenience - measured: agents_used was
    0.0 across every recorded run. This is the mechanical half. It fires once per turn,
    only at or above the configured level, and never on a turn that already delegated.
    """
    if tool not in WRITE_TOOLS:
        return None
    cfg = _cfg(root)
    mode = cfg.get("enforce_mode", "ask")
    floor = cfg.get("enforce_delegation_from_level", 4)
    if mode == "off" or not cfg.get("enabled", True) :
        return None
    turn = _turn(root, sid)
    if not turn:
        return None
    # Single mode: the main thread does ordinary work itself; only a turn classified
    # high/critical keeps the delegation check (workflow.plan delegates the same turns).
    risky = turn.get("risk") in ("high", "critical")
    if cfg.get("agent_mode") == "single" and not risky:
        return None
    sig = _signature(tool, tool_input)
    already = turn.get("delegation_enforced")
    if already and already != sig:
        return None                      # a different call, later in the same turn
    if int(turn.get("level", 1)) < int(floor) and not (risky and cfg.get("agent_mode") == "single"):
        return None
    if not already and _delegated_already(root, turn.get("started", 0), sid):
        return None
    _mark_enforced(root, turn, sig, sid)
    agents = [a for a in turn.get("agents", []) if a not in ("orchestrator", "router")]
    # One resolver, not a third inline prefix: the hook text and `aos plan` said
    # different things for the same stage until these were centralised.
    from runtime import classify
    named = ", ".join(classify.dispatch_name(a) for a in agents) \
        or classify.dispatch_name("builder")
    return {
        "action": "BLOCK" if mode == "deny" else "CONFIRM",
        "reason": ("this turn classified level %s (depth %s, risk %s) and no subagent has been "
                   "dispatched. Delegate to %s with a contract instead of editing directly:\n\n%s"
                   "\n\nOverride deliberately if delegation genuinely costs more than it returns."
                   % (turn.get("level"), turn.get("depth"), turn.get("risk"), named, CONTRACT)),
        "matches": [{"id": "delegation.not_dispatched"}],
    }


FAMILY = ("haiku", "sonnet", "opus")
TIER_ALIAS = {"fast": 0, "mid": 1, "balanced": 1, "strong": 2, "deep": 2}


def _family(model):
    low = str(model or "").lower().strip()
    if low in TIER_ALIAS:
        return TIER_ALIAS[low]
    return next((i for i, f in enumerate(FAMILY) if f in low), None)


def model_check(root, tool, tool_input=None, sid=None):
    """An aos-* dispatch must name a model at least as strong as the plan's.

    The plan's model= was prose, and an Agent call without `model` silently inherits the
    parent's (opus): a level-1 lookup billed as deep work, or a high-risk review on haiku.
    Stronger than planned passes; missing or weaker is sent back with the right value.
    """
    if not _boot.is_delegation(tool):
        return None
    ti = tool_input or {}
    sub = str(ti.get("subagent_type") or "")
    if not sub.startswith("aos-") or _cfg(root).get("enforce_model", True) is False:
        return None
    turn = _turn(root, sid)
    if not turn or turn.get("gate_only"):
        return None
    role = sub[4:]
    planned = (turn.get("models") or {}).get(role) if isinstance(turn.get("models"), dict) else None
    if not planned:
        try:
            from runtime import models
            planned = models.route(int(turn.get("level", 1)), turn.get("risk", "normal"), role)["model"]
        except Exception:
            planned = None               # fail closed below: an explicit, rankable model is still required
    want = _family(planned)
    if want is None:                     # unknown plan or router failure: floor by risk
        want = {"critical": 2, "high": 2, "elevated": 1}.get(turn.get("risk"), 0)
    given = _family(ti.get("model"))
    if given is not None and given >= want:
        return None
    if not ti.get("model"):
        why = ""
    elif given is None:
        why = "; %r is not a model this check can rank (use haiku, sonnet or opus)" % ti.get("model")
    else:
        why = "; %s is below that" % ti.get("model")
    target = planned or FAMILY[want]
    return {"action": "BLOCK",
            "reason": ("dispatch %s with model=%s (level %s, risk %s)%s. Re-send the same call "
                       "with `model: \"%s\"`, or a stronger one."
                       % (sub, target, turn.get("level"), turn.get("risk"), why, target)),
            "matches": [{"id": "delegation.model"}]}


SCRATCH = ("/tmp/", "/private/tmp/", "/var/folders/")


def discuss_check(root, tool, tool_input=None, sid=None):
    """Owner rule: an idea, bug or problem is discussed first; nothing is edited before "go".

    Scratch paths stay writable for research notes. Bash is not gated here: the injected
    rule covers commits and pushes, and a shell parser would be a guess.
    """
    cfg = _cfg(root)
    if tool not in WRITE_TOOLS or cfg.get("discuss_gate", "block") == "off" \
            or not cfg.get("enabled", True):
        return None
    turn = _turn(root, sid)
    if not turn or not turn.get("discuss"):
        return None
    path = str((tool_input or {}).get("file_path") or (tool_input or {}).get("notebook_path") or "")
    if path and os.path.realpath(path).startswith(SCRATCH):
        return None
    return {"action": "BLOCK",
            "reason": ("discussion turn: the owner presented an idea, bug or problem and has not "
                       "said go. Present the proposal, trade-offs and options, ask if we are "
                       "ready, and wait. Edits open when the owner replies go."),
            "matches": [{"id": "owner.discuss_first"}]}


HANDBACK_TOOLS = ("SubagentHandback",)


def handback_gate(root, data):
    """Deny a subagent's first hand-back when it edited code and ran nothing after.

    In the desktop app a subagent ends by calling SubagentHandback; SubagentStop fires
    after the report is already delivered, so a block there cannot send it back
    (measured live: gate.log said block, the agent had already returned). A PreToolUse
    deny reaches the subagent as its next instruction. Once per agent, so one that
    genuinely cannot run anything says so and is let through.
    """
    agent_id = data.get("agent_id")
    if data.get("tool_name") not in HANDBACK_TOOLS or not agent_id:
        return None
    if _cfg(root).get("proof_gate", "block") == "off":
        return None
    import stop
    sid = data.get("session_id")
    log = os.path.join(root, "state", "gate.log")
    try:
        with open(log) as fh:
            if any('"agent_id": "%s"' % agent_id in ln and '"handback"' in ln for ln in fh):
                return None
    except (IOError, OSError):
        pass
    gap = stop.proof_gap(_boot.session_events(root, sid, agent_id=agent_id),
                         str((data.get("tool_input") or {}))[:2000])
    stop._trace(root, "handback", sid, agent_id, gap)
    return gap


def main():
    """Hook mode (default): emit a JSON permission decision, exit 0.

    Guard mode (`--guard`): exit 2 when this call should not proceed, nothing on stdout.
    That is the convention a project's own auto-approval chain can consume - without it,
    another hook's `allow` suppresses this one's `ask` and the decision never surfaces.
    """
    guard_mode = "--guard" in sys.argv
    root = _boot.load()
    data = _boot.payload()
    tool = data.get("tool_name") or ""
    if tool in HANDBACK_TOOLS:
        gap = handback_gate(root, data)
        if gap:
            _boot.emit({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": "[agentic-os proof gate] " + gap
                + " Then hand back again with the command and its output."}})
        return 0
    ti = data.get("tool_input") or {}
    try:
        from runtime import guards
    except Exception:
        return 0
    try:
        verdict = model_check(root, tool, ti, data.get("session_id"))
    except Exception as exc:
        verdict = None                   # a bug here must not also switch off the checks below
        _boot.note_error(root, "model_check", exc)
    if not verdict:
        try:
            verdict = discuss_check(root, tool, ti, data.get("session_id"))
        except Exception as exc:
            verdict = None
            _boot.note_error(root, "discuss_check", exc)
    verdict = verdict or delegation_check(_boot.load(), tool, ti, data.get("session_id"))
    if not verdict and tool == "Bash":
        verdict = guards.check(ti.get("command", ""), {"tool": tool})
    elif not verdict and tool in WRITE_TOOLS:
        verdict = guards.check_path_write(ti.get("file_path") or ti.get("notebook_path") or "")
        verdict.setdefault("matches", [])
    if not verdict:
        return 0
    action = verdict["action"]
    if action == "ALLOW":
        return 0
    if guard_mode:
        sys.stderr.write("[agentic-os] %s: %s\n" % (action, verdict.get("reason", "")))
        return 2
    decision = "deny" if action == "BLOCK" else "ask"
    reason = "[agentic-os guard: %s] %s" % (action, verdict.get("reason", ""))
    _boot.emit({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": decision,
                                       "permissionDecisionReason": reason}})
    try:
        from runtime import learning
        con = learning.connect()
        learning.observe(con, None, "guard_%s" % action.lower(),
                         ",".join(m["id"] for m in verdict.get("matches", [])) or "path")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
