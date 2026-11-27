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
        assert queue.claim(con)["id"] == a
        assert queue.claim(other)["id"] == b
        assert queue.claim(con) is None
        assert queue.get(con, a)["status"] == "RUNNING"
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
        assert queue.add(con, "next one") == 1 or queue.stats(con)["total"] == 1
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
        # agents outside the roster and sessions with no plan are not touched
        assert _agent(root, "S", subagent_type="Explore", prompt="x") is None
        assert _agent(root, "NOPLAN", subagent_type="aos-tester", prompt="x") is None
    finally:
        rm(d)
