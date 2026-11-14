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


def main():
    root = _boot.load()
    cwd = _boot.payload().get("cwd") or os.getcwd()
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
            bits.append("Stale queue: %d tasks idle >7d (ids %s). Run `aos queue stale` to review." %
                        (len(old), ",".join(str(t["id"]) for t in old)))
        if len(queue.ready(queue.connect())) >= 4:
            bits.append("Many ready tasks: run `aos queue plan` for parallel waves "
                        "(small tasks batched per builder) instead of one pipeline each.")
    except Exception:
        pass
    pr = _stale_prs(cwd)
    if pr:
        bits.append(pr)
    bits.append("Run `aos plan \"<task>\"` before non-trivial work; guards run automatically.")
    _boot.emit({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                       "additionalContext": " ".join(bits)}})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
