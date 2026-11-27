"""Persistent task queue (SQLite). Survives session loss.

Statuses form the task lifecycle; dependencies gate readiness; a failed task never
stops unrelated work.
"""
import json
import os
import sqlite3
import time

from . import paths, util

STATUSES = ["QUEUED", "CLASSIFYING", "PLANNED", "READY", "RUNNING", "TESTING", "REPAIRING",
            "REVIEWING", "FINAL_VALIDATION", "COMPLETED", "PARTIAL", "WAITING_DEPENDENCY",
            "WAITING_APPROVAL", "BLOCKED", "PAUSED", "FAILED", "ESCALATED", "CANCELLED"]
TERMINAL = {"COMPLETED", "CANCELLED"}
UNSATISFIED = {"FAILED", "BLOCKED", "ESCALATED", "CANCELLED", "PARTIAL"}
SCHEMA_VERSION = 1


def connect(db_path=None):
    path = db_path or paths.state("queue.db")
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'QUEUED',
        depth INTEGER DEFAULT 1,
        risk TEXT DEFAULT 'normal',
        agent TEXT,
        model TEXT,
        classification TEXT,
        skills TEXT,
        result TEXT,
        attempts INTEGER DEFAULT 0,
        created_at TEXT, updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS deps (
        task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        depends_on INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        kind TEXT DEFAULT 'explicit',
        PRIMARY KEY (task_id, depends_on)
    );
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER, kind TEXT, detail TEXT, at TEXT
    );
    """)
    con.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    con.commit()
    return con


def add(con, title, body="", depends_on=(), depth=1, risk="normal", agent=None, classification=None):
    deps = [int(x) for x in depends_on]
    missing = [x for x in deps if not con.execute("SELECT 1 FROM tasks WHERE id=?", (x,)).fetchone()]
    if missing:
        raise ValueError("unknown dependency %s" % ",".join(map(str, missing)))
    cur = con.execute(
        "INSERT INTO tasks (title, body, status, depth, risk, agent, classification, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (title, body, "QUEUED", depth, risk, agent,
         json.dumps(classification) if classification else None, util.now(), util.now()))
    tid = cur.lastrowid
    for dep in deps:
        con.execute("INSERT OR IGNORE INTO deps VALUES (?,?,'explicit')", (tid, dep))
    infer(con, tid, title)
    log(con, tid, "created", title)
    con.commit()
    return tid


INFER_RULES = [("test", ("build", "implement", "add", "create")),
               ("review", ("build", "implement", "test", "add")),
               ("deploy", ("test", "review"))]


def infer(con, task_id, title):
    """Infer dependencies: 'test X' waits on an open 'build X' with overlapping subject."""
    low = title.lower()
    words = set(w for w in low.replace("-", " ").split() if len(w) > 3)
    for verb, prereqs in INFER_RULES:
        if not low.startswith(verb) and (" %s " % verb) not in low:
            continue
        for row in con.execute("SELECT id, title FROM tasks WHERE id != ? AND status NOT IN ('COMPLETED','CANCELLED')",
                               (task_id,)):
            other = row["title"].lower()
            if not any(other.startswith(p) or (" %s " % p) in other for p in prereqs):
                continue
            ow = set(w for w in other.replace("-", " ").split() if len(w) > 3)
            if words & ow:
                con.execute("INSERT OR IGNORE INTO deps VALUES (?,?,'inferred')", (task_id, row["id"]))


def blockers(con, task_id):
    out = []
    for row in con.execute(
            "SELECT t.id, t.status FROM deps d JOIN tasks t ON t.id = d.depends_on WHERE d.task_id = ?",
            (task_id,)):
        if row["status"] != "COMPLETED":
            out.append({"id": row["id"], "status": row["status"],
                        "permanent": row["status"] == "CANCELLED"})
    return out


def ready(con):
    """Tasks that may run now. Failure of one task never hides an independent one."""
    out = []
    rows = con.execute("SELECT * FROM tasks WHERE status IN ('QUEUED','READY','PLANNED','PAUSED',"
                       "'WAITING_DEPENDENCY') ORDER BY id").fetchall()
    for row in rows:
        b = blockers(con, row["id"])
        if b:
            if row["status"] != "WAITING_DEPENDENCY":
                set_status(con, row["id"], "WAITING_DEPENDENCY",
                           "waiting on %s" % ",".join(str(x["id"]) for x in b))
            continue
        if row["status"] == "WAITING_DEPENDENCY":    # self-heal: its blockers are gone
            set_status(con, row["id"], "READY", "dependencies met")
            row = con.execute("SELECT * FROM tasks WHERE id=?", (row["id"],)).fetchone()
        out.append(dict(row))
    return out


def claim(con):
    """Take the oldest ready task (FIFO by id) and mark it RUNNING.

    Compare-and-set on the status, so two sessions sharing the queue never take the
    same task: the loser's UPDATE matches no row and it moves on to the next one.
    """
    for row in ready(con):
        cur = con.execute("UPDATE tasks SET status='RUNNING', updated_at=? WHERE id=? AND status=?",
                          (util.now(), row["id"], row["status"]))
        if cur.rowcount == 1:
            log(con, row["id"], "status", "RUNNING claimed")
            con.commit()
            row["status"] = "RUNNING"
            return row
        con.commit()
    return None


def set_status(con, task_id, status, detail=""):
    if status not in STATUSES:
        raise ValueError("unknown status %s" % status)
    prev = con.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not prev:
        raise ValueError("unknown task %s" % task_id)
    con.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=?", (status, util.now(), task_id))
    log(con, task_id, "status", "%s %s" % (status, detail))
    if status == "COMPLETED":
        # wake dependents that were parked
        for row in con.execute("SELECT task_id FROM deps WHERE depends_on=?", (task_id,)):
            dep_id = row["task_id"]
            if not blockers(con, dep_id):
                con.execute("UPDATE tasks SET status='READY', updated_at=? WHERE id=? AND status='WAITING_DEPENDENCY'",
                            (util.now(), dep_id))
    if status == "CANCELLED":
        # A cancelled prerequisite never completes, so a dependent waiting on it waits
        # forever. Mark it BLOCKED with the reason instead of leaving it silently parked.
        for row in con.execute("SELECT task_id FROM deps WHERE depends_on=?", (task_id,)):
            dep_id = row["task_id"]
            cur = con.execute("SELECT status FROM tasks WHERE id=?", (dep_id,)).fetchone()
            if cur and cur["status"] not in TERMINAL:
                con.execute("UPDATE tasks SET status='BLOCKED', updated_at=? WHERE id=?",
                            (util.now(), dep_id))
                log(con, dep_id, "status",
                    "BLOCKED prerequisite %s was cancelled" % task_id)
    if prev["status"] == "CANCELLED" and status not in TERMINAL:
        # Reopened: release only the dependents this task's cancellation blocked.
        reason = "BLOCKED prerequisite %s was cancelled" % task_id
        for row in con.execute("SELECT task_id FROM deps WHERE depends_on=?", (task_id,)).fetchall():
            last = con.execute("SELECT detail FROM events WHERE task_id=? AND kind='status'"
                               " ORDER BY id DESC LIMIT 1", (row["task_id"],)).fetchone()
            if last and last["detail"] == reason:
                con.execute("UPDATE tasks SET status='WAITING_DEPENDENCY', updated_at=? "
                            "WHERE id=? AND status='BLOCKED'", (util.now(), row["task_id"]))
                log(con, row["task_id"], "status", "WAITING_DEPENDENCY prerequisite %s reopened"
                    % task_id)
    if status in ("FAILED", "BLOCKED", "ESCALATED"):
        for row in con.execute("SELECT task_id FROM deps WHERE depends_on=?", (task_id,)):
            con.execute("UPDATE tasks SET status='WAITING_DEPENDENCY', updated_at=? WHERE id=? AND status NOT IN ('COMPLETED','CANCELLED')",
                        (util.now(), row["task_id"]))
    con.commit()


def record(con, task_id, **fields):
    allowed = {"agent", "model", "skills", "result", "classification", "depth", "risk", "attempts"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append("%s=?" % k)
        vals.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
    if not sets:
        return
    vals.extend([util.now(), task_id])
    con.execute("UPDATE tasks SET %s, updated_at=? WHERE id=?" % ", ".join(sets), vals)
    con.commit()


def log(con, task_id, kind, detail):
    con.execute("INSERT INTO events (task_id, kind, detail, at) VALUES (?,?,?,?)",
                (task_id, kind, str(detail)[:2000], util.now()))


def get(con, task_id):
    row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return dict(row) if row else None


def listing(con, status=None):
    if status:
        rows = con.execute("SELECT * FROM tasks WHERE status=? ORDER BY id", (status,))
    else:
        rows = con.execute("SELECT * FROM tasks ORDER BY id")
    out = []
    for r in rows:
        d = dict(r)
        d["blockers"] = [b["id"] for b in blockers(con, r["id"])]
        out.append(d)
    return out


def stale(con, days=7):
    """Non-terminal tasks not updated for more than `days` days (updated_at is UTC)."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - days * 86400))
    rows = con.execute("SELECT * FROM tasks WHERE status NOT IN ('COMPLETED','CANCELLED')"
                       " AND updated_at < ? ORDER BY id", (cutoff,))
    return [dict(r) for r in rows]


def stats(con):
    counts = {}
    for row in con.execute("SELECT status, COUNT(*) c FROM tasks GROUP BY status"):
        counts[row["status"]] = row["c"]
    return {"total": sum(counts.values()), "by_status": counts}
