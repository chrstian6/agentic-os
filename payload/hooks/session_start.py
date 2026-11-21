#!/usr/bin/env python3
"""SessionStart: inject verified Agentic OS state (never fabricated) as context."""
import calendar
import json
import os
import shutil
import subprocess
import sys
import time

import _boot


def _stale_prs(cwd):
    """One line naming own open PRs idle >24h; any failure or timeout yields nothing."""
    try:
        if not shutil.which("gh"):
            return ""
        git = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=cwd,
                             capture_output=True, timeout=2)
        if git.returncode:
            return ""
        r = subprocess.run(["gh", "pr", "list", "--author", "@me", "--state", "open", "--json",
                            "number,title,updatedAt,headRefName", "--limit", "20"],
                           cwd=cwd, capture_output=True, text=True, timeout=4)
        if r.returncode:
            return ""
        now, old = time.time(), []
        for p in json.loads(r.stdout):
            t = calendar.timegm(time.strptime(p["updatedAt"], "%Y-%m-%dT%H:%M:%SZ"))
            if now - t > 86400:
                old.append("#%d %s (%dd idle)" % (p["number"], p["title"], (now - t) // 86400))
        return ("Stale open PRs in this repo: %s - merge, close, or report each before new work."
                % ", ".join(old)) if old else ""
    except Exception:
        return ""


def _forget_seen(root, sid):
    """Compaction and /clear drop the skill text from context; the prompt hook must
    re-send it instead of naming it as 'still in force'."""
    path = os.path.join(root, "state", "session_skills.json")
    try:
        with open(path) as fh:
            data = json.load(fh)
        if data.pop(sid, None) is not None:
            with open(path + ".tmp", "w") as fh:
                json.dump(data, fh)
            os.replace(path + ".tmp", path)
    except (IOError, OSError, ValueError):
        pass


def restore(root, sid):
    """After compaction: the plan the summary may have flattened, from disk."""
    turn = _boot.read_turn(root, sid)
    if not turn:
        return ""
    bits = ["Restored after compaction - the turn in progress: \"%s\" (level %s, risk %s)."
            % (turn.get("prompt", ""), turn.get("level"), turn.get("risk"))]
    if turn.get("skills"):
        bits.append("Its skills (re-sent on the next prompt; reload now with "
                    "`aos skills show <name>`): %s." % ", ".join(turn["skills"][:8]))
    ev = _boot.session_events(root, sid, since=turn.get("started", 0), main_only=True)
    files = sorted({e["path"] for e in ev if e.get("path")})[-10:]
    runs = [e["cmd"] for e in ev if e.get("cmd")][-5:]
    if files:
        bits.append("Files touched so far: %s." % ", ".join(files))
    if runs:
        bits.append("Last commands run: %s." % " | ".join(runs))
    return " ".join(bits)


def main():
    root = _boot.load()
    data = _boot.payload()
    cwd = data.get("cwd") or os.getcwd()
    sid, source = data.get("session_id"), data.get("source") or "startup"
    if sid and source in ("compact", "clear"):
        _forget_seen(root, sid)
    if source == "compact":
        text = restore(root, sid) if sid else ""
        if text:
            _boot.emit({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                               "additionalContext": text}})
        return 0
    try:
        from runtime import learning, queue
    except Exception:
        return 0
    bits = []
    try:
        version = open(os.path.join(root, "VERSION")).read().strip()
        bits.append("Agentic OS %s active (%s)." % (version, root))
    except Exception:
        return 0
    try:
        st = queue.stats(queue.connect())
        if st["total"]:
            bits.append("Queue: %d tasks %s." % (st["total"], st["by_status"]))
    except Exception:
        pass
    try:
        pols = learning.active(learning.connect())
        if pols:
            bits.append("Learned policies in force: %s." %
                        ", ".join("%s %s(%s)" % (p["kind"], p["key"], p["value"]) for p in pols[:5]))
    except Exception:
        pass
    try:
        old = queue.stale(queue.connect())
        if old:
            bits.append("%d queued tasks idle >7d (`aos queue stale`)." % len(old))
    except Exception:
        pass
    pr = _stale_prs(cwd)
    if pr:
        bits.append(pr)
    _boot.emit({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                       "additionalContext": " ".join(bits)}})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
