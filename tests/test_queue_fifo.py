"""Queue integrity: FIFO order, no dropped tasks, one claimant per task, right model per task."""
import os
import sqlite3

from helpers import rm, tmpdir
from runtime import queue, workflow
from test_context import _fresh, _run

HEAVY = ("migrate the authentication system to oauth across the frontend and backend with a "
         "schema migration, rewrite the session store and update every api route")


def _db():
    d = tmpdir()
    return os.path.join(d, "q.db"), d


def test_claim_takes_the_oldest_ready_task_and_never_the_same_twice():
    path, d = _db()
    try:
        con = queue.connect(path)
        a = queue.add(con, "first job")
        b = queue.add(con, "second job")
        other = queue.connect(path)          # a second session on the same queue
        stale = queue.ready(con)             # session 1 reads the queue...
        assert queue.claim(other)["id"] == a  # ...session 2 claims the head first
        assert queue._take(con, stale)["id"] == b, "the compare-and-set must skip a taken task"
        assert queue.claim(con) is None
        assert queue.get(con, a)["status"] == "RUNNING"
    finally:
        rm(d)


def test_cancelled_then_completed_prerequisite_releases_its_dependent():
    path, d = _db()
    try:
        con = queue.connect(path)
        a = queue.add(con, "prepare fixtures")
        b = queue.add(con, "run the import", depends_on=[a])
        queue.set_status(con, a, "CANCELLED")
        queue.set_status(con, a, "COMPLETED")        # straight back, no reopen step
        assert b in [t["id"] for t in queue.ready(con)], queue.get(con, b)
    finally:
        rm(d)


def test_dependent_stays_blocked_while_another_prerequisite_is_cancelled():
    path, d = _db()
    try:
        con = queue.connect(path)
        a = queue.add(con, "prepare fixtures")
        c = queue.add(con, "prepare data")
        b = queue.add(con, "run the import", depends_on=[a, c])
        queue.set_status(con, a, "CANCELLED")
        queue.set_status(con, c, "CANCELLED")
        queue.set_status(con, c, "QUEUED", "reopened")     # reopen in the other order
        assert queue.get(con, b)["status"] == "BLOCKED"      # a is still cancelled
        queue.set_status(con, a, "QUEUED", "reopened")
        queue.set_status(con, a, "COMPLETED")
        queue.set_status(con, c, "COMPLETED")
        assert b in [t["id"] for t in queue.ready(con)], queue.get(con, b)
    finally:
        rm(d)


def test_failed_prerequisite_does_not_requeue_running_work():
    path, d = _db()
    try:
        con = queue.connect(path)
        a = queue.add(con, "prepare fixtures")
        b = queue.add(con, "run the import", depends_on=[a])
        queue.set_status(con, a, "COMPLETED")
        assert queue.claim(con)["id"] == b
        queue.set_status(con, a, "FAILED", "rework")
        assert queue.get(con, b)["status"] == "RUNNING"
    finally:
        rm(d)


def test_claim_never_restarts_a_paused_task():
    path, d = _db()
    try:
        con = queue.connect(path)
        a = queue.add(con, "paused job")
        b = queue.add(con, "live job")
        queue.set_status(con, a, "PAUSED")
        assert queue.claim(con)["id"] == b
        assert queue.claim(con) is None and queue.get(con, a)["status"] == "PAUSED"
    finally:
        rm(d)


def test_reopen_releases_even_after_a_later_note():
    path, d = _db()
    try:
        con = queue.connect(path)
        a = queue.add(con, "prepare fixtures")
        b = queue.add(con, "run the import", depends_on=[a])
        queue.set_status(con, a, "CANCELLED")
        queue.log(con, b, "status", "note: owner pinged")
        queue.set_status(con, a, "QUEUED", "reopened")
        queue.set_status(con, a, "COMPLETED")
        assert b in [t["id"] for t in queue.ready(con)]
    finally:
        rm(d)


def test_claim_skips_a_task_still_waiting_on_its_dependency():
    path, d = _db()
    try:
        con = queue.connect(path)
        a = queue.add(con, "build the csv export")
        b = queue.add(con, "write release notes", depends_on=[a])
        c = queue.add(con, "unrelated chore")
        assert queue.claim(con)["id"] == a
        assert queue.claim(con)["id"] == c       # b waits, c is next in line
        queue.set_status(con, a, "COMPLETED")
        assert queue.claim(con)["id"] == b
    finally:
        rm(d)


def test_reopened_cancelled_prerequisite_releases_its_dependent():
    path, d = _db()
    try:
        con = queue.connect(path)
        a = queue.add(con, "prepare fixtures")
        b = queue.add(con, "run the import", depends_on=[a])
        queue.set_status(con, a, "CANCELLED")
        assert queue.get(con, b)["status"] == "BLOCKED"
        queue.set_status(con, a, "QUEUED", "reopened")
        queue.set_status(con, a, "COMPLETED")
        assert b in [t["id"] for t in queue.ready(con)], queue.get(con, b)
    finally:
        rm(d)


def test_manually_blocked_task_stays_blocked():
    path, d = _db()
    try:
        con = queue.connect(path)
        a = queue.add(con, "prepare fixtures")
        b = queue.add(con, "run the import", depends_on=[a])
        queue.set_status(con, b, "BLOCKED", "waiting on vendor")
        queue.set_status(con, a, "COMPLETED")
        assert queue.get(con, b)["status"] == "BLOCKED"
    finally:
        rm(d)


def test_set_status_on_unknown_task_fails_loudly():
    path, d = _db()
    try:
        con = queue.connect(path)
        try:
            queue.set_status(con, 999, "COMPLETED")
            raise AssertionError("unknown task id accepted")
        except ValueError:
            pass
        assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    finally:
        rm(d)


def test_add_with_missing_dependency_leaves_no_half_task():
    path, d = _db()
    try:
        con = queue.connect(path)
        try:
            queue.add(con, "orphan", depends_on=[42])
            raise AssertionError("missing dependency accepted")
        except (ValueError, sqlite3.IntegrityError):
            pass
        assert queue.stats(con)["total"] == 0
        assert queue.add(con, "next one") == 1, "a refused add must not burn an id"
    finally:
        rm(d)


def test_waves_keep_fifo_order_and_carry_a_model():
    path, d = _db()
    try:
        con = queue.connect(path)
        big = queue.add(con, HEAVY)
        small = queue.add(con, "fix a typo in the footer text")
        plan = workflow.queue_waves(queue.ready(con))
        units = [u for w in plan["waves"] for u in w]
        assert units[0]["tasks"][0]["id"] == big, units   # queued first, dispatched first
        assert units[1]["tasks"][0]["id"] == small
        assert all(u.get("model") in ("haiku", "sonnet", "opus") for u in units), units
    finally:
        rm(d)


def test_waves_never_let_a_small_task_overtake_an_earlier_heavy_one():
    path, d = _db()
    try:
        con = queue.connect(path)
        ids = [queue.add(con, t) for t in ("fix a typo in the footer text", HEAVY,
                                           "fix a typo in the header text", HEAVY,
                                           "fix a typo in the about text")]
        plan = workflow.queue_waves(queue.ready(con))
        order = [r["id"] for w in plan["waves"] for u in w for r in u["tasks"]]
        assert order == ids, plan
    finally:
        rm(d)


def _agent(root, sid, **ti):
    return _run(root, "pre_tool_use.py", {"session_id": sid, "tool_name": "Agent", "tool_input": ti})


def test_agent_dispatch_without_the_planned_model_is_sent_back():
    d, root = _fresh()
    try:
        _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": HEAVY})
        out = _agent(root, "S", subagent_type="aos-tester", prompt="x")
        hs = out["hookSpecificOutput"]
        assert hs["permissionDecision"] == "deny" and "model=" in hs["permissionDecisionReason"], hs
        # below the planned tier is refused too
        out = _agent(root, "S", subagent_type="aos-reviewer", prompt="x", model="haiku")
        assert out and out["hookSpecificOutput"]["permissionDecision"] == "deny", out
        # the planned model, or a stronger one, passes
        assert _agent(root, "S", subagent_type="aos-reviewer", prompt="x", model="opus") is None
        assert _agent(root, "S", subagent_type="aos-tester", prompt="x", model="opus") is None
        assert _agent(root, "S", subagent_type="aos-tester", prompt="x", model="strong") is None
        for bad in ("inherit", "fast"):         # unrankable or too weak: fail closed
            out = _agent(root, "S", subagent_type="aos-tester", prompt="x", model=bad)
            assert out and out["hookSpecificOutput"]["permissionDecision"] == "deny", (bad, out)
        # agents outside the roster and sessions with no plan are not touched
        assert _agent(root, "S", subagent_type="Explore", prompt="x") is None
        assert _agent(root, "NOPLAN", subagent_type="aos-tester", prompt="x") is None
    finally:
        rm(d)
