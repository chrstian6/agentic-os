"""A project's own skills must be routable too.

myjeweler-ai has 101 skills in .claude/skills - anti-card, apple-design,
animation-vocabulary - and the router could not see one of them. Discovering them is what
makes "I have a bunch of design skills" true in practice rather than on disk.
"""
import os
import sys

from helpers import DIST, PAYLOAD, rm, tmpdir, write
from runtime import registry, router

sys.path.insert(0, os.path.join(DIST, "installer"))
import installer  # noqa: E402

PROJECT_SKILLS = {
    "anti-card": "---\nname: anti-card\ndescription: Stop wrapping every section in a card. "
                 "Use space and type to group instead of borders and shadows.\n---\n" + "x " * 300,
    "apple-design": "---\nname: apple-design\ndescription: Apple-style visual design: "
                    "restraint, typography, generous whitespace, precise alignment.\n---\n" + "y " * 300,
    "postgres-tuning": "---\nname: postgres-tuning\ndescription: Index and query plan tuning "
                       "for a postgres database backend.\n---\n" + "z " * 300,
    "broken": "no frontmatter at all, and barely any body",
}


def _project():
    d = tmpdir()
    write(os.path.join(d, "package.json"), '{"name":"x","dependencies":{"next":"14"}}')
    for name, text in PROJECT_SKILLS.items():
        write(os.path.join(d, ".claude", "skills", name, "SKILL.md"), text)
    return d


def test_project_skills_are_discovered_with_inferred_triggers():
    d = _project()
    try:
        found = registry.scan_project(os.path.join(d, ".claude", "skills"))
        assert set(found) >= {"project/anti-card", "project/apple-design",
                              "project/postgres-tuning"}
        card = found["project/anti-card"]
        assert "card" in card["triggers"], card["triggers"]
        assert card["priority"] < 5, "project skills must lose a tie to a vetted OS skill"
        assert card["source"] == "project"
        assert "visual" in found["project/apple-design"]["domains"], found["project/apple-design"]
        assert "backend" in found["project/postgres-tuning"]["domains"]
    finally:
        rm(d)


def test_a_malformed_project_skill_is_skipped_not_fatal():
    d = _project()
    try:
        found = registry.scan_project(os.path.join(d, ".claude", "skills"))
        assert "project/broken" in found, "a description-less skill is still discoverable"
        assert found["project/broken"]["triggers"], "falls back to the folder name"
    finally:
        rm(d)


def test_the_agentic_os_entry_skill_is_not_re_registered():
    d = _project()
    try:
        write(os.path.join(d, ".claude", "skills", "agentic-os", "SKILL.md"),
              "---\nname: agentic-os\ndescription: entry\n---\nbody")
        found = registry.scan_project(os.path.join(d, ".claude", "skills"))
        assert "project/agentic-os" not in found
    finally:
        rm(d)


def test_router_reaches_project_skills_alongside_os_skills():
    d = _project()
    try:
        inst = installer.Install(d, quiet=True)
        inst.install()
        root = os.path.join(d, ".claude", "agentic-os")
        os_reg = registry.load(os.path.join(root, "skills", "registry.json"))
        proj = registry.load(os.path.join(root, "skills", "project-registry.json"))
        assert len(proj["skills"]) >= 3, proj

        merged = dict(os_reg["skills"])
        merged.update(proj["skills"])
        r = router.route("stop wrapping the dashboard sections in a card",
                         agent="builder", reg={"skills": merged})
        assert "project/anti-card" in r["loaded"], r["loaded"]

        r2 = router.route("tune the slow postgres query on the reports endpoint",
                          agent="builder", reg={"skills": merged})
        assert "project/postgres-tuning" in r2["loaded"], r2["loaded"]
        assert "builder/backend-engineering" in r2["loaded"], "OS skills still route"
    finally:
        rm(d)


def test_status_and_doctor_report_the_discovery():
    d = _project()
    try:
        inst = installer.Install(d, quiet=True)
        inst.install()
        assert inst.status()["project_skills_discovered"] >= 3
        detail = [c for c in inst.doctor()["checks"] if c["check"] == "skill registry"][0]
        assert "project skills discovered" in detail["detail"], detail
        assert inst.doctor()["ok"]
    finally:
        rm(d)


def test_inferred_triggers_lose_to_curated_ones():
    """'Design, write and run tests' must not make a test skill win a redesign."""
    os_reg = registry.load(os.path.join(PAYLOAD, "skills", "registry.json"))
    proj = registry.scan_project(os.path.join(os.path.dirname(PAYLOAD), "tests", "fixtures"))
    merged = dict(os_reg["skills"])
    merged["project/testing"] = {
        "name": "project/testing", "description": "Design, write and run tests",
        "path": "x", "priority": 4, "source": "project", "agents": [],
        "domains": ["testing", "visual"],
        "triggers": ["design", "testing", "tests", "write"],
        "dependencies": [], "conflicts": [],
    }
    scores, _why = router.score("redesign the dashboard visual hierarchy", "builder",
                                {"skills": merged})
    assert scores["builder/design-taste"] > scores["project/testing"] * 2, \
        (scores["builder/design-taste"], scores["project/testing"])


def test_a_retired_project_skill_is_not_routable():
    """A project may retire a skill from ROUTING without deleting it.

    myjeweler kept 21 broad predecessors — `repair`, `testing`, `frontend-design`
    — de-routed so they could not compete with the granular skill that now owns
    that ground. Their opt-out was a YAML COMMENT, which this scanner cannot
    see, so they were indexed and outranked the real skill: routing "fix the
    failing authentication tests" to `project/repair` and `project/testing`
    while `repairer/systematic-debugging` never loaded.
    """
    from runtime import registry

    d = tmpdir()
    try:
        def skill(name, extra=""):
            write(os.path.join(d, name, "SKILL.md"),
                  "---\nname: %s\ndescription: debugging and repair of failing tests\n%s---\n\nbody %s\n"
                  % (name, extra, "word " * 60))

        skill("live-one")
        skill("explicit-optout", "routable: false\n")
        skill("comment-optout",
              "# Not routable since 2026-08-30: superseded for ROUTING by debugging.\n")

        got = registry.scan_project(d)
        names = set(got)
        assert "project/live-one" in names, names
        assert "project/explicit-optout" not in names, "routable:false was indexed"
        assert "project/comment-optout" not in names, "the prose marker was ignored"
    finally:
        rm(d)


def test_a_project_skill_honours_its_own_agent_declaration():
    """A project skill that names its agent must be filtered like a vetted one.

    The scanner hardcoded `agents: []`, and the router's filter reads
    `if agent and meta.get("agents") and agent not in meta["agents"]` — an empty
    list is FALSY, so the filter was skipped entirely and every project skill
    was offered to every agent. Measured in the field: a tester and a researcher
    were each offered six image-generation and visual-design skills for a
    redesign task.

    Declaring nothing still means any agent. That is a reasonable default; it
    just has to be the skill's choice, not the scanner's.
    """
    from runtime import registry

    d = tmpdir()
    try:
        def skill(name, extra=""):
            write(os.path.join(d, name, "SKILL.md"),
                  "---\nname: %s\ndescription: visual polish for landing pages\n%s---\n\n%s\n"
                  % (name, extra, "word " * 60))

        skill("declares-one", "agent: builder\n")
        skill("declares-list", "agents: [builder, reviewer]\n")
        skill("declares-any", "agent: any\n")
        skill("declares-nothing")

        got = registry.scan_project(d)
        assert got["project/declares-one"]["agents"] == ["builder"], got["project/declares-one"]
        assert got["project/declares-list"]["agents"] == ["builder", "reviewer"]
        assert got["project/declares-any"]["agents"] == [], "'any' must mean unfiltered"
        assert got["project/declares-nothing"]["agents"] == [], "undeclared means unfiltered"

        # and the filter actually bites: a builder-only skill is not offered
        # to a researcher
        reg = {"skills": got}
        loaded = registry and None
        from runtime import router
        picked = router.route("visual polish for landing pages",
                              agent="researcher", reg=reg)["loaded"]
        assert "project/declares-one" not in picked, picked
        picked = router.route("visual polish for landing pages",
                              agent="builder", reg=reg)["loaded"]
        assert "project/declares-one" in picked, picked
    finally:
        rm(d)
