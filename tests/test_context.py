"""Context management and proof-of-work: session isolation, compaction recovery, the
proof gate, and model routing that the Agent tool can actually consume."""
import json
import os
import shutil
import subprocess
import sys

from helpers import PAYLOAD, rm, tmpdir


def _fresh():
    d = tmpdir()
    root = os.path.join(d, "aos")
    shutil.copytree(PAYLOAD, root, ignore=shutil.ignore_patterns("state", "__pycache__"))
    os.makedirs(os.path.join(root, "state"), exist_ok=True)
    return d, root


def _run(root, script, payload):
    env = dict(os.environ, AOS_HOME=root)
    r = subprocess.run([sys.executable, os.path.join(root, "hooks", script)],
                       input=json.dumps(payload), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


def _tool(root, sid, tool, agent_id=None, **ti):
    p = {"session_id": sid, "tool_name": tool, "tool_input": ti, "tool_response": {}}
    if agent_id:
        p["agent_id"] = agent_id
    _run(root, "post_tool_use.py", p)


PROMPT = "add a repair-status filter to the dashboard page"


def test_concurrent_sessions_do_not_share_turn_state():
    d, root = _fresh()
    try:
        _run(root, "user_prompt_submit.py", {"session_id": "A", "prompt": PROMPT})
        _run(root, "user_prompt_submit.py",
             {"session_id": "B", "prompt": "rename the helper in the billing module"})
        turns = os.path.join(root, "state", "turns")
        assert sorted(os.listdir(turns)) == ["A.json", "B.json"]
        assert "repair" in json.load(open(os.path.join(turns, "A.json")))["prompt"]
        # B's edits must not count against A's turn
        _tool(root, "B", "Edit", file_path="lib/billing.py")
        _tool(root, "A", "Bash", command="pytest -q")
        assert _run(root, "stop.py", {"session_id": "A"}) is None
        assert not os.path.exists(os.path.join(turns, "A.json"))
        assert os.path.exists(os.path.join(turns, "B.json"))
    finally:
        rm(d)


def test_compaction_resets_seen_skills_and_restores_the_plan():
    d, root = _fresh()
    try:
        first = _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": PROMPT})
        ctx = first["hookSpecificOutput"]["additionalContext"]
        assert "<skill name=" in ctx
        import re
        sent = set(re.findall(r'<skill name="([^"]+)"', ctx))
        again = _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": PROMPT})
        resent = set(re.findall(r'<skill name="([^"]+)"',
                                again["hookSpecificOutput"]["additionalContext"]))
        assert sent and not (sent & resent), (sent, resent)

        out = _run(root, "session_start.py", {"session_id": "S", "source": "compact"})
        restored = out["hookSpecificOutput"]["additionalContext"]
        assert "repair-status filter" in restored, restored

        after = _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": PROMPT})
        back = set(re.findall(r'<skill name="([^"]+)"',
                              after["hookSpecificOutput"]["additionalContext"]))
        assert sent & back, "skill text was lost to compaction and must be re-sent"
    finally:
        rm(d)


def test_session_start_does_not_contradict_automatic_planning():
    d, root = _fresh()
    try:
        out = _run(root, "session_start.py", {"session_id": "S", "source": "startup"})
        assert "aos plan" not in out["hookSpecificOutput"]["additionalContext"]
    finally:
        rm(d)


def test_pre_compact_tells_the_summary_what_to_keep():
    d, root = _fresh()
    try:
        _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": PROMPT})
        _tool(root, "S", "Edit", file_path="app/dashboard/page.tsx")
        _tool(root, "S", "Bash", command="npm test -- dashboard")
        env = dict(os.environ, AOS_HOME=root)
        r = subprocess.run([sys.executable, os.path.join(root, "hooks", "pre_compact.py")],
                           input=json.dumps({"session_id": "S", "trigger": "auto"}),
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        text = r.stdout
        assert "repair-status filter" in text
        assert "app/dashboard/page.tsx" in text and "npm test -- dashboard" in text
        assert len(text) < 10000
    finally:
        rm(d)


def _block(out):
    return bool(out) and out.get("decision") == "block"


def _sub_stop(root, payload):
    """SubagentStop blocks with exit 2 + stderr. Returns (blocked, reason)."""
    env = dict(os.environ, AOS_HOME=root)
    p = dict(payload, hook_event_name="SubagentStop")
    r = subprocess.run([sys.executable, os.path.join(root, "hooks", "stop.py")],
                       input=json.dumps(p), capture_output=True, text=True, env=env)
    assert r.returncode in (0, 2), r.stderr
    return r.returncode == 2, r.stderr


def test_proof_gate_blocks_edit_without_a_run():
    d, root = _fresh()
    try:
        _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": PROMPT})
        _tool(root, "S", "Bash", command="pytest -q")
        _tool(root, "S", "Edit", file_path="app/filter.py")
        out = _run(root, "stop.py", {"session_id": "S", "stop_hook_active": False})
        assert _block(out), out
        assert "app/filter.py" in out["reason"]
        # the turn is kept so the eventual stop is still measured
        assert os.path.exists(os.path.join(root, "state", "turns", "S.json"))
        # never loop: a continuation caused by this hook is let through
        assert not _block(_run(root, "stop.py", {"session_id": "S", "stop_hook_active": True}))
    finally:
        rm(d)


def test_proof_gate_passes_after_a_run_and_ignores_docs():
    d, root = _fresh()
    try:
        _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": PROMPT})
        _tool(root, "S", "Edit", file_path="app/filter.py")
        _tool(root, "S", "Bash", command="pytest -q")
        _tool(root, "S", "Edit", file_path="docs/notes.md")
        assert not _block(_run(root, "stop.py", {"session_id": "S"}))
    finally:
        rm(d)


def test_proof_gate_blocks_unbacked_claims():
    d, root = _fresh()
    try:
        _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": PROMPT})
        _tool(root, "S", "Read", file_path="app/filter.py")
        out = _run(root, "stop.py", {"session_id": "S",
                                     "last_assistant_message": "Fixed. All tests pass."})
        assert _block(out), out
    finally:
        rm(d)


def test_subagent_stop_judges_only_that_subagent():
    d, root = _fresh()
    try:
        _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": PROMPT})
        _tool(root, "S", "Bash", command="pytest -q")            # main thread ran tests
        _tool(root, "S", "Edit", agent_id="sub1", file_path="app/x.ts")
        blocked, reason = _sub_stop(root, {"session_id": "S", "agent_id": "sub1",
                                           "agent_type": "aos-builder"})
        assert blocked and "app/x.ts" in reason, reason
        _tool(root, "S", "Bash", agent_id="sub1", command="npx vitest run x")
        assert not _sub_stop(root, {"session_id": "S", "agent_id": "sub1"})[0]
        # SubagentStop must not consume the main turn
        assert os.path.exists(os.path.join(root, "state", "turns", "S.json"))
    finally:
        rm(d)


def test_delegations_are_logged():
    d, root = _fresh()
    try:
        _tool(root, "S", "Agent", subagent_type="aos-builder", prompt="x")
        rec = json.loads(open(os.path.join(root, "state", "events.jsonl")).read().splitlines()[-1])
        assert rec["agent"] == "aos-builder"
    finally:
        rm(d)


def test_harness_messages_are_not_classified_as_tasks():
    d, root = _fresh()
    try:
        for p in ("<task-notification>\n<task-id>x</task-id> completed",
                  "[Subagent hand-back] The text below is the final report of a subagent"):
            assert _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": p}) is None
    finally:
        rm(d)


def test_models_route_to_agent_tool_aliases():
    sys.path.insert(0, PAYLOAD)
    from runtime import models
    cfg = models._cfg()
    for tier in models.ORDER:
        assert models.resolve(tier, cfg, available=[]) in ("haiku", "sonnet", "opus"), tier
    assert models.route(1, "normal", "builder", cfg)["model"] == "opus"   # owner: builders deep
    assert models.route(1, "normal", "router", cfg)["model"] == "haiku"
    assert models.route(2, "normal", "tester", cfg)["model"] == "sonnet"


def test_dispatch_line_names_the_model_to_pass():
    d, root = _fresh()
    try:
        cfg_path = os.path.join(root, "config", "auto.json")
        cfg = json.load(open(cfg_path))
        cfg["agent_mode"] = "multi"
        json.dump(cfg, open(cfg_path, "w"))
        out = _run(root, "user_prompt_submit.py", {
            "session_id": "S",
            "prompt": "redesign the pricing page and add a stripe checkout api route with tests"})
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "DISPATCH" in ctx and "model=" in ctx, ctx[:600]
    finally:
        rm(d)


def test_agent_frontmatter_matches_role_tier():
    """The frontmatter model is what runs when no override is passed; it must agree
    with the role floor in models.json or the two silently drift (builder did)."""
    import glob
    import re
    sys.path.insert(0, PAYLOAD)
    from runtime import models
    cfg = models._cfg()
    for path in glob.glob(os.path.join(PAYLOAD, "agents", "aos-*.md")):
        role = os.path.basename(path)[4:-3]
        model = re.search(r"^model:\s*(\S+)", open(path).read(), re.M).group(1)
        want = models.resolve(cfg["agent_preferred_tier"][role], cfg, available=[])
        assert model == want, (role, model, want)


def test_subagent_gate_ignores_turn_timing_and_is_traced():
    """Live miss: a new prompt reset the turn's start after the subagent's edit, so the
    edit fell outside the window. Judge a subagent by its agent_id alone."""
    import time
    d, root = _fresh()
    try:
        _tool(root, "S", "Write", agent_id="sub9", file_path="probe.py")
        time.sleep(0.01)
        _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": PROMPT})
        blocked, _r = _sub_stop(root, {"session_id": "S", "agent_id": "sub9",
                                       "last_assistant_message": "done"})
        assert blocked
        trace = open(os.path.join(root, "state", "gate.log")).read()
        assert "SubagentStop" in trace and "sub9" in trace and "block" in trace, trace
    finally:
        rm(d)


def test_injected_context_stays_under_the_harness_cap():
    """Claude Code spills additionalContext over 10,000 chars to a file. Measured live: a
    pasted policy produced 20.5 KB at depth 4."""
    d, root = _fresh()
    try:
        prompt = ("audit our payment security, auth, stripe checkout, secrets handling, "
                  "rate limiting, database migrations, load testing and code review policy "
                  "for the production auction platform") * 3
        out = _run(root, "user_prompt_submit.py", {"session_id": "S", "prompt": prompt})
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert len(ctx) < 10000, len(ctx)
    finally:
        rm(d)


def test_subagent_handback_is_gated_once():
    """In the desktop app a subagent ends by calling SubagentHandback; SubagentStop fires
    after the report is delivered, so only a PreToolUse deny can send it back."""
    d, root = _fresh()
    try:
        _tool(root, "S", "Write", agent_id="h1", file_path="probe.py")
        hb = {"session_id": "S", "agent_id": "h1", "tool_name": "SubagentHandback",
              "tool_input": {"report": "done"}}
        out = _run(root, "pre_tool_use.py", hb)
        hso = out["hookSpecificOutput"]
        assert hso["permissionDecision"] == "deny" and "probe.py" in hso["permissionDecisionReason"]
        # once only: a second handback is let through so an agent that cannot run is not stuck
        assert _run(root, "pre_tool_use.py", hb) is None
        # an agent that ran something after its edit is never stopped
        _tool(root, "S", "Write", agent_id="h2", file_path="b.py")
        _tool(root, "S", "Bash", agent_id="h2", command="python3 b.py")
        assert _run(root, "pre_tool_use.py", dict(hb, agent_id="h2")) is None
    finally:
        rm(d)
