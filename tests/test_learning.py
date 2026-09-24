"""Learning must change future decisions, be reversible, and never weaken safety."""
import os

from helpers import PAYLOAD, rm, tmpdir
from runtime import classify, learning, metrics, policy, registry, router

REG = registry.load(os.path.join(PAYLOAD, "skills", "registry.json"))


def _stores():
    d = tmpdir()
    return learning.connect(os.path.join(d, "l.db")), metrics.connect(os.path.join(d, "m.db")), d


def test_observations_become_patterns_and_hypotheses():
    lcon, _m, d = _stores()
    try:
        for task_id in range(3):
            learning.observe(lcon, task_id, "missing_skill", "css|builder/design-taste")
        assert not learning.hypothesize(lcon, min_count=4), "should need more evidence"
        cands = learning.hypothesize(lcon, min_count=3)
        assert cands and cands[0]["kind"] == "skill_boost", cands
        assert cands[0]["key"] == "builder/design-taste"
    finally:
        rm(d)


def test_full_champion_challenger_cycle_changes_behaviour():
    lcon, mcon, d = _stores()
    try:
        task = "tweak the css on the pricing page"
        before = router.route(task, agent="builder", reg=REG, policies=learning.active(lcon))
        assert "builder/design-taste" not in before["loaded"], before["loaded"]

        # OBSERVE -> PATTERN -> HYPOTHESIS
        for i in range(3):
            learning.observe(lcon, i, "missing_skill", "css|builder/design-taste")
        cand = learning.hypothesize(lcon)[0]

        # CANDIDATE POLICY
        res = learning.propose(lcon, cand["kind"], cand["key"], cand["scope"], cand["value"],
                               cand["reason"], cand["evidence"])
        assert res["accepted"], res
        pid = res["policy_id"]
        assert learning.active(lcon) == [], "a challenger must not be in force yet"

        # EXPERIMENT + MEASURE
        for _ in range(4):
            metrics.record(mcon, 1, arm="champion", success=0.5, first_pass_success=0.2,
                           repairs=1.0, tokens=1000)
            metrics.record(mcon, 2, arm="challenger", policy_id=pid, success=1.0,
                           first_pass_success=0.9, repairs=0.1, tokens=1050)
        cmp_ = learning.compare(mcon, pid)
        assert cmp_["decision"] == "promote", cmp_

        # PROMOTE -> FUTURE APPLICATION
        assert learning.promote(lcon, pid, cmp_)["promoted"]
        pols = learning.active(lcon)
        assert len(pols) == 1 and pols[0]["status"] == "champion"
        after = router.route(task, agent="builder", reg=REG, policies=pols)
        assert "builder/design-taste" in after["loaded"], (before["loaded"], after["loaded"])

        # ROLLBACK -> behaviour reverts
        learning.rollback(lcon, pid, "test rollback")
        reverted = router.route(task, agent="builder", reg=REG, policies=learning.active(lcon))
        assert "builder/design-taste" not in reverted["loaded"], reverted["loaded"]
        hist = [h for h in learning.history(lcon) if h["id"] == pid][0]
        assert hist["status"] == "rolled_back" and hist["reason"] == "test rollback"
        assert hist["evidence"] and hist["created_at"] and hist["decided_at"]
    finally:
        rm(d)


def test_weak_challenger_is_rejected():
    lcon, mcon, d = _stores()
    try:
        pid = learning.propose(lcon, "skill_boost", "builder/motion", "form", 3.0,
                               "hunch")["policy_id"]
        for _ in range(4):
            metrics.record(mcon, 1, arm="champion", success=1.0, repairs=0.0, tokens=1000)
            metrics.record(mcon, 2, arm="challenger", policy_id=pid, success=0.6,
                           repairs=2.0, tokens=3000)
        cmp_ = learning.compare(mcon, pid)
        assert cmp_["decision"] == "reject", cmp_
        learning.reject(lcon, pid, "worse on quality and cost")
        assert learning.active(lcon) == []
    finally:
        rm(d)


def test_insufficient_evidence_blocks_promotion():
    lcon, mcon, d = _stores()
    try:
        pid = learning.propose(lcon, "level_bump", "auth", "auth", 1, "seen twice")["policy_id"]
        metrics.record(mcon, 1, arm="champion", success=1.0)
        metrics.record(mcon, 2, arm="challenger", policy_id=pid, success=1.0)
        assert learning.compare(mcon, pid)["decision"] == "insufficient_evidence"
    finally:
        rm(d)


def test_safety_floor_rejects_unsafe_candidates():
    lcon, _m, d = _stores()
    try:
        unsafe = [
            ("skill_boost", "disable the guard for rm -rf", "", 5.0),
            ("depth_floor", "skip tests for hotfixes", "hotfix", 1),
            ("level_bump", "auto-approve deploys without confirmation", "deploy", 1),
            ("skill_suppress", "builder/security", "backend", 3.0),
            ("guard_disable", "git.force_push", "", 1),
            ("depth_floor", "normal", "x", 0),
            ("level_bump", "trivial", "x", -1),
        ]
        for kind, key, scope, value in unsafe:
            res = learning.propose(lcon, kind, key, scope, value, "measured faster")
            assert not res["accepted"], "unsafe candidate accepted: %s %s" % (kind, key)
        assert learning.active(lcon) == [] and learning.challengers(lcon) == []
        rejected = [h for h in learning.history(lcon) if h["status"] == "rejected"]
        assert len(rejected) == len(unsafe)
        assert all(h["reason"].startswith("SAFETY FLOOR") for h in rejected)
    finally:
        rm(d)


def test_safety_floor_also_applies_at_promotion_time():
    lcon, mcon, d = _stores()
    try:
        pid = learning.propose(lcon, "skill_boost", "builder/motion", "ui", 2.0, "ok")["policy_id"]
        # tamper with the stored policy the way a compromised learner might
        lcon.execute("UPDATE policies SET key='skip required tests' WHERE id=?", (pid,))
        lcon.commit()
        res = learning.promote(lcon, pid)
        assert not res["promoted"], res
        assert learning.active(lcon) == []
    finally:
        rm(d)


def test_policies_bias_classification_and_depth():
    pols = [{"kind": "level_bump", "key": "migration", "scope": "migration", "value": 1},
            {"kind": "depth_floor", "key": "migration", "scope": "migration", "value": 4}]
    base = classify.classify("write a small data migration")
    biased = classify.classify("write a small data migration", policies=pols)
    assert biased["difficulty"]["level"] > base["difficulty"]["level"]
    assert biased["depth"] >= 4
    assert policy.apply_depth(1, "unrelated task", pols) == 1


def test_cycle_closes_the_loop_from_recorded_evidence():
    """Hooks record; `aos learn cycle` decides. No manual proposing required."""
    lcon, mcon, d = _stores()
    try:
        for i in range(3):
            learning.observe(lcon, i, "missing_skill", "css|builder/design-taste")
        first = learning.cycle(lcon, mcon)
        assert first["proposed"], first
        pid = first["proposed"][0]["policy_id"]
        assert first["pending"] and first["pending"][0]["decision"] == "insufficient_evidence"
        assert learning.active(lcon) == [], "nothing may be promoted without runs"

        # the prompt hook samples arms; simulate the runs it would record
        for _ in range(4):
            metrics.record(mcon, None, arm="champion", success=0.5, repairs=1.0, tokens=1000)
            metrics.record(mcon, None, arm="challenger", policy_id=pid, success=1.0,
                           repairs=0.0, tokens=1010)
        second = learning.cycle(lcon, mcon)
        assert any(x["decision"] == "promote" for x in second["decisions"]), second
        assert [p["key"] for p in learning.active(lcon)] == ["builder/design-taste"]

        # idempotent: a second cycle does not re-propose what is already in force
        third = learning.cycle(lcon, mcon)
        assert third["proposed"] == [], third
    finally:
        rm(d)


def test_cycle_never_proposes_an_unsafe_candidate():
    lcon, mcon, d = _stores()
    try:
        for i in range(3):
            learning.observe(lcon, i, "unused_skill", "backend|builder/security")
        rep = learning.cycle(lcon, mcon)
        assert rep["proposed"] == [], rep
        assert rep["rejected_unsafe"], rep
        assert "safety" in rep["rejected_unsafe"][0]["reason"].lower()
    finally:
        rm(d)


def test_cycle_dry_run_does_not_promote():
    lcon, mcon, d = _stores()
    try:
        pid = learning.propose(lcon, "skill_boost", "builder/motion", "ui", 3.0, "x")["policy_id"]
        for _ in range(4):
            metrics.record(mcon, None, arm="champion", success=0.2)
            metrics.record(mcon, None, arm="challenger", policy_id=pid, success=1.0)
        rep = learning.cycle(lcon, mcon, auto_promote=False)
        assert learning.active(lcon) == [], rep
    finally:
        rm(d)
