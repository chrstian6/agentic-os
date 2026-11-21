#!/usr/bin/env python3
"""UserPromptSubmit: run the Agentic OS on every prompt, automatically.

Classifies the prompt, routes the minimum sufficient skill set, and injects the plan plus
the skill content as context - so no one has to remember to call `aos plan`. Trivial
prompts get one line; everything else gets the workflow it needs.

Fails open and silent: a broken runtime must never block a prompt.
"""
import hashlib
import json
import os
import sys
import time

import _boot

FRONT = "---"


def _cfg(root):
    try:
        with open(os.path.join(root, "config", "auto.json")) as fh:
            return json.load(fh)
    except (IOError, OSError, ValueError):
        return {"enabled": True, "min_prompt_chars": 12, "skip_prefixes": ["/"],
                "quiet_below_level": 2, "inline_skill_budget_chars": 14000,
                "max_inlined_skills": 5}


PASTE_MARKERS = ("\u23fa", "\u23bf", "\u2387", "Loaded .claude/", "$ ", "  \u23bf  ",
                 "User answered Claude's questions", "Searched for", "\u2192")


def task_text(prompt, cfg):
    """What the user is asking for, not everything they pasted.

    A pasted transcript or log is context: it is full of nouns from other tasks and it
    inflates both the level and the skill set. Classify on the parts a person actually
    typed - the opening and the closing lines - and cap what is considered.
    """
    text = (prompt or "").strip()
    cap = int(cfg.get("classify_char_cap", 600))
    if len(text) <= cap:
        return text
    looks_pasted = sum(text.count(m) for m in PASTE_MARKERS) >= 2
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if looks_pasted:
        # The ask leads; the paste follows. Keep the opening line, and a trailing line only
        # when it reads like something a person typed rather than transcript tail.
        keep = lines[:1]
        for ln in reversed(lines[1:]):
            body = ln.strip()
            if ln[:1].isspace() or len(body) > 200 or body.startswith(("-", "$", "\u23fa", "\u23bf")):
                continue
            if body.endswith(("?", ".", "!")):
                keep.append(body)
            break
        return "\n".join(keep)[:cap]
    return (text[:cap // 2] + " " + text[-cap // 2:])


HARNESS_MARKERS = ("<task-notification", "<system-reminder", "<side-sessions-event",
                   "<ci-monitor-event", "<cross-session-message", "[Subagent hand-back]")


def is_harness_message(text):
    """Task notifications and subagent hand-backs arrive through the prompt hook too.
    They are not a new task: classifying one re-plans the turn and re-sends skills."""
    head = text[:300]
    return any(head.startswith(m) or m == "[Subagent hand-back]" and m in head
               for m in HARNESS_MARKERS)


def _body(path):
    """Skill text without its frontmatter."""
    try:
        with open(path, errors="replace") as fh:
            text = fh.read()
    except (IOError, OSError):
        return ""
    if text.startswith(FRONT):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return text.strip()


HARNESS_CAP = 9500      # Claude Code's additionalContext limit is 10,000 chars
TAIL_RESERVE = 1800     # the listed/kept lines and closing guidance after the skills
SEEN_FILE = "session_skills.json"
SEEN_KEEP = 30


def _seen(root, sid):
    """Skills already inlined in this session; their text is still in context."""
    if not sid:
        return set()
    try:
        with open(os.path.join(root, "state", SEEN_FILE)) as fh:
            return set(json.load(fh).get(sid, {}).get("names", []))
    except (IOError, OSError, ValueError):
        return set()


def _remember(root, sid, names):
    if not sid or not names:
        return
    path = os.path.join(root, "state", SEEN_FILE)
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (IOError, OSError, ValueError):
        data = {}
    entry = data.get(sid, {"names": []})
    entry["names"] = sorted(set(entry["names"]) | set(names))
    entry["at"] = time.time()
    data[sid] = entry
    data = dict(sorted(data.items(), key=lambda kv: kv[1].get("at", 0))[-SEEN_KEEP:])
    try:
        with open(path + ".tmp", "w") as fh:
            json.dump(data, fh)
        os.replace(path + ".tmp", path)
    except (IOError, OSError):
        pass


def _gate_only_turn(root, session_id):
    """No routing for this prompt, but the Stop proof gate still needs a turn to judge.

    An open turn (a gate block that is still being answered, or a turn a harness message
    interrupts) is kept as it is: its start covers these edits and its classification
    still holds. Otherwise a bare marker, which stop.py gates and does not measure.
    """
    if not _boot.read_turn(root, session_id):
        _boot.write_turn(root, session_id, {"started": time.time(), "gate_only": True})


def build_context(root, prompt, session_id=None):
    sys.path.insert(0, root)
    os.environ.setdefault("AOS_HOME", root)
    from runtime import adapter, learning, paths, workflow  # noqa: E402

    cfg = _cfg(root)
    if not cfg.get("enabled", True):
        return None
    text = (prompt or "").strip()
    if len(text) < cfg.get("min_prompt_chars", 12) \
            or any(text.startswith(p) for p in cfg.get("skip_prefixes", [])) \
            or is_harness_message(text):
        _gate_only_turn(root, session_id)
        return None

    arm, policy_id = "champion", None
    try:
        lcon = learning.connect()
        policies = learning.active(lcon)
        # Challenger sampling: half the turns run the candidate policy, so the
        # comparison has two real arms instead of one arm and a hypothesis.
        pending = learning.challengers(lcon)
        if pending:
            cand = pending[0]
            bucket = int(hashlib.sha1(text.encode("utf-8")).hexdigest(), 16) % 2
            if bucket == 0:
                policies = policies + [cand]
                arm, policy_id = "challenger", cand["id"]
    except Exception:
        policies = []
    try:
        adapter_data = adapter.load(os.path.join(root, "adapter.json"))
    except Exception:
        adapter_data = {}

    subject = task_text(text, cfg)
    plan = workflow.plan(subject, policies=policies, adapter_data=adapter_data)
    c = plan["classification"]
    level = c["difficulty"]["level"]
    risk = c["risk"]

    skills_planned = []
    for stage in plan["stages"]:
        for name in stage["skills"]:
            if name not in skills_planned:
                skills_planned.append(name)
    _boot.write_turn(root, session_id, {
        "started": time.time(), "prompt": subject[:300], "level": level,
        "risk": risk["level"], "depth": c["depth"], "skills": skills_planned,
        "agents": [s["agent"] for s in plan["stages"]],
        "models": {s["agent"]: s["model"] for s in plan["stages"]},
        "arm": arm, "policy_id": policy_id})

    head = ["[Agentic OS] level %d/5, risk %s, workflow depth %d."
            % (level, risk["level"], c["depth"])]
    if risk["factors"]:
        head.append("Risk factors: %s." % ", ".join(risk["factors"][:4]))

    if level < cfg.get("quiet_below_level", 2) and risk["level"] == "normal":
        head.append("Trivial: do it directly, no delegation, no ceremony. "
                    "Still: evidence for any claim, and finish the whole request.")
        # Names only, no inlined text: a trivial turn should not pay for skills, but
        # it should still know which ones exist for it (`aos skills show <name>`).
        named = [n for n in skills_planned if n not in ("shared/evidence", "project/lazy")][:3]
        if named:
            head.append("Relevant skills if needed: %s." % ", ".join(named))
        return " ".join(head)

    lines = list(head)
    lines.append("Workflow: %s." % " -> ".join(plan["workflow"]))
    if plan["delegate"]:
        # the Agent tool takes `model` (haiku|sonnet|opus): name that, not the tier label
        tier = {s["agent"]: "model=%s" % s["model"] for s in plan["stages"]}
        steps = []
        for i, ph in enumerate(plan.get("phases") or [], 1):
            who = ", ".join("%s (%s)" % (d, tier.get(a, "?")) for a, d in zip(ph["agents"], ph["dispatch"]))
            if ph["name"] == "build" and ph.get("parallel"):
                who += " - heavy: one builder per disjoint-file slice, all in ONE message"
            elif ph.get("on_failure"):
                who = "ONLY if a check fails: " + who
            elif len(ph["agents"]) > 1:
                who += ", in ONE message"
            steps.append("%d) %s: %s" % (i, ph["name"], who))
        lines.append("DISPATCH in phases, do not implement directly: %s. Max %d subagents in "
                     "flight. Pass each model= value as the Agent call's `model`. "
                     "Each brief: MISSION / CONTEXT / SUCCESS / FORBIDDEN / EVIDENCE "
                     "(EVIDENCE = commands run and their output, not files read). "
                     "You stay accountable for the result." % ("; ".join(steps), plan.get("max_parallel", 3)))
    elif plan.get("fan_out"):
        lines.append(
            "Single-agent mode, HEAVY task: you own it, but slice it first. Split into parts "
            "that touch disjoint files and need no other part's output. Send one aos-builder "
            "Agent call per part, ALL in ONE message so they run in parallel; each brief "
            "names MISSION and the routed skill lines (paste the output of `aos brief`), the exact "
            "FILES it may touch, SUCCESS, FORBIDDEN, EVIDENCE. Parts that share "
            "files or depend on each other stay serial, here. You integrate and run the final "
            "verification yourself. Too small to slice? Do it here. Queued work: "
            "`aos queue ready` lists tasks with no blockers - those fan out the same way.")
    else:
        lines.append("Do not delegate: %s" % plan["direct_execution_reason"])
    if plan["delegate"] or plan.get("fan_out"):
        for s in plan["stages"]:
            if s["agent"] in ("builder", "repairer", "tester"):
                lines.append('Brief header: run .claude/agentic-os/bin/aos brief "<your MISSION>" '
                             '--agent %s and paste its output at the top of the dispatch prompt.'
                             % s["agent"])
    if plan["test_first"]:
        lines.append("Test-first: write the failing test and watch it fail before implementing.")

    # union of the routed skills across stages, best-scoring first
    best, where = {}, {}
    for stage in plan["stages"]:
        scores = stage.get("skill_scores") or {}
        for i, name in enumerate(stage["skills"]):
            score = float(scores.get(name, 0.0))
            if score >= best.get(name, -1):
                best[name] = score
                where[name] = stage["skill_paths"][i]
    # highest-scoring first: what gets inlined should be what matters most, not whichever
    # stage happened to be listed first
    ordered = [(-best[n], n, where[n]) for n in sorted(best, key=lambda n: -best[n])]
    by_depth = cfg.get("inline_budget_by_depth") or {}
    budget = int(by_depth.get(str(c["depth"]), cfg.get("inline_skill_budget_chars", 10000)))
    max_inline = int((cfg.get("max_inlined_by_depth") or {}).get(
        str(c["depth"]), cfg.get("max_inlined_skills", 4)))
    # A skill inlined earlier in this session is still in context: name it, do not
    # resend it. Measured: three related prompts re-injected 14.5, 16.8 and 17.4 KB.
    # ponytail: after a context compaction the text is gone; the name and path stay
    # in the plan, and `aos skills show <name>` reloads it.
    # Claude Code spills additionalContext over 10,000 chars to a file and shows only a
    # preview: skills past the cap are never read. Measured live: 20.5 KB at depth 4.
    budget = min(budget, HARNESS_CAP - len(" ".join(lines)) - TAIL_RESERVE)
    seen = _seen(root, session_id)
    inlined, listed, kept = [], [], []
    for _i, name, rel in ordered[:max_inline]:
        if name in seen:
            kept.append(name)
            continue
        body = _body(rel if os.path.isabs(rel) else os.path.join(root, rel))
        if body and len(body) <= budget:
            budget -= len(body)
            inlined.append((name, body))
        else:
            listed.append((name, rel))
    for _i, name, rel in ordered[max_inline:]:
        listed.append((name, rel))

    def assemble(inlined, listed, omitted):
        out = [" ".join(lines)]
        if inlined:
            out.append("\nSkills the router SUGGESTS for this task (%d of them) - read them first:"
                       % (len(inlined) + len(listed) + omitted))
            for name, body in inlined:
                out.append("\n<skill name=\"%s\">\n%s\n</skill>" % (name, body))
        if listed or omitted:
            more = ("; %d more omitted to fit the context cap (aos skills search)" % omitted
                    if omitted else "")
            out.append("\nAlso scored, read if needed: %s%s"
                       % (", ".join("%s (%s)" % (n, p) for n, p in listed), more))
        if kept:
            out.append("\nStill in force from earlier this session (not resent): %s." % ", ".join(kept))
        # The suggestion is a starting point, not a permit. Scoring is a keyword
        # heuristic and it misses: it cannot tell that a brand task wants the brand
        # skill when the word "brand" never appears. The agent has judgement the
        # scorer does not, so give it the whole shelf and say so — and say how to
        # reach it, because an agent that does not know the command will not guess.
        if not seen:
            out.append("\nYOU CHOOSE, not the router. The list above is a suggestion from keyword "
                       "scoring, and it is often incomplete. You may read ANY skill in the library, "
                       "as many as the task needs, at any point:\n"
                       "    aos skills list   --agent <you>      what you may use\n"
                       "    aos skills search <words>            find one by name or description\n"
                       "    aos skills show   <name>             read its full text\n"
                       "Load more when the task turns out to need them. Ignore a suggested one that "
                       "does not apply, and say why.")
        out.append("\nGuards run automatically on every command and write. "
                   "Before reporting done, run the completion audit. If this work created a branch or PR: "
                   "before done, merge it (or state why not) and give the PR link - never leave it open silently.")
        return out

    # The cap is on the whole block, not on the skills: over it, Claude Code shows a
    # preview and the closing guard lines are lost. Trim the least important first:
    # the scored-but-not-inlined names, then the lowest-scoring inlined bodies.
    omitted = 0
    out = assemble(inlined, listed, omitted)
    while len("\n".join(out)) > HARNESS_CAP and (listed or inlined):
        (listed or inlined).pop()
        omitted += 1
        out = assemble(inlined, listed, omitted)
    over = len("\n".join(out)) - HARNESS_CAP
    if over > 0:                        # the plan lines alone overflow: shorten them, keep the rest
        out[0] = out[0][:max(len(out[0]) - over - 3, 0)] + "..."
    _remember(root, session_id, [n for n, _b in inlined])
    return "\n".join(out)


def main():
    root = _boot.load()
    data = _boot.payload()
    ctx = build_context(root, data.get("prompt", ""), data.get("session_id"))
    if not ctx:
        return 0
    _boot.emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                       "additionalContext": ctx}})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
