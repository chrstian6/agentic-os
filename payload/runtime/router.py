"""Skill router: task -> minimum sufficient set of loaded skills.

Installed skills are not loaded skills. Scoring is trigger-based, filtered by the
acting agent, biased by the project adapter and by learned policies, then trimmed
to the depth's skill budget after dependency and conflict resolution.
"""
import re

from . import paths, policy, registry, util

STACK_DOMAIN_HINTS = {
    "frontend": ["frontend", "visual", "ui"],
    "backend": ["backend", "data"],
}


def load_registry():
    """The OS library plus whatever skills the project already had.

    config/router.json `project_skills: false` routes the OS library alone: a
    project whose own .claude/skills predate the OS can opt out of having them
    compete with (and shadow) the routed set, without deleting them.
    """
    reg = registry.load(paths.p("skills", "registry.json"))
    proj = registry.load(paths.p("skills", "project-registry.json"), )
    cfg = util.load_json(paths.config("router.json"), default={}) or {}
    if cfg.get("project_skills", True) is False:
        proj = {}
    merged = dict(reg.get("skills", {}))
    for name, meta in (proj.get("skills") or {}).items():
        merged.setdefault(name, meta)
    return {"skills": merged, "os_count": len(reg.get("skills", {})),
            "project_count": len(proj.get("skills") or {})}


def _trigger_hit(trig, text):
    """Does this trigger appear in the task as a WORD, not as a substring?

    It used to be a plain `trig in text`, which fires on fragments:

        "rename the variable"  -> trigger `aria`  (v-ARIA-ble)  -> accessibility
        "format the invoice"   -> trigger `orm`   (f-ORM-at)    -> backend
        "format the invoice"   -> trigger `form`  (FORM-at)     -> interaction

    Every one of those pulled a whole skill into a task it has nothing to do
    with, and the shorter the trigger the more often it happens. Boundaries are
    checked against alphanumerics rather than \\b so that a trigger ending in a
    symbol (`next.js`) still matches, and multi-word triggers ("test failed",
    "not working") work unchanged.

    Both edges cannot simply be sealed, because some triggers are deliberate
    STEMS: `accessib` exists to catch "accessible" AND "accessibility". So the
    LEFT edge is always a boundary — that alone kills every case above, since
    all three matched mid-word — and the right edge stays open for a trigger
    long enough to be a stem rather than a word.

    # ponytail: length heuristic, 6 chars. A trigger could declare itself a stem
    # explicitly (`accessib*`) if this ever mis-sorts one; it has not yet.
    """
    t = (trig or "").lower().strip()
    if not t:
        return False
    tail = "" if len(t) >= 6 else r"(?![a-z0-9])"
    return re.search(r"(?<![a-z0-9])%s%s" % (re.escape(t), tail), text) is not None


UI_DOMAINS = {"frontend", "visual", "ui"}
UI_NOUNS = ("ui", "page", "screen", "component", "layout", "css", "style", "button", "form",
            "modal", "dialog", "dashboard", "frontend", "visual", "view", "navbar", "sidebar",
            "landing", "theme", "font", "color", "colour", "responsive", "animation", "hero")
BACKEND_NOUNS = ("api", "endpoint", "rpc", "service", "schema", "migration", "migrate",
                 "database", "query", "worker", "job", "queue", "server", "backend", "sql",
                 "table", "ledger", "webhook", "cron", "settlement", "payout")


def _backend_only(text):
    """The task names backend things and nothing a user sees.

    Measured: "redesign the settlement service, migrate payouts to a new ledger schema"
    routed design-taste and existing-project-redesign on the verb alone, which pulled
    accessibility, anti-ai-slop and responsive-design in as dependencies, and put a
    design critic in the check phase of a backend change.
    """
    return any(_trigger_hit(w, text) for w in BACKEND_NOUNS) and \
        not any(_trigger_hit(w, text) for w in UI_NOUNS)


def score(task_text, agent=None, reg=None, adapter=None, policies=()):
    reg = reg or load_registry()
    text = util.norm(task_text)
    backend_only = _backend_only(text)
    scores = {}
    why = {}
    for name, meta in reg.get("skills", {}).items():
        if agent and meta.get("agents") and agent not in meta["agents"]:
            continue
        s = 0.0
        reasons = []
        # A curated trigger is a deliberate claim; one inferred from a project skill's
        # prose is a guess, and "Design, write and run tests" should not make a test skill
        # win a redesign. Weight them accordingly.
        weight = 1.5 if meta.get("source") == "project" else 3.0
        for trig in meta.get("triggers", []):
            if _trigger_hit(trig, text):
                s += weight
                reasons.append("trigger:%s" % trig.lower())
        for dom in meta.get("domains", []):
            if _trigger_hit(dom, text):
                s += 1.5
                reasons.append("domain:%s" % dom)
        # A project skill's triggers are guessed from its prose ("project", "system",
        # "loop"), so one stray common word must not route it. Require two distinct
        # hits, or its own name in the task.
        if meta.get("source") == "project" and s > 0:
            own = name.split("/", 1)[-1].replace("-", " ")
            hits = len([r for r in reasons if r.startswith("trigger:")])
            if hits < 2 and own not in text.replace("-", " "):
                s, reasons = 0.0, []
        # The stack only breaks ties between skills the TASK already matched. Measured:
        # a Next.js adapter alone scored frontend-engineering 3.3 on "fix the login bug
        # in the api", past min_score, with no word of the task about UI.
        if adapter and s > 0:
            for key, domains in STACK_DOMAIN_HINTS.items():
                if adapter.get(key) and set(domains) & set(d.lower() for d in meta.get("domains", [])):
                    s += 0.5
                    reasons.append("stack:%s" % key)
            for fw in adapter.get("frameworks", []) + adapter.get("languages", []):
                if fw and fw.lower() in [t.lower() for t in meta.get("triggers", [])]:
                    s += 1.0
                    reasons.append("stack:%s" % fw)
        doms = set(d.lower() for d in meta.get("domains", []))
        if backend_only and doms & UI_DOMAINS and "backend" not in doms:
            s, reasons = 0.0, []
        if s > 0:
            s += meta.get("priority", 5) / 10.0
        scores[name] = s
        why[name] = reasons
    policy.apply_skill_scores(scores, task_text, policies)
    return scores, why


def resolve(selected, reg):
    """Pull in dependencies, then drop lower-priority sides of conflicts."""
    skills = reg.get("skills", {})
    out = list(selected)
    i = 0
    while i < len(out):
        for dep in skills.get(out[i], {}).get("dependencies", []):
            if dep in skills and dep not in out:
                out.append(dep)
        i += 1
    dropped = []
    for name in list(out):
        for other in list(out):
            if other == name or name not in out or other not in out:
                continue
            if other in skills.get(name, {}).get("conflicts", []):
                loser = min((name, other), key=lambda n: skills.get(n, {}).get("priority", 5))
                if loser in out:
                    out.remove(loser)
                    dropped.append(loser)
    return out, dropped


def always_for(agent, reg):
    """Skills an agent loads on every task, trigger or not.

    A POSTURE is not a technique. "Do not over-build" and "decide the visual
    rather than defaulting it" apply to every piece of an agent's work, so a
    posture that arrives only when a trigger happens to match is missing from
    exactly the task phrased unusually — the one most likely to need it.

    Measured before this existed: `design-taste` loaded for "build a settings
    page" and not for "add a tooltip to the button". Same agent, same kind of
    work, different wording.

    Configured per agent in config/router.json's `always_by_agent`. Ships empty:
    a posture is a project's ruling about its own work, not something a
    distribution should assume. A name that resolves to no installed skill is
    skipped rather than fatal — a router that crashes on a stale config is worse
    than one that routes without a posture.
    """
    cfg = util.load_json(paths.config("router.json"), default={}) or {}
    wanted = (cfg.get("always_by_agent") or {}).get(agent or "", [])
    return [n for n in wanted if n in reg.get("skills", {})]


def route(task_text, agent=None, budget=6, reg=None, adapter=None, policies=(), min_score=None):
    reg = reg or load_registry()
    if min_score is None:  # tunable: `aos learn tune --knob router.min_score`
        cfg = util.load_json(paths.config("router.json"), default={}) or {}
        min_score = float(cfg.get("min_score", 2.5))
    scores, why = score(task_text, agent, reg, adapter, policies)
    ranked = sorted([(s, n) for n, s in scores.items() if s >= min_score], reverse=True)
    picked = [n for _s, n in ranked[:budget]]
    # Postures go in FIRST and do not consume budget: they are the floor, and a
    # busy task is precisely when they would otherwise be crowded out.
    always = always_for(agent, reg)
    for n in always:
        # Tagged whether or not a trigger also matched: it is loaded because it
        # is mandatory, and a reader who sees only "trigger:page" would think
        # rewording the task could drop it.
        why.setdefault(n, []).append("MANDATORY:%s" % agent)
    picked = [n for n in always if n not in picked] + picked
    resolved, dropped = resolve(picked, reg)
    # dependencies may push past budget; keep them (they are the minimum sufficient set)
    return {
        "loaded": resolved,
        "dropped_conflicts": dropped,
        "considered": len(scores),
        "budget": budget,
        "scores": {n: round(s, 2) for s, n in ranked},
        "why": {n: why.get(n, []) for n in resolved},
        "paths": [reg["skills"][n]["path"] for n in resolved if n in reg.get("skills", {})],
    }
