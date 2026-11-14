"""The installer must really install, be idempotent, and never touch what it does not own."""
import json
import os
import sys

from helpers import DIST, rm, tmpdir, write

sys.path.insert(0, os.path.join(DIST, "installer"))
import installer  # noqa: E402

UNRELATED = {
    "src/app.py": "print('user code')\n",
    ".claude/settings.local.json": '{"permissions": {"allow": ["Bash(ls:*)"]}}\n',
    ".claude/agents/my-agent.md": "---\nname: my-agent\ndescription: mine\n---\nkeep me\n",
    ".claude/skills/my-skill/SKILL.md": "---\nname: my-skill\ndescription: mine\n---\nkeep me\n",
    ".claude/commands/my-cmd.md": "my command\n",
}


def project():
    d = tmpdir()
    write(os.path.join(d, "package.json"),
          '{"name":"x","dependencies":{"next":"14"},"scripts":{"test":"vitest run"}}')
    write(os.path.join(d, ".claude", "settings.json"), '{"model": "opus"}\n')
    write(os.path.join(d, ".claude", "CLAUDE.md"), "# House rules\n\nUse tabs.\n")
    for rel, content in UNRELATED.items():
        write(os.path.join(d, rel), content)
    return d


def assert_project_intact(d):
    for rel, content in UNRELATED.items():
        p = os.path.join(d, rel)
        assert os.path.exists(p), "installer destroyed %s" % rel
        assert open(p).read() == content, "installer modified %s" % rel
    settings = json.load(open(os.path.join(d, ".claude", "settings.json")))
    assert settings.get("model") == "opus", "user settings lost"
    assert "House rules" in open(os.path.join(d, ".claude", "CLAUDE.md")).read()


def test_fresh_install_creates_everything():
    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        m = inst.install()
        root = os.path.join(d, ".claude", "agentic-os")
        for rel in ("runtime/cli.py", "config/guards.json", "hooks/pre_tool_use.py",
                    "bin/aos", "bin/agentic-os", "VERSION", "manifest.json",
                    "adapter.json", "skills/registry.json", "state/queue.db"):
            assert os.path.exists(os.path.join(root, rel)), rel
        assert len([f for f in os.listdir(os.path.join(d, ".claude", "agents"))
                    if f.startswith("aos-")]) == 9
        assert os.path.exists(os.path.join(d, ".claude", "skills", "agentic-os", "SKILL.md"))
        assert installer.BEGIN in open(os.path.join(d, ".claude", "CLAUDE.md")).read()
        assert not os.path.exists(os.path.join(d, "CLAUDE.md")), \
            "must reuse the project's existing memory file, not create a second one"
        assert installer.HOOK_MARKER in open(os.path.join(d, ".claude", "settings.json")).read()
        assert m["adapter"]["languages"] == ["javascript"], m["adapter"]
        assert inst.doctor()["ok"], inst.doctor()
        assert_project_intact(d)
    finally:
        rm(d)


def test_install_is_idempotent():
    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        first = inst.install()
        second = inst.install()
        assert first["install_id"] == second["install_id"]
        assert set(first["files"]) == set(second["files"])
        claude_md = open(os.path.join(d, ".claude", "CLAUDE.md")).read()
        assert claude_md.count(installer.BEGIN) == 1
        settings = json.load(open(os.path.join(d, ".claude", "settings.json")))
        for event in ("PreToolUse", "PostToolUse", "SessionStart"):
            ours = [e for e in settings["hooks"][event]
                    if installer.HOOK_MARKER in json.dumps(e)]
            assert len(ours) == 1, (event, settings["hooks"][event])
        agents = os.listdir(os.path.join(d, ".claude", "agents"))
        assert len(agents) == len(set(agents)) == 10
        assert inst.doctor()["ok"]
    finally:
        rm(d)


def test_clean_install_replaces_only_owned_content():
    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        inst.install()
        root = os.path.join(d, ".claude", "agentic-os")
        # stale content from an "older version" plus live state
        stale = write(os.path.join(root, "skills", "obsolete", "SKILL.md"), "old")
        con_path = os.path.join(root, "state", "queue.db")
        sys.path.insert(0, root)
        from runtime import queue
        con = queue.connect(con_path)
        queue.add(con, "task from the old installation")
        con.close()

        inst.install(clean=True)
        assert not os.path.exists(stale), "clean install kept a stale owned file"
        con = queue.connect(con_path)
        assert queue.stats(con)["total"] == 0, "clean install must reset state"
        con.close()
        assert_project_intact(d)
        assert inst.doctor()["ok"]
    finally:
        rm(d)


def test_update_preserves_state_and_user_config():
    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        inst.install()
        root = os.path.join(d, ".claude", "agentic-os")
        sys.path.insert(0, root)
        from runtime import queue
        con = queue.connect(os.path.join(root, "state", "queue.db"))
        queue.add(con, "work in progress")
        con.close()
        cfg = os.path.join(root, "config", "workflow.json")
        data = json.load(open(cfg))
        data["max_repair_attempts"] = 7
        write(cfg, json.dumps(data, indent=2))

        inst.install(update=True)
        con = queue.connect(os.path.join(root, "state", "queue.db"))
        assert queue.stats(con)["total"] == 1, "update wiped the queue"
        con.close()
        assert json.load(open(cfg))["max_repair_attempts"] == 7, "update clobbered user config"
        assert os.path.exists(cfg + ".new"), "the new config version should be offered"

        # and it must survive the update after that, and the one after that
        inst.install(update=True)
        inst.install(update=True)
        assert json.load(open(cfg))["max_repair_attempts"] == 7, \
            "a kept edit died on the second update"
        assert_project_intact(d)
    finally:
        rm(d)


def test_uninstall_removes_only_agentic_os():
    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        inst.install()
        inst.uninstall()
        assert not os.path.exists(os.path.join(d, ".claude", "agentic-os"))
        agents = os.listdir(os.path.join(d, ".claude", "agents"))
        assert agents == ["my-agent.md"], agents
        assert not os.path.exists(os.path.join(d, ".claude", "skills", "agentic-os"))
        claude_md = open(os.path.join(d, ".claude", "CLAUDE.md")).read()
        assert installer.BEGIN not in claude_md and "House rules" in claude_md
        settings = json.load(open(os.path.join(d, ".claude", "settings.json")))
        assert installer.HOOK_MARKER not in json.dumps(settings)
        assert settings["model"] == "opus"
        assert_project_intact(d)
    finally:
        rm(d)


def test_block_lands_in_the_repo_root_when_there_is_no_claude_md():
    """Claude Code reads <project>/CLAUDE.md - do not write a file nothing loads."""
    d = tmpdir()
    try:
        write(os.path.join(d, "package.json"), '{"name":"x"}')
        inst = installer.Install(d, quiet=True)
        inst.install()
        root_md = os.path.join(d, "CLAUDE.md")
        assert os.path.exists(root_md), "block must go to the repo-root CLAUDE.md"
        assert installer.BEGIN in open(root_md).read()
        assert not os.path.exists(os.path.join(d, ".claude", "CLAUDE.md"))
        assert inst.manifest()["claude_md"]["path"] == "CLAUDE.md"
        inst.uninstall()
        assert not os.path.exists(root_md), "a file we created solely for the block is removed"
    finally:
        rm(d)


def test_existing_root_claude_md_is_preserved():
    d = tmpdir()
    try:
        write(os.path.join(d, "package.json"), '{"name":"x"}')
        write(os.path.join(d, "CLAUDE.md"), "# Project rules\n\nNo emoji.\n")
        inst = installer.Install(d, quiet=True)
        inst.install()
        text = open(os.path.join(d, "CLAUDE.md")).read()
        assert "No emoji." in text and installer.BEGIN in text
        assert os.path.exists(os.path.join(d, "CLAUDE.md.aos-backup"))
        inst.uninstall()
        after = open(os.path.join(d, "CLAUDE.md")).read()
        assert "No emoji." in after and installer.BEGIN not in after
    finally:
        rm(d)


def test_detects_existing_installation():
    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        assert not inst.exists()
        inst.install()
        assert inst.exists()
        os.remove(inst.manifest_path)
        assert inst.exists(), "must detect an installation without a manifest"
    finally:
        rm(d)


def test_manifest_tracks_ownership():
    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        m = inst.install()
        assert m["install_id"] and m["version"] and m["schema"] == installer.SCHEMA
        assert len(m["files"]) > 90
        for rel in m["files"]:
            assert rel.startswith(".claude"), rel
        assert not inst._safe_to_delete(os.path.join(d, "src", "app.py"))
        assert not inst._safe_to_delete(os.path.join(d, ".claude", "settings.json"))
        assert not inst._safe_to_delete(os.path.join(d, ".claude", "agents", "my-agent.md"))
        assert inst._safe_to_delete(os.path.join(d, ".claude", "agentic-os", "runtime", "cli.py"))
        assert inst._safe_to_delete(os.path.join(d, ".claude", "agents", "aos-builder.md"))
    finally:
        rm(d)


def test_doctor_detects_a_broken_installation():
    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        inst.install()
        os.remove(os.path.join(d, ".claude", "agentic-os", "config", "guards.json"))
        res = inst.doctor()
        assert not res["ok"]
        assert any(not c["ok"] and c["check"] == "owned files present" for c in res["checks"])
    finally:
        rm(d)


def test_status_reports_only_real_state():
    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        assert inst.status() == {"installed": False, "project": os.path.abspath(d)}
        inst.install()
        st = inst.status()
        assert st["installed"] and st["skills_installed"] == 58
        assert len(st["agents"]) == 9
        assert st["queue"]["total"] == 0
        assert st["learning"] == {"champion_policies": 0, "challengers": 0, "observations": 0}
        assert st["adapter"]["test_command"] == "npm test"
    finally:
        rm(d)


def test_doctor_treats_config_edits_as_supported_not_broken():
    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        inst.install()
        cfg = os.path.join(d, ".claude", "agentic-os", "config", "auto.json")
        data = json.load(open(cfg))
        data["enforce_mode"] = "deny"
        write(cfg, json.dumps(data, indent=2))

        res = inst.doctor()
        assert res["ok"], [c for c in res["checks"] if not c["ok"]]
        note = [c for c in res["checks"] if c["check"] == "local config edits"]
        assert note and "auto.json" in note[0]["detail"], res["checks"]

        # a modified runtime file is still a real fault: update would overwrite it
        rt = os.path.join(d, ".claude", "agentic-os", "runtime", "router.py")
        write(rt, open(rt).read() + "\n# local hack\n")
        res2 = inst.doctor()
        assert not res2["ok"]
        assert any(not c["ok"] and c["check"] == "owned files unmodified"
                   for c in res2["checks"]), res2["checks"]
    finally:
        rm(d)


def test_installed_copy_does_not_drift_from_the_payload():
    """An install must be byte-identical to the payload it came from.

    Every other test in this suite exercises the DIST. None of them proved the
    INSTALLED copy behaves the same, which is the only thing a project runs.

    To be precise about what doctor already covers, measured rather than
    assumed: doctor DOES catch a locally modified install file, because it
    hashes owned files against the manifest. What neither doctor nor this test
    can catch is the other drift — an install that is faithful to the payload it
    came from while the payload has moved on. myjeweler sat at 1.1.0 against a
    1.7.0 dist for weeks reporting `doctor: healthy`. That one is a VERSION
    comparison, which is what `agentic-os drift` exists for.
    """
    import hashlib
    import subprocess

    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        inst.install()
        root = os.path.join(d, ".claude", "agentic-os")

        def sha(p):
            return hashlib.sha256(open(p, "rb").read()).hexdigest()

        # runtime/ and hooks/ are code: they must match the payload exactly.
        # config/ and state/ are deliberately excluded — config is user-tunable
        # and preserved across updates, state is generated.
        compared = 0
        for sub in ("runtime", "hooks"):
            src = os.path.join(DIST, "payload", sub)
            for name in sorted(os.listdir(src)):
                if not name.endswith(".py"):
                    continue
                got = os.path.join(root, sub, name)
                assert os.path.exists(got), "payload file missing from install: %s/%s" % (sub, name)
                assert sha(got) == sha(os.path.join(src, name)), \
                    "installed %s/%s differs from the payload" % (sub, name)
                compared += 1
        assert compared >= 10, "compared only %d files — the walk found almost " \
                               "nothing, so this proves nothing" % compared

        # and the installed CLI must actually run, from its own bin, naming
        # agents that exist in that project rather than bare roles
        out = subprocess.run([os.path.join(root, "bin", "aos"), "plan",
                              "migrate the authentication system to oauth across the "
                              "frontend and backend with a schema migration"],
                             capture_output=True, text=True, cwd=d)
        assert out.returncode == 0, out.stderr
        plan = json.loads(out.stdout)
        stages = plan["stages"]
        assert stages, "installed CLI planned no stages"
        for stage in stages:
            assert stage["dispatch"] == "aos-" + stage["agent"], stage
            assert os.path.exists(os.path.join(d, ".claude", "agents",
                                               stage["dispatch"] + ".md")), \
                "plan named %s, which is not installed in this project" % stage["dispatch"]
        assert inst.doctor()["ok"], inst.doctor()
        assert_project_intact(d)
    finally:
        rm(d)


def test_update_keeps_a_config_the_payload_never_shipped():
    """A config file the user created must survive an update that adds one.

    The guard read `recorded not in (None, sha(dp))`. `recorded is None` means
    the prior manifest never tracked this file — which is precisely the case
    where the user created it — and that spelling treated it as "not modified"
    and overwrote it. Shipping config/memory.json upstream on 2026-09-12
    destroyed a project's configured Obsidian vault path exactly this way.
    """
    d = project()
    try:
        inst = installer.Install(d, quiet=True)
        inst.install()
        root = os.path.join(d, ".claude", "agentic-os")
        mine = os.path.join(root, "config", "memory.json")

        # Simulate the real shape: an installation made BEFORE the payload
        # shipped this config. Dropping it from the manifest is what makes
        # `recorded` None on the next update — installing fresh always records
        # it, which is why the first version of this test could not fail.
        man = json.load(open(os.path.join(root, "manifest.json")))
        man["files"] = {k: v for k, v in man["files"].items()
                        if not k.endswith("config/memory.json")}
        write(os.path.join(root, "manifest.json"), json.dumps(man, indent=2))
        write(mine, '{"schema_version": 1, "vault_root": "/my/vault"}\n')

        inst.install(update=True)

        assert os.path.exists(mine), "update deleted a user-created config"
        got = json.load(open(mine))
        assert got["vault_root"] == "/my/vault", \
            "update overwrote a user-created config: %s" % got
        assert os.path.exists(mine + ".new"), \
            "the shipped version must still be offered alongside it"
    finally:
        rm(d)


def test_drift_reports_installs_that_are_behind():
    """The drift nothing else catches: faithful to an OLD payload.

    doctor hashes owned files against the manifest written when they were
    installed, so an install two versions behind is internally consistent and
    reports healthy. myjeweler sat at 1.1.0 against a 1.7.0 distribution for
    weeks, green throughout.
    """
    d = project()
    try:
        installer.Install(d, quiet=True).install()
        current = open(os.path.join(DIST, "payload", "VERSION")).read().strip()

        res = installer.drift([d])
        assert res["ok"] is True, res
        assert res["projects"][0]["state"] == "current", res
        assert res["distribution"] == current

        # Rewind it the way a real stale install looks. The manifest hash has to
        # move with the file: a genuinely old install is INTERNALLY CONSISTENT,
        # which is the whole reason doctor cannot see it. Editing VERSION alone
        # just makes doctor report a locally modified owned file, which is a
        # different (and already detected) problem.
        import hashlib
        root = os.path.join(d, ".claude", "agentic-os")
        vf = os.path.join(root, "VERSION")
        write(vf, "1.1.0\n")
        man = json.load(open(os.path.join(root, "manifest.json")))
        for key in man["files"]:
            if key.endswith("agentic-os/VERSION"):
                man["files"][key] = hashlib.sha256(open(vf, "rb").read()).hexdigest()
        write(os.path.join(root, "manifest.json"), json.dumps(man, indent=2))
        res = installer.drift([d])
        assert res["ok"] is False, "a version-behind install must not read as ok"
        assert res["projects"][0]["state"] == "BEHIND", res
        assert res["projects"][0]["installed"] == "1.1.0"

        # and doctor still says healthy — which is exactly why drift exists
        assert installer.Install(d, quiet=True).doctor()["ok"] is True

        missing = installer.drift([os.path.join(d, "nope")])
        assert missing["projects"][0]["state"] == "not installed", missing
    finally:
        rm(d)


def test_registry_build_rebuilds_the_project_library_too():
    """`aos registry build` must refresh the project index, not only the OS one.

    It rebuilt only the OS registry; the project index was written by the
    installer alone. So adding a project skill — or editing one's `agents:`
    frontmatter — left the router reading a stale index until the next install,
    and the symptom reads like a routing bug rather than a stale file.

    Runs against a real installation rather than the distribution: pointing the
    CLI at the payload writes a project-registry.json into it, which must never
    ship. That mistake broke eight other tests when this was first written.
    """
    import subprocess

    d = project()
    try:
        installer.Install(d, quiet=True).install()
        root = os.path.join(d, ".claude", "agentic-os")
        reg_path = os.path.join(root, "skills", "project-registry.json")

        def indexed():
            return set(json.load(open(reg_path))["skills"])

        assert "project/my-skill" in indexed(), "fixture skill missing after install"

        # a NEW skill, added after install, is invisible until a rebuild
        write(os.path.join(d, ".claude", "skills", "late-skill", "SKILL.md"),
              "---\nname: late-skill\ndescription: added after the install\n---\n\n%s\n"
              % ("word " * 60))
        assert "project/late-skill" not in indexed()

        out = subprocess.run([os.path.join(root, "bin", "aos"), "registry", "build"],
                             capture_output=True, text=True, cwd=d)
        assert out.returncode == 0, out.stderr
        got = json.loads(out.stdout)
        assert got["built"] > 0 and got["project"] > 0, got
        assert "project/late-skill" in indexed(), "rebuild did not pick up the new skill"
    finally:
        rm(d)


def test_deployed_installer_finds_the_distribution():
    """The copy inside a project has no payload; version/update/drift must still work."""
    import subprocess
    d = project()
    try:
        installer.Install(d, quiet=True).install()
        cli = os.path.join(d, ".claude", "agentic-os", "bin", "agentic-os")
        for cmd in ("version", "drift", "update", "doctor"):
            r = subprocess.run([cli, cmd], capture_output=True, text=True)
            assert r.returncode == 0, "%s failed: %s%s" % (cmd, r.stdout, r.stderr)
        assert installer.Install(d, quiet=True).doctor()["ok"] is True
    finally:
        rm(d)


def test_repeated_updates_do_not_grow_claude_md():
    d = project()
    try:
        installer.Install(d, quiet=True).install()
        path = installer.Install(d, quiet=True).claude_md_path()
        before = open(path).read()
        for _ in range(3):
            installer.Install(d, quiet=True).install(update=True)
        assert open(path).read() == before, "each update added blank lines to CLAUDE.md"
    finally:
        rm(d)


def test_plugin_wired_hooks_are_not_written_twice():
    # 1.8.5: an enabled agentic-os plugin already runs the hooks.
    assert installer.plugin_wired({"enabledPlugins": {"agentic-os@local": True}})
    assert not installer.plugin_wired({"enabledPlugins": {"agentic-os@local": False}})
    assert not installer.plugin_wired({"enabledPlugins": {"other@x": True}})
    assert not installer.plugin_wired({}) and not installer.plugin_wired([])
