"""The runtime CLI is the interface agents actually use."""
import json
import os
import subprocess
import sys

from helpers import PAYLOAD

CLI = [sys.executable, os.path.join(PAYLOAD, "runtime", "cli.py")]
ENV = dict(os.environ, AOS_HOME=PAYLOAD)


def run(*args):
    r = subprocess.run(CLI + list(args), capture_output=True, text=True, env=ENV)
    return r.returncode, json.loads(r.stdout) if r.stdout.strip() else None


def test_plan_command():
    code, out = run("plan", "add pagination to the users endpoint")
    assert code == 0
    assert out["stages"] and out["classification"]["depth"] >= 1
    assert all(s["model"] and s["skills"] is not None for s in out["stages"])


def test_guard_command_exit_codes():
    code, out = run("guard", "rm -rf /")
    assert code == 1 and out["action"] == "BLOCK"
    code, out = run("guard", "npm test")
    assert code == 0 and out["action"] == "ALLOW"


def test_registry_validate():
    code, out = run("registry", "validate")
    assert code == 0 and out["problems"] == [] and out["count"] == 59


def test_models_command_is_honest_about_availability():
    code, out = run("models")
    assert code == 0
    for tier, info in out["validation"].items():
        assert "confirmed" in info and info["model"]


def test_route_command():
    code, out = run("route", "improve the accessibility of the nav menu", "--agent", "builder")
    assert code == 0 and "builder/accessibility" in out["loaded"]


def test_learn_cycle_command():
    code, out = run("learn", "cycle", "--dry-run")
    assert code == 0
    for key in ("proposed", "rejected_unsafe", "decisions", "pending", "champions"):
        assert key in out, out


def test_vault_ships_inert_and_is_wired():
    """The vault link must be present but OFF until a vault_root is configured.

    It lived as a local patch to one project's runtime/cli.py for three days and
    was silently overwritten by every `update` — runtime/ is not preserved. So
    it belongs in the payload. Shipping it ON would point every install at one
    person's filesystem, hence the empty default.
    """
    from runtime import cli, vault

    cfg = vault.load_config()
    assert cfg.get("vault_root") == "", "the shipped default must name no vault"
    assert vault.is_linked(cfg) is False, "must ship unlinked"
    assert vault.write_enabled(cfg) is False, "must not write back until configured"

    # Wired into the CLI: drive `aos vault status` end to end through main()
    # and read what it printed. Asserting the branch exists by reading the
    # source would pass on a parser that never reaches it.
    import contextlib
    import io
    import json as _json

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(["vault", "status"])
    assert rc in (0, None), "aos vault status exited %r" % rc
    got = _json.loads(buf.getvalue())
    assert got["linked"] is False and got["write_enabled"] is False, got
    assert "read_folders" in got and "indexed" in got, got


def test_skills_list_accepts_either_agent_spelling():
    """`--agent aos-builder` must work, not just `--agent builder`.

    An agent knows itself by its installed name — its own frontmatter says
    `name: aos-builder` — while skill frontmatter is keyed on the short config
    name. Before this fold, `--agent aos-builder` returned 1 skill where
    `--agent builder` returned 73: a dead end that reads like an empty library,
    and every agent definition tells the agent to run exactly that command.
    """
    code_short, short = run("skills", "list", "--agent", "builder")
    code_long, long_ = run("skills", "list", "--agent", "aos-builder")
    assert code_short == 0 and code_long == 0
    assert short["count"] > 1, "fixture library too small to prove anything"
    assert short["count"] == long_["count"], (short["count"], long_["count"])
    assert [s["name"] for s in short["skills"]] == [s["name"] for s in long_["skills"]]
