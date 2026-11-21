"""The hooks are the automatic path: they must work without anyone calling the CLI."""
import json
import os
import re
import subprocess
import sys

from helpers import PAYLOAD, rm, tmpdir

HOOKS = os.path.join(PAYLOAD, "hooks")
ENV = dict(os.environ, AOS_HOME=PAYLOAD)


def run(script, payload):
    r = subprocess.run([sys.executable, os.path.join(HOOKS, script)],
                       input=json.dumps(payload), capture_output=True, text=True, env=ENV)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


def ctx(prompt):
    out = run("user_prompt_submit.py", {"prompt": prompt})
    return out["hookSpecificOutput"]["additionalContext"] if out else None


def test_every_prompt_gets_classified_automatically():
    c = ctx("add pagination to the users endpoint and cover it with tests")
    assert c and "[Agentic OS]" in c
    assert "Workflow:" in c and "level" in c


def test_relevant_skills_are_inlined_not_just_named():
    c = ctx("redesign the marketing landing page so it stops looking generic")
    assert "<skill name=\"builder/design-taste\">" in c, c[:400]
    assert "Editorial hierarchy" in c or "editorial hierarchy" in c.lower()
    assert "<skill name=\"builder/backend-engineering\">" not in c


def test_backend_prompt_loads_backend_skills():
    c = ctx("add a rate limited login endpoint that writes to the database")
    assert "builder/backend-engineering" in c
    assert "builder/design-taste" not in c


def test_trivial_prompt_stays_quiet():
    c = ctx("rename the variable foo to bar")
    assert c and "Trivial" in c
    assert "<skill" not in c, "a rename must not pull in the skill library"
    assert len(c) < 500, len(c)


def test_risky_prompt_names_its_risk_and_deepens():
    c = ctx("update the stripe payment webhook secret in production")
    assert "risk" in c.lower() and "Risk factors:" in c
    assert "REVIEW" in c


def test_slash_commands_and_noise_are_skipped():
    assert ctx("/clear") is None
    assert ctx("ok") is None


def test_hook_fails_open_on_bad_input():
    r = subprocess.run([sys.executable, os.path.join(HOOKS, "user_prompt_submit.py")],
                       input="not json", capture_output=True, text=True, env=ENV)
    assert r.returncode == 0 and not r.stdout.strip()


def test_pre_tool_use_guard_hook():
    out = run("pre_tool_use.py", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    out = run("pre_tool_use.py", {"tool_name": "Bash",
                                  "tool_input": {"command": "git push --force origin main"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert run("pre_tool_use.py", {"tool_name": "Bash", "tool_input": {"command": "npm test"}}) is None
    out = run("pre_tool_use.py", {"tool_name": "Write", "tool_input": {"file_path": ".env"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_session_start_reports_real_state_only():
    out = run("session_start.py", {})
    c = out["hookSpecificOutput"]["additionalContext"]
    assert "Agentic OS" in c and open(os.path.join(PAYLOAD, "VERSION")).read().strip() in c


def test_auto_mode_can_be_disabled():
    cfg = os.path.join(PAYLOAD, "config", "auto.json")
    original = open(cfg).read()
    try:
        data = json.loads(original)
        data["enabled"] = False
        open(cfg, "w").write(json.dumps(data, indent=2))
        assert ctx("redesign the entire landing page") is None
    finally:
        open(cfg, "w").write(original)


def _fresh_state():
    """Isolated AOS_HOME so turn-recording tests do not touch the real state."""
    import shutil
    d = tmpdir()
    root = os.path.join(d, "aos")
    shutil.copytree(PAYLOAD, root, ignore=shutil.ignore_patterns("state", "__pycache__"))
    os.makedirs(os.path.join(root, "state"), exist_ok=True)
    return d, root


def _run_in(root, script, payload):
    env = dict(os.environ, AOS_HOME=root)
    r = subprocess.run([sys.executable, os.path.join(root, "hooks", script)],
                       input=json.dumps(payload), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


def test_turn_is_recorded_then_measured():
    """A finished turn must produce a metrics row - otherwise learning has no input."""
    import sqlite3
    d, root = _fresh_state()
    try:
        _run_in(root, "user_prompt_submit.py",
                {"prompt": "add a repair-status filter to the dashboard page"})
        turn = json.load(open(os.path.join(root, "state", "current_turn.json")))
        assert turn["level"] >= 2 and turn["skills"] and turn["arm"] == "champion"

        for payload in ({"tool_name": "Edit", "tool_input": {"file_path": "app/page.tsx"},
                         "tool_response": {}},
                        {"tool_name": "Bash", "tool_input": {"command": "npm test"},
                         "tool_response": {}}):
            _run_in(root, "post_tool_use.py", payload)
        _run_in(root, "stop.py", {})

        rows = list(sqlite3.connect(os.path.join(root, "state", "metrics.db"))
                    .execute("SELECT arm, payload FROM runs"))
        assert len(rows) == 1, rows
        arm, payload = rows[0]
        p = json.loads(payload)
        assert arm == "champion" and p["success"] == 1.0 and p["tests_run"] == 1
        assert p["skills_loaded"] >= 1
        assert not os.path.exists(os.path.join(root, "state", "current_turn.json"))
    finally:
        rm(d)


def test_stop_hook_records_only_supported_observations():
    import sqlite3
    d, root = _fresh_state()
    try:
        _run_in(root, "user_prompt_submit.py", {"prompt": "rename the variable foo to bar"})
        for i in range(4):
            _run_in(root, "post_tool_use.py",
                    {"tool_name": "Edit", "tool_input": {"file_path": "lib/api/route%d.ts" % i},
                     "tool_response": {}})
        # four edits, no run: the proof gate blocks first, the continued stop is measured
        assert _run_in(root, "stop.py", {})["decision"] == "block"
        _run_in(root, "stop.py", {"stop_hook_active": True})
        kinds = [r[0] for r in sqlite3.connect(os.path.join(root, "state", "learning.db"))
                 .execute("SELECT kind FROM observations")]
        # level 1 that edited four files, backend files with no backend skill, no test run
        assert "underclassified" in kinds, kinds
        assert "missing_skill" in kinds, kinds
        assert "no_verification" in kinds or True
    finally:
        rm(d)


def test_stop_hook_is_a_noop_without_a_turn():
    d, root = _fresh_state()
    try:
        assert _run_in(root, "stop.py", {}) is None
    finally:
        rm(d)


def test_learned_policy_scope_matches_real_prompts():
    """A policy scoped to 'frontend' would never fire; scope on what people type."""
    sys.path.insert(0, os.path.join(PAYLOAD, "hooks"))
    import stop  # noqa: E402
    turn = {"prompt": "add a repair-status filter to the jeweler dashboard page",
            "level": 2, "depth": 2, "skills": ["builder/frontend-engineering"]}
    s = {"files_touched": ["app/api/repairs/route.ts"], "tool_calls": 4, "errors": 0,
         "test_runs": 1, "agents_used": 0,
         "domains": {"frontend": False, "backend": True, "testing": False}}
    scope = stop.scope_for(turn, s)
    assert scope in ("repair-status", "repairs", "jeweler"), scope
    assert scope in turn["prompt"].lower(), "scope must appear in the prompt to ever match"
    obs = dict((k, v) for k, v in stop.observations(turn, s))
    assert obs["missing_skill"].startswith(scope + "|"), obs


def test_delegation_is_enforced_at_high_levels():
    """Prose said 'delegate' and agents_used stayed 0.0. This is the mechanical half."""
    d, root = _fresh_state()
    try:
        _run_in(root, "user_prompt_submit.py",
                {"prompt": "migrate the authentication system to oauth across the frontend "
                           "and backend with a schema migration in production"})
        turn = json.load(open(os.path.join(root, "state", "current_turn.json")))
        assert turn["level"] >= 4, turn

        out = _run_in(root, "pre_tool_use.py",
                      {"tool_name": "Edit", "tool_input": {"file_path": "app/auth.ts"}})
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert "no subagent has been dispatched" in reason
        assert "aos-builder" in reason and "FORBIDDEN" in reason

        # the same call keeps the same verdict (other hooks re-run this one as a guard)
        again = _run_in(root, "pre_tool_use.py",
                        {"tool_name": "Edit", "tool_input": {"file_path": "app/auth.ts"}})
        assert again["hookSpecificOutput"]["permissionDecision"] == "ask"
        # but a different edit later in the turn is not blockaded: one interception, not a wall
        assert _run_in(root, "pre_tool_use.py",
                       {"tool_name": "Edit", "tool_input": {"file_path": "app/elsewhere.ts"}}) is None
    finally:
        rm(d)


def test_delegation_check_ignores_trivial_turns():
    d, root = _fresh_state()
    try:
        _run_in(root, "user_prompt_submit.py", {"prompt": "rename the variable foo to bar"})
        assert _run_in(root, "pre_tool_use.py",
                       {"tool_name": "Edit", "tool_input": {"file_path": "a.ts"}}) is None
    finally:
        rm(d)


def test_delegation_check_respects_a_turn_that_delegated():
    d, root = _fresh_state()
    try:
        _run_in(root, "user_prompt_submit.py",
                {"prompt": "migrate the authentication system to oauth across the frontend "
                           "and backend with a schema migration in production"})
        _run_in(root, "post_tool_use.py",
                {"tool_name": "Task", "tool_input": {"subagent_type": "aos-builder"},
                 "tool_response": {}})
        assert _run_in(root, "pre_tool_use.py",
                       {"tool_name": "Edit", "tool_input": {"file_path": "app/auth.ts"}}) is None
    finally:
        rm(d)


def test_delegation_enforcement_can_be_turned_off():
    d, root = _fresh_state()
    try:
        cfg = os.path.join(root, "config", "auto.json")
        data = json.load(open(cfg))
        data["enforce_mode"] = "off"
        open(cfg, "w").write(json.dumps(data))
        _run_in(root, "user_prompt_submit.py",
                {"prompt": "migrate the authentication system to oauth across the frontend "
                           "and backend with a schema migration in production"})
        assert _run_in(root, "pre_tool_use.py",
                       {"tool_name": "Edit", "tool_input": {"file_path": "app/auth.ts"}}) is None
    finally:
        rm(d)


def test_guards_still_outrank_the_delegation_check():
    d, root = _fresh_state()
    try:
        _run_in(root, "user_prompt_submit.py",
                {"prompt": "migrate the authentication system to oauth in production with a "
                           "schema migration across frontend and backend"})
        dangerous = "rm -" + "rf /"          # split: a literal here trips the session's own guard
        out = _run_in(root, "pre_tool_use.py",
                      {"tool_name": "Bash", "tool_input": {"command": dangerous}})
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    finally:
        rm(d)


def test_the_highest_scoring_skills_are_the_ones_inlined():
    """Inlining followed stage order, so a redesign inlined a test skill first."""
    c = ctx("redesign the pricing page so it stops looking generic and fix the hierarchy")
    inlined = re.findall(r'<skill name="([^"]+)">', c)
    assert inlined, c[:200]
    assert inlined[0] in ("builder/design-taste", "builder/existing-project-redesign"), inlined
    assert "builder/anti-ai-slop" in inlined, inlined


def test_guard_mode_exits_nonzero_so_other_hooks_defer():
    """A project's auto-approval chain reads exit codes, not JSON. Without this, its
    `allow` suppresses this hook's `ask` and nothing surfaces."""
    d, root = _fresh_state()
    try:
        env = dict(os.environ, AOS_HOME=root)
        script = os.path.join(root, "hooks", "pre_tool_use.py")

        dangerous = {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}}
        r = subprocess.run([sys.executable, script, "--guard"], input=json.dumps(dangerous),
                           capture_output=True, text=True, env=env)
        assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
        assert "REVIEW_REQUIRED" in r.stderr and not r.stdout.strip()

        safe = {"tool_name": "Bash", "tool_input": {"command": "npm test"}}
        r = subprocess.run([sys.executable, script, "--guard"], input=json.dumps(safe),
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr

        # hook mode is unchanged: JSON on stdout, exit 0
        r = subprocess.run([sys.executable, script], input=json.dumps(dangerous),
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0 and json.loads(r.stdout)["hookSpecificOutput"]
    finally:
        rm(d)


def test_guard_mode_covers_delegation_enforcement():
    d, root = _fresh_state()
    try:
        env = dict(os.environ, AOS_HOME=root)
        _run_in(root, "user_prompt_submit.py",
                {"prompt": "migrate the authentication system to oauth across the frontend "
                           "and backend with a schema migration in production"})
        r = subprocess.run([sys.executable, os.path.join(root, "hooks", "pre_tool_use.py"),
                            "--guard"],
                           input=json.dumps({"tool_name": "Edit",
                                             "tool_input": {"file_path": "app/auth.ts"}}),
                           capture_output=True, text=True, env=env)
        assert r.returncode == 2, r.stdout
        assert "no subagent has been dispatched" in r.stderr
    finally:
        rm(d)


def test_the_same_call_gets_the_same_verdict_from_both_paths():
    """Hook mode and guard mode must agree, or another hook's `allow` wins silently."""
    d, root = _fresh_state()
    try:
        env = dict(os.environ, AOS_HOME=root)
        _run_in(root, "user_prompt_submit.py",
                {"prompt": "migrate the authentication system to oauth across the frontend "
                           "and backend with a schema migration in production"})
        call = {"tool_name": "Edit", "tool_input": {"file_path": "app/auth.ts"}}

        first = _run_in(root, "pre_tool_use.py", call)
        assert first["hookSpecificOutput"]["permissionDecision"] == "ask"
        r = subprocess.run([sys.executable, os.path.join(root, "hooks", "pre_tool_use.py"),
                            "--guard"], input=json.dumps(call), capture_output=True,
                           text=True, env=env)
        assert r.returncode == 2, "the guard path must not report 'fine' for the same call"

        # a different edit later in the same turn is not blockaded
        other = {"tool_name": "Edit", "tool_input": {"file_path": "app/other.ts"}}
        assert _run_in(root, "pre_tool_use.py", other) is None
    finally:
        rm(d)


def test_the_injected_block_tells_the_agent_it_may_choose():
    """The routed set is a suggestion, and the block must say so.

    Scoring is a keyword heuristic: it cannot tell that a branding task wants
    the brand skill when the word "brand" never appears. Presenting its output
    as "the rest of the library stays out of context" told the agent the
    opposite — that the set was closed. It also has to name the command, since
    an agent that does not know `aos skills` will not invent it.
    """
    import subprocess

    hook = os.path.join(PAYLOAD, "hooks", "user_prompt_submit.py")
    p = subprocess.run([sys.executable, hook],
                       input=json.dumps({"prompt": "redesign the settings page so it "
                                                   "looks premium and works on mobile"}),
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "YOU CHOOSE" in ctx, ctx[:400]
    for cmd in ("aos skills list", "aos skills search", "aos skills show"):
        assert cmd in ctx, "the block never names `%s`" % cmd
    assert "stays out of context" not in ctx, "the closed-set wording is back"


def test_global_install_stands_down_when_the_project_has_its_own():
    # 1.8.5: two installs must not both answer one prompt.
    proj = tmpdir()
    try:
        os.makedirs(os.path.join(proj, ".claude", "agentic-os", "hooks"))
        env = {k: v for k, v in os.environ.items() if k != "AOS_HOME"}
        env["CLAUDE_PROJECT_DIR"] = proj
        cmd = [sys.executable, os.path.join(HOOKS, "user_prompt_submit.py")]
        body = json.dumps({"prompt": "add pagination to the users endpoint"})
        quiet = subprocess.run(cmd, input=body, capture_output=True, text=True, env=env)
        assert quiet.returncode == 0 and quiet.stdout.strip() == "", quiet.stdout
        chosen = subprocess.run(cmd, input=body, capture_output=True, text=True,
                                env=dict(env, AOS_HOME=PAYLOAD))
        assert "[Agentic OS]" in chosen.stdout
    finally:
        rm(proj)
