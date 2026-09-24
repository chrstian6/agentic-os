import os

from helpers import rm, tmpdir
from runtime import queue


def _db():
    d = tmpdir()
    return os.path.join(d, "q.db"), d


def test_dependency_ordering_and_isolation():
    path, d = _db()
    try:
        con = queue.connect(path)
        a = queue.add(con, "Build the CSV serializer")
        b = queue.add(con, "Update the docs")
        c = queue.add(con, "Test the CSV serializer", depends_on=[a])
        dd = queue.add(con, "Fix an unrelated typo")

        ready = [t["id"] for t in queue.ready(con)]
        assert a in ready and b in ready and dd in ready, ready
        assert c not in ready, "C must wait for A"

        # A fails: C keeps waiting, B and D are untouched
        queue.set_status(con, a, "FAILED", "compile error")
        ready = [t["id"] for t in queue.ready(con)]
        assert b in ready and dd in ready, "unrelated work must continue"
        assert c not in ready
        assert queue.get(con, c)["status"] == "WAITING_DEPENDENCY"

        # A is repaired: C becomes runnable
        queue.set_status(con, a, "COMPLETED")
        assert c in [t["id"] for t in queue.ready(con)]
    finally:
        rm(d)


def test_inferred_dependency():
    path, d = _db()
    try:
        con = queue.connect(path)
        build = queue.add(con, "build the export pipeline")
        test = queue.add(con, "test the export pipeline")
        assert [b["id"] for b in queue.blockers(con, test)] == [build]
    finally:
        rm(d)


def test_state_survives_reconnect():
    path, d = _db()
    try:
        con = queue.connect(path)
        tid = queue.add(con, "long running work")
        queue.set_status(con, tid, "RUNNING")
        con.close()
        con2 = queue.connect(path)
        assert queue.get(con2, tid)["status"] == "RUNNING"
        assert queue.stats(con2)["total"] == 1
    finally:
        rm(d)


def test_all_lifecycle_statuses_accepted():
    path, d = _db()
    try:
        con = queue.connect(path)
        tid = queue.add(con, "x")
        for s in queue.STATUSES:
            queue.set_status(con, tid, s)
        try:
            queue.set_status(con, tid, "NOT_A_STATUS")
            raise AssertionError("unknown status accepted")
        except ValueError:
            pass
    finally:
        rm(d)


def test_records_classification_and_results():
    path, d = _db()
    try:
        con = queue.connect(path)
        tid = queue.add(con, "ship it", depth=3, risk="high")
        queue.record(con, tid, agent="builder", model="claude-sonnet-5",
                     skills=["builder/backend-engineering"], attempts=2)
        row = queue.get(con, tid)
        assert row["agent"] == "builder" and row["depth"] == 3 and row["risk"] == "high"
        assert row["attempts"] == 2
        events = con.execute("SELECT COUNT(*) FROM events WHERE task_id=?", (tid,)).fetchone()[0]
        assert events >= 1
    finally:
        rm(d)
