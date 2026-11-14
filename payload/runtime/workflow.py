"""Adaptive engineering workflow: planning, repair bounds and the completion audit.

This module is a planner and state machine. It decides *what* should happen and
records *what did*; the reasoning work itself is performed by the agents Claude Code
runs. It does not claim to execute agents on its own or in the background.
"""
from . import adapter, artifacts, classify, models, paths, router, util

TRIVIAL_MAX_LEVEL = 1
MODES = ("multi", "single")


def _auto():
    try:
        return util.load_json(paths.config("auto.json")) or {}
    except Exception:
        return {}


def agent_mode():
    """'multi' delegates to role agents; 'single' does every stage in the main thread."""
    m = _auto().get("agent_mode", "multi")
    return m if m in MODES else "multi"


def fan_out(level):
    """Heavy task, either mode: slice it and run one builder per independent slice."""
    return level >= int(_auto().get("fanout_from_level", 4))


def max_parallel():
    return max(1, int(_auto().get("max_parallel", 3)))


UI_DOMAINS = {"frontend", "visual", "ui"}


def phases(stages, level):
    """Group role stages into rounds, so a multi-agent run is 2-3 waits, not 5-8.

    Measured before this: a level-3 backend task planned analyst, builder, tester,
    repairer, reviewer as five serial dispatches - a repairer before anything failed.
    Now: prepare (level 4+ only, parallel) -> build -> check (tester and reviewer in
    parallel) -> repair only when a check fails. The main thread is the orchestrator,
    so it is never dispatched; the design critic only joins work that touches UI, and
    the researcher only when the task matched a research skill.
    """
    full = router.load_registry()
    reg = full.get("skills", {})
    always = set(router.always_for("builder", full))
    by = {s["agent"]: s for s in stages}
    def ui_only(name):
        doms = set(d.lower() for d in reg.get(name, {}).get("domains", []))
        return bool(doms & UI_DOMAINS) and "backend" not in doms and name not in always
    ui = any(ui_only(k) for s in stages if s["agent"] == "builder" for k in s["skills"])
    prep = []
    if level >= 4 and "analyst" in by:
        prep.append("analyst")
    if "researcher" in by and by["researcher"].get("skill_scores"):
        prep.append("researcher")
    check = [a for a in ("tester", "reviewer") if a in by]
    if ui and "design-critic" in by:
        check.append("design-critic")
    out = []
    if prep:
        out.append({"name": "prepare", "agents": prep, "parallel": True})
    out.append({"name": "build", "agents": ["builder"], "parallel": fan_out(level)})
    if check:
        out.append({"name": "check", "agents": check, "parallel": True})
    if "repairer" in by:
        out.append({"name": "repair", "agents": ["repairer"], "on_failure": True})
    for ph in out:
        ph["dispatch"] = [classify.dispatch_name(a) for a in ph["agents"]]
    return out


def queue_waves(tasks, policies=()):
    """Turn ready queue rows into parallel waves instead of one full pipeline each.

    Small tasks (level <= 2) share one builder in batches of `batch_size`; heavier ones
    get a builder each. A wave holds at most max_parallel() dispatches, all sent in one
    message. Rows in one wave must touch disjoint files; the caller checks that.
    """
    cap = max_parallel()
    size = max(1, int(_auto().get("batch_size", 3)))
    small, big = [], []
    for t in tasks:
        c = classify.classify("%s %s" % (t.get("title", ""), t.get("body", "") or ""), 0, policies)
        lvl = c["difficulty"]["level"]
        row = {"id": t["id"], "title": t.get("title", ""), "level": lvl, "risk": c["risk"]["level"]}
        (small if lvl <= 2 and c["risk"]["level"] == "normal" else big).append(row)
    units = [{"agent": "aos-builder", "tasks": small[i:i + size]} for i in range(0, len(small), size)]
    units += [{"agent": "aos-builder", "tasks": [r]} for r in big]
    waves = [units[i:i + cap] for i in range(0, len(units), cap)]
    return {"max_parallel": cap, "batch_size": size, "dispatches": len(units), "waves": waves}


def plan(task_text, file_count=0, agent_hint=None, policies=(), adapter_data=None):
    c = classify.classify(task_text, file_count, policies)
    if adapter_data is None:
        try:
            adapter_data = adapter.load(paths.p("adapter.json"))
        except Exception:
            adapter_data = {}
    stages = []
    for agent in c["agents"]:
        r = router.route(task_text, agent=agent, budget=c["skill_budget"],
                         adapter=adapter_data, policies=policies)
        m = models.route(c["difficulty"]["level"], c["risk"]["level"], agent)
        # `agent` stays the bare role — it is the key router.route and
        # models.route look up. `dispatch` is the installed agent name, and the
        # only one a Task call accepts.
        stages.append({"agent": agent, "dispatch": classify.dispatch_name(agent),
                       "model": m["model"], "tier": m["tier"],
                       "skills": r["loaded"], "skill_paths": r["paths"],
                       "skill_scores": r["scores"]})
    wf = util.load_json(paths.config("workflow.json"))
    # Single mode still delegates high/critical risk, matching pre_tool_use.delegation_check.
    risky = c["risk"]["level"] in ("high", "critical")
    delegate = ((agent_mode() == "multi" or risky)
                and c["delegate"] and c["depth"] > TRIVIAL_MAX_LEVEL)
    return {
        "classification": c,
        "workflow": c["workflow"],
        "stages": stages,
        "mode": agent_mode(),
        "fan_out": fan_out(c["difficulty"]["level"]),
        "phases": phases(stages, c["difficulty"]["level"]),
        "max_parallel": max_parallel(),
        # Gate on the risk-floored depth, not raw difficulty: a level-1 task raised by risk still delegates.
        "delegate": delegate,
        "direct_execution_reason": None if delegate else
            ("single-agent mode: do every stage yourself, using the routed skills as role lenses"
             if agent_mode() == "single" else
             "level %d task: delegation would cost more than it returns" % c["difficulty"]["level"]),
        "max_repair_attempts": wf["max_repair_attempts"],
        "test_first": "RED" in c["workflow"],
    }


def repair_decision(attempts, max_attempts, same_failure):
    """Bounded repair. Repeated identical failure changes strategy rather than retrying."""
    if attempts >= max_attempts:
        return {"action": "ESCALATE", "why": "repair budget of %d exhausted" % max_attempts}
    if same_failure and attempts >= 2:
        return {"action": "CHANGE_STRATEGY",
                "why": "the same failure survived %d repairs; the diagnosis is wrong" % attempts}
    return {"action": "REPAIR", "why": "attempt %d of %d" % (attempts + 1, max_attempts)}


AUDIT_QUESTIONS = [
    ("request", "What did the user actually request?"),
    ("definition_of_done", "What defines done for this request?"),
    ("evidence", "What evidence proves each requirement is met?"),
    ("unverified", "What remains unverified?"),
    ("failures", "What failed?"),
    ("repairs", "What was repaired, and was the root cause fixed?"),
    ("avoidance", "Was any difficult part of the request quietly avoided?"),
    ("scope_creep", "Was work added that the user did not ask for?"),
]


def completion_audit(task, agent_artifacts, criteria=()):
    """Return a verdict. COMPLETED requires evidence for every acceptance criterion."""
    findings = []
    covered = []
    evidence_blob = " ".join(
        [str(a.get("summary", "")) for a in agent_artifacts]
        + [str(e) for a in agent_artifacts for e in a.get("evidence", [])]).lower()
    for crit in criteria:
        # ponytail: word-overlap heuristic; a majority of the criterion's significant
        # words must appear in the evidence. It flags gaps for a human, it does not judge.
        words = [w.strip(".,;:()") for w in crit.lower().split() if len(w) > 4]
        hits = [w for w in words if w in evidence_blob]
        if words and len(hits) >= max(2, int(len(words) * 0.5)):
            covered.append(crit)
        else:
            findings.append("no evidence for acceptance criterion: %s" % crit)
    for a in agent_artifacts:
        if a.get("tests_failed"):
            findings.append("%s reports %s failing tests" % (a.get("agent"), a["tests_failed"]))
        if a.get("remaining_work"):
            findings.append("%s reports remaining work: %s" % (a.get("agent"), a["remaining_work"][:3]))
        if a.get("status") in ("failed", "blocked"):
            findings.append("%s finished with status %s" % (a.get("agent"), a.get("status")))
        if a.get("uncertainties"):
            findings.append("%s left uncertainties unresolved: %s" % (a.get("agent"), a["uncertainties"][:3]))
    if criteria and not any(a.get("tests_run") for a in agent_artifacts):
        findings.append("no test was run for a task with acceptance criteria")
    verdict = "COMPLETED" if not findings else ("PARTIAL" if covered else "FAILED")
    return {"verdict": verdict, "criteria_covered": covered, "findings": findings,
            "questions": [q for _k, q in AUDIT_QUESTIONS], "audited_at": util.now()}


def summarize(task, agent_artifacts):
    return artifacts.context_pack(task, agent_artifacts)
