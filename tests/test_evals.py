import json
import os

from helpers import rm, tmpdir, write
from runtime import evals


def test_shipped_eval_scores_100_on_its_own_payload():
    res = evals.run(evals.load_cases())
    assert res["total"] >= 30, res["total"]
    assert res["score"] == 100.0, res["failures"]


def test_a_wrong_expectation_lowers_the_score_and_is_named():
    bad = {"id": "bad", "kind": "risk", "prompt": "fix a typo in the footer",
           "min": "critical", "max": "critical"}
    res = evals.run([bad])
    assert res["score"] == 0.0
    assert res["failures"][0]["id"] == "bad"


def test_each_case_kind_is_checked():
    cases = [
        {"id": "r", "kind": "route", "prompt": "the checkout endpoint is slow, p95 is 2 seconds",
         "must": [["builder/performance"]], "mustnot": []},
        {"id": "k", "kind": "risk", "prompt": "issue a refund through stripe",
         "min": "high", "max": "critical"},
        {"id": "d", "kind": "delegate", "prompt": "rename the variable", "mode": "single",
         "delegate": False},
    ]
    res = evals.run(cases)
    assert res["by_kind"] == {"route": [1, 1], "risk": [1, 1], "delegate": [1, 1]}, res


def test_unknown_kind_fails_closed():
    res = evals.run([{"id": "x", "kind": "vibes", "prompt": "anything"}])
    assert res["score"] == 0.0 and "unknown kind" in res["failures"][0]["why"]


def test_baseline_regression_is_detected():
    d = tmpdir()
    try:
        path = os.path.join(d, "baseline.json")
        evals.save_baseline({"score": 90.0, "passed": 9, "total": 10}, path)
        assert evals.compare({"score": 80.0}, path)["regressed"] is True
        assert evals.compare({"score": 95.0}, path)["regressed"] is False
        assert evals.compare({"score": 95.0}, os.path.join(d, "none.json"))["baseline"] is None
    finally:
        rm(d)


def test_traces_are_capped_and_read_newest_first():
    d = tmpdir()
    try:
        path = os.path.join(d, "traces.jsonl")
        for i in range(12):
            evals.record_trace({"prompt": "p%d" % i, "risk": "normal"}, path=path, cap=10)
        got = evals.traces(path=path)
        assert len(got) == 10 and got[0]["prompt"] == "p11", [t["prompt"] for t in got]
    finally:
        rm(d)


def test_label_turns_a_trace_into_a_case_that_runs():
    d = tmpdir()
    try:
        lab = os.path.join(d, "labeled.jsonl")
        trace = {"prompt": "issue a refund through stripe", "risk": "high", "mode": "single",
                 "delegate": True, "skills": []}
        case = evals.label(trace, "risk", path=lab, min="high", max="critical")
        assert case["kind"] == "risk" and case["prompt"] == trace["prompt"]
        cases = evals.load_cases(cases_path=os.path.join(d, "none.json"), labeled_path=lab)
        assert evals.run(cases)["score"] == 100.0
        for kind, kw in (("route", {}), ("risk", {"min": None, "max": "high"}),
                         ("delegate", {"delegate": None})):
            try:
                evals.label(trace, kind, path=lab, **kw)
                raise AssertionError("%s label with no expectation must be refused" % kind)
            except ValueError:
                pass
    finally:
        rm(d)


def test_labeled_cases_from_state_are_included():
    d = tmpdir()
    try:
        lab = os.path.join(d, "labeled.jsonl")
        write(lab, json.dumps({"id": "lab1", "kind": "risk", "prompt": "delete every row of the users table in production",
                               "min": "high", "max": "critical"}) + "\n")
        ids = [c["id"] for c in evals.load_cases(labeled_path=lab)]
        assert "lab1" in ids
    finally:
        rm(d)


def test_tune_keeps_a_change_only_when_the_score_rises_and_logs_each_try():
    import shutil
    from runtime import paths
    d = tmpdir()
    try:
        cfg = os.path.join(d, "risk.json")
        shutil.copy(paths.config("risk.json"), cfg)
        log = os.path.join(d, "tune.jsonl")
        cases = [c for c in evals.load_cases() if c["kind"] == "risk"]
        # a broken threshold: nothing reaches "high", so the high cases fail
        res = evals.tune(cases, "risk.high", start=50, config_path=cfg, log_path=log, apply=True)
        assert res["kept"] and res["best"] != 50 and res["best_score"] > res["base_score"], res
        assert json.load(open(cfg))["level_thresholds"]["high"] == res["best"]
        assert len(open(log).read().splitlines()) == len(res["tries"]) >= 4
        # already-good config: nothing beats it, nothing is written
        before = open(cfg).read()
        res = evals.tune(cases, "risk.high", config_path=cfg, log_path=log, apply=True)
        assert not res["kept"] and open(cfg).read() == before, res
        # dry run never writes
        res = evals.tune(cases, "risk.high", start=50, config_path=cfg, log_path=log)
        assert res["kept"] and open(cfg).read() == before
    finally:
        rm(d)
