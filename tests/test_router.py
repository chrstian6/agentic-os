import os

from helpers import PAYLOAD
from runtime import registry, router

REG = registry.load(os.path.join(PAYLOAD, "skills", "registry.json"))


def route(task, agent=None, budget=6):
    return router.route(task, agent=agent, budget=budget, reg=REG)


def test_css_task_loads_frontend_skills_only():
    r = route("adjust the css padding on the pricing page component", agent="builder")
    assert any(s.startswith("builder/frontend") or s == "builder/component-architecture"
               for s in r["loaded"]), r["loaded"]
    assert not any(s.startswith("builder/backend") for s in r["loaded"]), r["loaded"]
    assert not any(s.startswith("tester/") for s in r["loaded"]), r["loaded"]


def test_backend_task_loads_backend_and_security():
    r = route("add an api endpoint that writes to the database", agent="builder")
    assert "builder/backend-engineering" in r["loaded"], r["loaded"]
    assert "builder/security" in r["loaded"], "security is a declared dependency"
    assert "builder/design-taste" not in r["loaded"]


def test_redesign_loads_design_stack():
    r = route("redesign the landing page so it stops looking generic",
              agent="builder", budget=8)
    for expected in ("builder/design-taste", "builder/anti-ai-slop"):
        assert expected in r["loaded"], r["loaded"]
    assert "builder/accessibility" in r["loaded"], "dependency resolution"


def test_security_task_loads_security_skills():
    r = route("review the auth token handling for injection vulnerabilities", agent="reviewer")
    assert "reviewer/security-review" in r["loaded"], r["loaded"]


def test_unrelated_skills_stay_unloaded():
    r = route("adjust the css padding on the pricing page", agent="builder", budget=8)
    assert len(r["loaded"]) < len(REG["skills"]) / 4, r["loaded"]
    assert "researcher/source-evaluation" not in r["loaded"]


def test_agent_filter_excludes_other_agents_skills():
    r = route("debug the failing integration test", agent="repairer")
    for s in r["loaded"]:
        agents = REG["skills"][s]["agents"]
        assert not agents or "repairer" in agents, (s, agents)


def test_dependencies_are_pulled_in():
    r = route("redesign the dashboard ui", agent="builder", budget=2)
    assert len(r["loaded"]) > 2, "dependencies must survive the budget"


def test_empty_task_loads_nothing():
    assert route("", agent="builder")["loaded"] == []


def test_mandatory_postures_load_regardless_of_wording():
    """A posture must not depend on the task's phrasing.

    Measured before always_by_agent existed: `builder/design-taste` loaded for
    "build a settings page" and NOT for "add a tooltip to the button" — same
    agent, same kind of work, different words. That is the failure a posture
    exists to prevent, so it cannot itself be trigger-driven.
    """
    import json as _json
    import os as _os

    from runtime import paths, router, util

    cfg_path = paths.config("router.json")
    original = open(cfg_path).read()
    reg = router.load_registry()
    posture = "builder/design-taste"
    assert posture in reg["skills"], "fixture skill missing from the registry"
    try:
        cfg = _json.loads(original)
        cfg["always_by_agent"] = {"builder": [posture, "no/such-skill"]}
        with open(cfg_path, "w") as fh:
            _json.dump(cfg, fh)
        util.load_json.__globals__.setdefault("_", None)   # no cache to clear

        for task in ("add a tooltip to the button",
                     "build a settings page",
                     "rename a variable"):
            got = router.route(task, agent="builder")
            assert posture in got["loaded"], \
                "posture missing for %r: %s" % (task, got["loaded"])
            assert "MANDATORY:builder" in got["why"].get(posture, []), got["why"]

        # a name that resolves to nothing installed is skipped, not fatal
        assert "no/such-skill" not in router.route("x", agent="builder")["loaded"]
        # and it does not leak into another agent
        assert posture not in router.route("add a tooltip to the button",
                                           agent="researcher")["loaded"]
    finally:
        with open(cfg_path, "w") as fh:
            fh.write(original)
    assert _os.path.exists(cfg_path)


def test_a_trigger_matches_a_word_not_a_fragment():
    """Short triggers must not fire inside longer words.

    Measured with a plain `trig in text`:
      "rename the variable"  -> `aria` (v-ARIA-ble)  pulled in accessibility
      "format the invoice"   -> `orm`  (f-ORM-at)    pulled in backend
      "format the invoice"   -> `form` (FORM-at)     pulled in interaction

    But the left edge alone is not enough either: some triggers are deliberate
    STEMS (`accessib` catches both "accessible" and "accessibility"), so the
    right edge stays open once a trigger is long enough to be a stem.
    """
    from runtime.router import _trigger_hit as hit

    # fragments — every one of these was a real false positive
    assert not hit("aria", "rename the variable userid to customerid")
    assert not hit("orm", "format the invoice")
    assert not hit("form", "format the invoice")
    assert not hit("bug", "open the debugger")

    # real words still match
    assert hit("aria", "add aria labels to the nav")
    assert hit("form", "add a form to the page")
    assert hit("debug", "debug the checkout flow")

    # stems still match both inflections
    assert hit("accessib", "improve the accessibility of the nav menu")
    assert hit("accessib", "make the menu accessible")

    # punctuation and multi-word triggers are unaffected
    assert hit("next.js", "upgrade next.js to 16")
    assert hit("test failed", "the test failed again")
