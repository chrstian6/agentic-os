"""Session start reads the owner's memory from the vault: preference notes and the newest handoff."""
import json
import os

from helpers import rm, tmpdir, write
from test_context import _fresh, _run


def _configure(root, vault, **brief):
    p = os.path.join(root, "config", "memory.json")
    cfg = json.load(open(p))
    cfg["vault_root"] = vault
    cfg["brief"] = brief
    json.dump(cfg, open(p, "w"))


def test_session_start_injects_notes_and_newest_handoff_within_budget():
    d, root = _fresh()
    vault = tmpdir()
    try:
        write(os.path.join(vault, "KB", "Design Preferences.md"),
              "---\ntags: [design]\n---\n# Design Preferences\n\n- Apple HIG. Less is more.\n" + "x " * 900)
        write(os.path.join(vault, "Sessions", "2026-11-16 Handoff.md"), "# old\n")
        write(os.path.join(vault, "Sessions", "2026-11-22 Handoff.md"), "# State\nqueue fix in review\n")
        write(os.path.join(vault, "Sessions", "Template.md"), "# template, not a handoff\n")
        _configure(root, vault, notes=["KB/Design Preferences.md", "KB/Missing.md"],
                   handoff_dir="Sessions", max_chars=600)
        ctx = _run(root, "session_start.py", {"session_id": "S"})["hookSpecificOutput"]["additionalContext"]
        assert "Owner memory" in ctx and "Apple HIG. Less is more." in ctx, ctx
        assert "tags:" not in ctx, "frontmatter must be stripped"
        assert "2026-11-22 Handoff.md" in ctx and "queue fix in review" in ctx, ctx
        assert "2026-11-16" not in ctx and "Template" not in ctx
        start = ctx.index("Owner memory")
        assert len(ctx[start:]) <= 600, len(ctx[start:])
    finally:
        rm(d)
        rm(vault)


def test_no_vault_no_brief():
    d, root = _fresh()
    try:
        ctx = _run(root, "session_start.py", {"session_id": "S"})["hookSpecificOutput"]["additionalContext"]
        assert "Owner memory" not in ctx
    finally:
        rm(d)


def test_a_broken_brief_config_is_logged_not_silent():
    d, root = _fresh()
    vault = tmpdir()
    try:
        _configure(root, vault, notes=[], handoff_dir="", max_chars="abc")
        out = _run(root, "session_start.py", {"session_id": "S"})
        assert out and "Owner memory" not in out["hookSpecificOutput"]["additionalContext"]
        log = os.path.join(root, "state", "hook-errors.log")
        assert os.path.exists(log) and "vault.session_brief" in open(log).read()
    finally:
        rm(d)
        rm(vault)


def test_budget_counts_the_header_with_a_long_vault_path():
    d, root = _fresh()
    vault = os.path.join(tmpdir(), "a-very-long-vault-folder-name-" + "x" * 120)
    try:
        write(os.path.join(vault, "KB", "P.md"), "# P\n" + "word " * 400)
        _configure(root, vault, notes=["KB/P.md"], handoff_dir="", max_chars=400)
        ctx = _run(root, "session_start.py", {"session_id": "S"})["hookSpecificOutput"]["additionalContext"]
        start = ctx.find("Owner memory")
        assert start >= 0 and len(ctx[start:]) <= 400, len(ctx[start:])
    finally:
        rm(d)
        rm(os.path.dirname(vault))
