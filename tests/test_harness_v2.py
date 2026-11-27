"""Harness v2: single writer, hand-back budget, memory lint, progress file, traces."""
import json
import os

from helpers import rm
from test_context import _fresh, _run, _sub_stop, _tool

HEAVY = ("migrate the authentication system to oauth across the frontend and backend with a "
         "schema migration, rewrite the session store and update every api route")


def _mode(root, mode):
    p = os.path.join(root, "config", "auto.json")
    cfg = json.load(open(p))
    cfg["agent_mode"] = mode
    cfg["fanout_from_level"] = 1  # force the heavy branch regardless of how HEAVY scores
    json.dump(cfg, open(p, "w"))


def test_single_mode_heavy_fans_out_readers_and_keeps_one_writer():
    d, root = _fresh()
    try:
        _mode(root, "single")
        out = _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": HEAVY})
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "read-only" in ctx and "one writer" in ctx, ctx[:1500]
        # the non-risky heavy branch says the same
        out = _run(root, "user_prompt_submit.py",
                   {"session_id": "T", "prompt": "refactor the dashboard components across the "
                                                 "frontend and add tests for every widget"})
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "read-only" in ctx and "one writer" in ctx, ctx[:1500]
    finally:
        rm(d)


def test_oversized_subagent_handback_is_sent_back_once():
    d, root = _fresh()
    try:
        _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": HEAVY})
        _tool(root, "S", "Read", agent_id="a1", file_path="app/auth.py")
        long_reply = "Found the session store in app/auth.py. " + ("detail " * 3000)
        blocked, why = _sub_stop(root, {"session_id": "S", "agent_id": "a1",
                                        "last_assistant_message": long_reply})
        assert blocked and "condense" in why.lower(), why
        short = "Session store: app/auth.py:40. Callers: app/api.py:12, app/jobs.py:88."
        assert not _sub_stop(root, {"session_id": "S", "agent_id": "a1",
                                    "last_assistant_message": short})[0]
        # never loop: the continuation this caused is let through even if still long
        assert not _sub_stop(root, {"session_id": "S", "agent_id": "a1", "stop_hook_active": True,
                                    "last_assistant_message": long_reply})[0]
    finally:
        rm(d)


def test_memory_lint_finds_known_stale_facts_and_is_quiet_on_clean():
    from helpers import tmpdir, write
    from runtime import memlint
    d = tmpdir()
    try:
        write(os.path.join(d, "app", "real.py"), "x = 1\n")
        doc = write(os.path.join(d, "CLAUDE.md"),
                    "See `app/real.py` and `app/gone.py`, and `other-repo/x.py`, `<id>/y.md`.\n"
                    "There are 51 skills. Installed at `.claude/agentic-os`, version `1.8.3`.\n")
        probs = memlint.lint([doc], project=d, skill_count=58, version="1.8.5")
        kinds = sorted(p["kind"] for p in probs)
        assert kinds == ["count", "path", "version"], probs
        assert any("app/gone.py" in p["detail"] for p in probs)
        write(doc, "See `app/real.py:12`. There are 58 skills. Version `1.8.5`.\n"
                   "`app/old.py` was deleted in the cleanup.\n")
        assert memlint.lint([doc], project=d, skill_count=58, version="1.8.5") == []
    finally:
        rm(d)


def test_session_start_reports_stale_facts_only_when_present():
    import shutil
    from helpers import PAYLOAD, tmpdir, write
    proj = tmpdir()
    try:
        root = os.path.join(proj, ".claude", "agentic-os")
        shutil.copytree(PAYLOAD, root, ignore=shutil.ignore_patterns("state", "__pycache__"))
        os.makedirs(os.path.join(root, "state"))
        os.makedirs(os.path.join(proj, "app"))
        doc = os.path.join(proj, "CLAUDE.md")
        write(doc, "See `app/missing-for-lint.tsx`.\n")
        ctx = _run(root, "session_start.py", {"session_id": "S"})["hookSpecificOutput"]["additionalContext"]
        assert "Stale facts" in ctx and "app/missing-for-lint.tsx" in ctx, ctx
        write(doc, "Nothing stale here.\n")
        ctx = _run(root, "session_start.py", {"session_id": "S"})["hookSpecificOutput"]["additionalContext"]
        assert "Stale facts" not in ctx, ctx
    finally:
        rm(proj)


def test_progress_file_is_created_for_real_work_and_survives_compaction():
    d, root = _fresh()
    try:
        out = _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": HEAVY})
        ctx = out["hookSpecificOutput"]["additionalContext"]
        path = os.path.join(root, "state", "progress", "S.md")
        assert os.path.exists(path) and path in ctx, ctx[-800:]
        assert "oauth" in open(path).read()
        with open(path, "a") as fh:
            fh.write("- pytest tests/auth -> 12 passed\n")
        restored = _run(root, "session_start.py", {"session_id": "S", "source": "compact"})
        assert "12 passed" in restored["hookSpecificOutput"]["additionalContext"]
        # a trivial prompt gets no progress file
        _run(root, "user_prompt_submit.py", {"session_id": "T", "prompt": "fix a typo in the footer text"})
        assert not os.path.exists(os.path.join(root, "state", "progress", "T.md"))
    finally:
        rm(d)


def test_prompt_hook_records_a_local_trace():
    d, root = _fresh()
    try:
        _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": HEAVY})
        lines = open(os.path.join(root, "state", "evals", "traces.jsonl")).read().splitlines()
        t = json.loads(lines[-1])
        assert t["session"] == "S" and "oauth" in t["prompt"] and "risk" in t, t
    finally:
        rm(d)
