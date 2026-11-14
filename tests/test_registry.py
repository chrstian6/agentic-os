"""The distribution must ship real skills, not placeholders."""
import json
import os

from helpers import PAYLOAD
from runtime import registry

REQUIRED = [
    "shared/evidence", "shared/verification", "shared/unlazy", "shared/uncertainty",
    "shared/safe-tool-use", "shared/context-minimization", "shared/artifact-handoff",
    "shared/failure-recovery",
    "builder/frontend-engineering", "builder/backend-engineering",
    "builder/component-architecture", "builder/accessibility", "builder/responsive-design",
    "builder/performance", "builder/security", "builder/design-taste", "builder/anti-ai-slop",
    "builder/interaction-design", "builder/motion", "builder/frontend-testing",
    "builder/existing-project-redesign",
    "researcher/technical-research", "researcher/documentation-analysis",
    "researcher/source-evaluation", "researcher/uncertainty-reduction",
    "tester/test-driven-development", "tester/test-design", "tester/unit-testing",
    "tester/integration-testing", "tester/e2e-testing", "tester/regression-testing",
    "tester/edge-case-analysis", "tester/failure-analysis", "tester/verification",
    "repairer/systematic-debugging", "repairer/root-cause-analysis",
    "repairer/regression-repair", "repairer/failure-analysis", "repairer/verification",
    "reviewer/code-review", "reviewer/requirements-review", "reviewer/adversarial-review",
    "reviewer/security-review", "reviewer/completion-audit", "reviewer/quality-review",
    "reviewer/scale-review",
]


def _scan():
    return registry.scan(os.path.join(PAYLOAD, "skills"))


def test_all_required_skills_exist():
    have = _scan()
    missing = [s for s in REQUIRED if s not in have]
    assert not missing, "missing skills: %s" % missing


def test_no_placeholder_skills():
    for name, meta in _scan().items():
        assert meta["words"] > 200, "%s has only %d words - placeholder?" % (name, meta["words"])
        assert meta["description"], name
        assert meta["triggers"] or meta["domains"], "%s is unroutable" % name


def test_dependencies_and_conflicts_resolve():
    reg = {"skills": _scan()}
    assert registry.validate(reg) == []


def test_registry_file_matches_disk():
    reg = registry.load(os.path.join(PAYLOAD, "skills", "registry.json"))
    assert set(reg["skills"]) == set(_scan()), "registry.json is stale"


def test_some_skills_have_executable_tests():
    tested = [n for n, m in _scan().items() if m["has_tests"]]
    assert len(tested) >= 2, tested


def test_agents_are_valid():
    d = os.path.join(PAYLOAD, "agents")
    names = sorted(f for f in os.listdir(d) if f.endswith(".md"))
    assert len(names) == 9, names
    for n in names:
        text = open(os.path.join(d, n)).read()
        meta, body = registry.parse_frontmatter(text)
        assert meta.get("name") == n[:-3], meta
        assert meta.get("description"), n
        assert meta.get("model") in ("opus", "sonnet", "haiku"), meta
        assert len(body.split()) > 150, "%s is a placeholder agent" % n
        assert "Output contract" in body or "output contract" in body, n
        # bounded by permission, not by prose: tools: is what the engine enforces
        assert meta.get("tools"), "%s has no tools: frontmatter - it inherits everything" % n
        assert "Agent" not in meta["tools"] and "Task" not in meta["tools"], \
            "%s can spawn subagents - nesting must stay bounded" % n
        if n in ("aos-reviewer.md", "aos-analyst.md", "aos-researcher.md",
                 "aos-design-critic.md", "aos-router.md", "aos-orchestrator.md"):
            assert "Write" not in meta["tools"] and "Edit" not in meta["tools"], \
                "%s must not write source" % n


def test_every_loaded_skill_path_is_openable():
    """A path a caller cannot open is worse than no path.

    scan() writes OS skill paths relative to the install root (portable file,
    stable hash) and scan_project() writes absolute ones (a project skill lives
    outside that root). Consumers could not tell which they held, and most did
    not try: `aos route` emitted "skills/builder/design-taste/SKILL.md", which
    resolves to nothing from a project root, and `aos skills show` returned an
    empty body. Only the UserPromptSubmit hook worked, because it joined the
    root itself.

    An agent told to read a path that does not exist goes looking elsewhere.
    """
    from runtime import registry, router

    reg = router.load_registry()
    skills = reg["skills"]
    assert len(skills) > 10, "registry too small to prove anything: %d" % len(skills)

    checked = 0
    for name, meta in skills.items():
        p = meta.get("path")
        assert p, "%s has no path" % name
        assert os.path.isabs(p), "%s path is not absolute: %s" % (name, p)
        assert os.path.isfile(p), "%s path does not exist: %s" % (name, p)
        checked += 1
    assert checked == len(skills)

    # and the file on disk stays portable — resolution happens on load, so the
    # installed registry.json is unchanged and its hash stays stable
    raw = json.load(open(os.path.join(PAYLOAD, "skills", "registry.json")))
    sample = next(iter(raw["skills"].values()))
    assert not os.path.isabs(sample["path"]), \
        "registry.json now stores an absolute path; it must stay portable"
    assert registry  # imported for the reader's benefit
