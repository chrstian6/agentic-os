import os

from helpers import PAYLOAD, rm, tmpdir
from runtime import artifacts, workflow


def test_plan_scales_with_difficulty():
    trivial = workflow.plan("rename the variable")
    assert trivial["delegate"] is False, trivial["direct_execution_reason"]
    assert len(trivial["stages"]) == 1

    complex_ = workflow.plan("migrate the authentication system to oauth across "
                             "the frontend and backend with a schema migration", file_count=20)
    assert complex_["delegate"] is True
    agents = [s["agent"] for s in complex_["stages"]]
    assert "reviewer" in agents and "tester" in agents, agents
    assert complex_["test_first"] is True


def test_plan_assigns_model_tiers():
    p = workflow.plan("design and implement a distributed rate limiter with a race "
                      "condition fix and schema migration in production", file_count=25)
    tiers = {s["agent"]: s["tier"] for s in p["stages"]}
    assert tiers.get("reviewer") == "DEEP", tiers
    assert all(s["model"] for s in p["stages"])


def test_repair_is_bounded_and_forces_strategy_change():
    assert workflow.repair_decision(0, 3, False)["action"] == "REPAIR"
    assert workflow.repair_decision(2, 3, True)["action"] == "CHANGE_STRATEGY"
    assert workflow.repair_decision(3, 3, False)["action"] == "ESCALATE"


def test_completion_audit_rejects_false_completion():
    task = {"id": 1, "title": "add csv export"}
    arts = [{"agent": "builder", "status": "ok", "summary": "added the csv exporter",
             "tests_run": 3, "tests_failed": 1, "evidence": ["ran pytest"], "remaining_work": []}]
    res = workflow.completion_audit(task, arts, ["csv exporter returns a header row"])
    assert res["verdict"] != "COMPLETED", res
    assert any("failing tests" in f for f in res["findings"]), res


def test_completion_audit_requires_evidence_per_criterion():
    task = {"id": 1, "title": "add csv export"}
    arts = [{"agent": "builder", "status": "ok", "summary": "added the exporter",
             "tests_run": 3, "tests_failed": 0, "evidence": ["pytest -q -> 3 passed"],
             "remaining_work": []}]
    res = workflow.completion_audit(task, arts, ["exporter streams for large tables"])
    assert res["verdict"] != "COMPLETED"
    assert any("no evidence" in f for f in res["findings"]), res


def test_completion_audit_passes_with_full_evidence():
    task = {"id": 1, "title": "add csv export"}
    arts = [{"agent": "builder", "status": "ok", "summary": "csv exporter streams rows",
             "tests_run": 4, "tests_failed": 0, "remaining_work": [],
             "evidence": ["pytest -q tests/test_export.py -> 4 passed",
                          "exporter streams for large tables verified with 50k rows"]}]
    res = workflow.completion_audit(task, arts, ["exporter streams for large tables"])
    assert res["verdict"] == "COMPLETED", res


def test_artifact_contract_is_enforced():
    d = tmpdir()
    try:
        artifacts.write(1, "builder", {"status": "ok", "summary": "done",
                                       "tests_run": 2, "tests_passed": 2}, root=d)
        for bad in ({"summary": "no status"},
                    {"status": "ok", "summary": "lying", "tests_failed": 2},
                    {"status": "ok", "summary": "lying", "remaining_work": ["half of it"]},
                    {"status": "great", "summary": "invalid status"}):
            try:
                artifacts.write(2, "builder", bad, root=d)
                raise AssertionError("accepted invalid artifact: %s" % bad)
            except ValueError:
                pass
        got = artifacts.read(1, "builder", root=d)
        assert got["status"] == "ok" and got["agent"] == "builder"
    finally:
        rm(d)


def test_context_pack_drops_transcripts():
    pack = artifacts.context_pack({"id": 1, "title": "t", "body": "b"},
                                  [{"agent": "analyst", "status": "ok", "summary": "spec",
                                    "evidence": ["x" * 5000]}])
    assert "x" * 100 not in str(pack), "evidence blobs must not be forwarded wholesale"
    assert pack["prior"][0]["summary"] == "spec"


def test_plan_names_the_installed_agent_not_the_bare_role():
    """Every stage must name something a Task call can actually dispatch.

    The two spellings drifted: the UserPromptSubmit hook prefixed `aos-` inline
    while `aos plan` emitted the bare role, so the JSON people script against
    named agents that do not exist on disk. A host guard that reads
    `.claude/agents/` refuses those, which turns a plan into a dead end.

    The bare role stays as `agent` because router.route and models.route look up
    on it; `dispatch` is what you type.
    """
    plan = workflow.plan("migrate the authentication system to oauth across "
                         "the frontend and backend with a schema migration",
                         file_count=20)
    assert plan["stages"], "no stages planned — nothing below proves anything"
    for stage in plan["stages"]:
        assert stage["dispatch"] == "aos-" + stage["agent"], stage
        # the definition must exist in the payload, or the guard refuses it
        definition = os.path.join(PAYLOAD, "agents", stage["dispatch"] + ".md")
        assert os.path.isfile(definition), "no agent definition: %s" % definition


def test_classify_exposes_dispatch_names_for_every_depth():
    from runtime import classify

    for task, files in (("rename the variable", 0),
                        ("migrate the authentication system to oauth across the "
                         "frontend and backend with a schema migration", 20)):
        c = classify.classify(task, files)
        assert c["agents"], "no agents at this depth"
        assert c["dispatch"] == ["aos-" + a for a in c["agents"]], c
    # idempotent: an already-prefixed name is not double-prefixed
    assert classify.dispatch_name("aos-builder") == "aos-builder"
