"""Regression tests for defects found by auditing the installation, not by a report."""
import json
import os
import subprocess
import sys
import time

from helpers import PAYLOAD, rm, tmpdir
from runtime import artifacts, models, queue


class _FakeRun(object):
    """Stands in for `claude --help`. Tests never launch the real binary: it is slow,
    it may not exist, and one hung invocation stalls the whole suite."""

    def __init__(self, sink):
        self.sink = sink
        self.stdout = "  --model  opus, sonnet, haiku\n"
        self.stderr = ""

    def __call__(self, *a, **k):
        self.sink["n"] += 1
        return self


def _stub_subprocess():
    calls = {"n": 0}
    fake = _FakeRun(calls)
    import runtime.models as m
    original = m.subprocess.run
    m.subprocess.run = fake
    return calls, original


def _restore(original):
    import runtime.models as m
    m.subprocess.run = original
    models._CACHE.clear()


def test_model_detection_is_cached_not_reshelled_per_stage():
    """One plan() spawned five `claude --help` processes - 365ms of a 419ms hook."""
    from runtime import workflow
    models._CACHE.clear()
    calls, original = _stub_subprocess()
    try:
        workflow.plan("redesign the dashboard and fix the visual hierarchy")
        first = calls["n"]
        workflow.plan("add an api endpoint for repair counts")
        assert first <= 1, "model detection must not shell out per stage (got %d)" % first
        assert calls["n"] == first, "the second plan must reuse the cache"
    finally:
        _restore(original)


def test_model_cache_expires():
    """Both tiers of the cache expire: in-process and on disk."""
    from runtime import paths
    env = os.environ.pop("AOS_AVAILABLE_MODELS", None)   # the env override wins by design
    disk = paths.state("models-cache.json")
    saved = open(disk).read() if os.path.exists(disk) else None
    models._CACHE.clear()
    models._CACHE.update({"models": ["opus"], "at": time.time() - models.CACHE_TTL_S - 1})
    if saved is not None:
        os.remove(disk)
    calls, original = _stub_subprocess()
    try:
        got = models.available_models()
        assert calls["n"] >= 1, "a stale cache must be refreshed"
        assert got == ["opus", "sonnet", "haiku"], got
    finally:
        _restore(original)
        if env is not None:
            os.environ["AOS_AVAILABLE_MODELS"] = env
        if saved is not None:
            open(disk, "w").write(saved)
        elif os.path.exists(disk):
            os.remove(disk)


def test_a_cancelled_prerequisite_does_not_park_its_dependents_silently():
    d = tmpdir()
    try:
        con = queue.connect(os.path.join(d, "q.db"))
        a = queue.add(con, "build the exporter")
        b = queue.add(con, "test the exporter", depends_on=[a])
        queue.set_status(con, a, "CANCELLED")

        assert queue.get(con, b)["status"] == "BLOCKED", queue.get(con, b)
        blockers = queue.blockers(con, b)
        assert blockers and blockers[0]["permanent"] is True, blockers
        events = [r["detail"] for r in con.execute(
            "SELECT detail FROM events WHERE task_id=?", (b,))]
        assert any("cancelled" in e for e in events), events
    finally:
        rm(d)


def test_a_failed_prerequisite_still_only_parks():
    """FAILED is recoverable - it must park, not permanently block."""
    d = tmpdir()
    try:
        con = queue.connect(os.path.join(d, "q.db"))
        a = queue.add(con, "build the exporter")
        b = queue.add(con, "test the exporter", depends_on=[a])
        queue.set_status(con, a, "FAILED")
        assert queue.get(con, b)["status"] == "WAITING_DEPENDENCY"
        assert queue.blockers(con, b)[0]["permanent"] is False
        queue.set_status(con, a, "COMPLETED")
        assert b in [t["id"] for t in queue.ready(con)]
    finally:
        rm(d)


def test_context_pack_respects_the_budget_it_advertises():
    """It returned 20191 chars when asked for 2000."""
    prior = [{"agent": "builder", "status": "ok", "summary": "s" * 20000,
              "files_changed": ["a"] * 50, "risks": ["r"] * 20, "evidence": []},
             {"agent": "tester", "status": "ok", "summary": "t" * 8000, "evidence": []}]
    pack = artifacts.context_pack({"id": 1, "title": "t", "body": "b" * 5000}, prior,
                                  max_chars=2000)
    assert len(json.dumps(pack)) <= 2000, len(json.dumps(pack))
    assert pack["prior"][0]["summary"], "trimming must not empty the field"
    assert [p["agent"] for p in pack["prior"]] == ["builder", "tester"], "shape survives"
    assert pack["task"]["id"] == 1


def test_small_packs_are_untouched():
    prior = [{"agent": "builder", "status": "ok", "summary": "did the thing",
              "files_changed": ["app/x.ts"], "evidence": []}]
    pack = artifacts.context_pack({"id": 1, "title": "t", "body": "b"}, prior)
    assert pack["prior"][0]["files_changed"] == ["app/x.ts"]
    assert pack["prior"][0]["summary"] == "did the thing"


def test_event_log_stays_bounded():
    d = tmpdir()
    try:
        root = os.path.join(d, "aos")
        os.makedirs(os.path.join(root, "state"))
        sys.path.insert(0, os.path.join(PAYLOAD, "hooks"))
        import post_tool_use  # noqa: E402
        path = os.path.join(root, "state", "events.jsonl")
        with open(path, "w") as fh:
            fh.write(("{\"tool\": \"Bash\", \"pad\": \"%s\"}\n" % ("x" * 250)) * 3000)
        post_tool_use._rotate(path)
        with open(path) as fh:
            kept = fh.readlines()
        assert len(kept) == post_tool_use.KEEP_EVENTS, len(kept)
        assert json.loads(kept[-1])["tool"] == "Bash", "rotation must keep valid records"
    finally:
        rm(d)
