"""Difficulty and risk classification."""
import re

from . import paths, policy, util

# Agent definitions install as `.claude/agents/aos-<role>.md`, but every config
# keyed on an agent — workflow.json's agents_by_depth, models.json's tiers, a
# skill's `agent:` frontmatter — uses the bare role. Both spellings are load
# bearing: the bare one is the lookup key, the prefixed one is the only thing
# the Task tool will accept, and a host guard that reads `.claude/agents/`
# refuses anything with no definition there.
#
# So the prefix is applied at the presentation boundary, in one place. It used
# to be an inline "aos-%s" in the UserPromptSubmit hook, which meant the hook
# said `aos-builder` while `aos plan` said `builder` for the same stage — the
# JSON being the half people script against.
AGENT_PREFIX = "aos-"


def dispatch_name(agent):
    """The installed agent name for a role — what you type into a Task call."""
    return agent if agent.startswith(AGENT_PREFIX) else AGENT_PREFIX + agent


def _load(name, cache={}):
    if name not in cache:
        cache[name] = util.load_json(paths.config(name))
    return cache[name]


def _matches(phrase, text, cache={}):
    """True when `phrase` occurs in `text` starting at a word boundary.

    Signals are stems ("optimi", "concurren"), so the end stays open. The start must
    not: plain substring matching let "ui" fire on "build", "form" on "platform" and
    "test" on "latest", which skewed scores toward the wrong dimensions.
    """
    if phrase not in cache:
        cache[phrase] = re.compile(r"(?<![a-z0-9])" + re.escape(phrase))
    return cache[phrase].search(text) is not None


def difficulty(task_text, file_count=0, policies=(), cfg=None):
    cfg = cfg or _load("classifier.json")
    text = util.norm(task_text)
    scores = {}
    hits = []
    for dim, signals in cfg["signals"].items():
        raw = 0
        for phrase, points in signals.items():
            if _matches(phrase, text):
                raw += points
                hits.append("%s:%s(%+d)" % (dim, phrase, points))
        weight = cfg["dimensions"].get(dim, {}).get("weight", 1.0)
        scores[dim] = max(0.0, raw) * weight
    total = sum(scores.values())
    for threshold, points in sorted(cfg["file_count_points"].items(), key=lambda kv: int(kv[0])):
        if file_count >= int(threshold):
            total += points
    thresholds = cfg["level_thresholds"]
    level = 1
    for t in thresholds:
        if total >= t:
            level += 1
    level = policy.apply_level(level, task_text, policies)
    return {"level": level, "score": round(total, 2), "dimensions":
            {k: round(v, 2) for k, v in scores.items()}, "signals": hits}


def _risk_hit(pat, text, cache={}):
    """A risk pattern as a word, with a plural/past tail, unless it is a long stem.

    Substring matching made "auth" fire on "author", "iam" on "william" and "charge"
    on "charger", so plain copy edits came back elevated and taught everyone to ignore
    the risk line. Patterns of 7+ characters stay open stems ("authoriz", "session").
    """
    if pat not in cache:
        p = pat.strip()
        if len(p) >= 7 or not p[-1:].isalnum():
            rx = re.escape(p)
        else:
            # Derived forms: settle->settlement, delete->deletion (the e drops), crypto->cryptography.
            # A dropped e must be replaced by a suffix, or "stripe" fires on "strip", "wipe" on "wip".
            if p.endswith("e"):
                tail = r"(?:e(?:s|d|ment|ments)?|ing|ion|ions)"
                rx = re.escape(p[:-1]) + tail
            else:
                rx = re.escape(p) + r"(?:s|es|d|ed|ing|ion|ions|graphy|graphic)?"
            rx += r"(?![a-z0-9])"
        cache[pat] = re.compile(r"(?<![a-z0-9])" + rx)
    return cache[pat].search(text) is not None


def risk(task_text, cfg=None):
    cfg = cfg or _load("risk.json")
    text = util.norm(task_text)
    points = 0
    factors = []
    for name, spec in cfg["factors"].items():
        for pat in spec["patterns"]:
            if _risk_hit(pat, text):
                points += spec["points"]
                factors.append("%s:%s" % (name, pat.strip()))
                break
    th = cfg["level_thresholds"]
    level = "normal"
    if points >= th["critical"]:
        level = "critical"
    elif points >= th["high"]:
        level = "high"
    elif points >= th["elevated"]:
        level = "elevated"
    return {"level": level, "points": points, "factors": factors,
            "workflow_floor": cfg["workflow_floor"].get(level)}


def classify(task_text, file_count=0, policies=()):
    d = difficulty(task_text, file_count, policies)
    r = risk(task_text)
    depth = d["level"]
    if r["workflow_floor"]:
        depth = max(depth, int(r["workflow_floor"]))
    depth = policy.apply_depth(depth, task_text, policies)
    wf = _load("workflow.json")
    return {
        "difficulty": d, "risk": r, "depth": depth,
        "workflow": wf["depths"][str(depth)],
        "agents": wf["agents_by_depth"][str(depth)],
        "dispatch": [dispatch_name(a) for a in wf["agents_by_depth"][str(depth)]],
        "skill_budget": wf["skill_budget_by_depth"][str(depth)],
        "delegate": depth >= wf["delegation_threshold_level"],
    }


def reclassify(previous, reason, task_text, file_count=0, extra_level=1, policies=()):
    """Raise a task's classification mid-flight. Reclassification only ever escalates."""
    fresh = classify(task_text, file_count, policies)
    fresh["depth"] = max(fresh["depth"], min(5, int(previous.get("depth", 1)) + extra_level))
    wf = _load("workflow.json")
    fresh["workflow"] = wf["depths"][str(fresh["depth"])]
    fresh["agents"] = wf["agents_by_depth"][str(fresh["depth"])]
    fresh["dispatch"] = [dispatch_name(a) for a in fresh["agents"]]
    fresh["skill_budget"] = wf["skill_budget_by_depth"][str(fresh["depth"])]
    fresh["reclassified_from"] = previous.get("depth")
    fresh["reclassification_reason"] = reason
    return fresh
