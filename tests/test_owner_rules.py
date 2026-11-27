"""Owner rules: brief ASD-STE100 replies on every prompt; ideas and bugs are discussed before any edit."""
import json
import os

from helpers import rm
from runtime import intent
from test_context import _fresh, _run


def _ctx(root, sid, prompt):
    out = _run(root, "user_prompt_submit.py", {"session_id": sid, "prompt": prompt})
    return out["hookSpecificOutput"]["additionalContext"] if out else ""


def _write(root, sid, path):
    return _run(root, "pre_tool_use.py", {"session_id": sid, "tool_name": "Write",
                                          "tool_input": {"file_path": path, "content": "x"}})


def test_intent_classifies_discuss_and_go():
    assert intent.is_discuss("i have an idea: what if the queue had priorities")
    assert intent.is_discuss("the login page is broken on safari")
    assert intent.is_discuss("improve our design skills, research and remember")
    assert not intent.is_discuss("fix the typo in the footer text")
    assert not intent.is_discuss("go ahead and fix the login bug")
    assert not intent.is_discuss("ensure the queue respects fifo order")
    # a go word inside a report is not an order
    assert intent.is_discuss("the bug: go back button is broken")
    assert intent.is_discuss("can we go over an idea?")
    assert intent.is_discuss("I approved the design but there's a bug")
    assert intent.is_go("go on the HIG design proposal")
    assert intent.is_go("ok, go ahead") and intent.is_go("Go")
    # plain build orders are not discussion
    for order in ("add a ? to the label", "rename the issues tab to tickets",
                  "Add maybe/no options to the RSVP form", "can you add a footer link?",
                  "search fails when query has a ? char, fix it", "Improve the error message for login",
                  "Please update the go.mod file", "Fix: the Go-to-top button overlaps the footer"):
        assert not intent.is_discuss(order), order
    # real reports and negated go words are discussion
    for report in ("the bid button doesn't work on mobile", "payouts are failing for ruby jewelers",
                   "don't go there, just discuss the bug",
                   "we should not go ahead yet, what are the trade-offs?"):
        assert intent.is_discuss(report), report
    # a neutral reply keeps the state; only go or an order changes it
    assert intent.classify("no", previous=True) and intent.classify("wait", previous=True)
    assert not intent.classify("go", previous=True)
    assert not intent.classify("fix the typo in the footer text", previous=True)


def test_every_prompt_carries_the_voice_rule():
    d, root = _fresh()
    try:
        assert "ASD-STE100" in _ctx(root, "S", "fix the typo in the footer text")
        assert "step-by-step" in _ctx(root, "S", "fix the typo in the footer text")
        p = os.path.join(root, "config", "auto.json")
        cfg = json.load(open(p)); cfg["voice"] = False; json.dump(cfg, open(p, "w"))
        assert "ASD-STE100" not in _ctx(root, "S", "fix the typo in the footer text")
    finally:
        rm(d)


def test_discuss_turn_blocks_edits_until_go():
    d, root = _fresh()
    try:
        ctx = _ctx(root, "S", "i have an idea: what if the queue had priorities?")
        assert "DISCUSS mode" in ctx, ctx[:400]
        out = _write(root, "S", "/Users/someone/project/app.py")
        assert out and out["hookSpecificOutput"]["permissionDecision"] == "deny", out
        assert "go" in out["hookSpecificOutput"]["permissionDecisionReason"]
        assert _write(root, "S", "/tmp/research-notes.md") is None      # scratch stays open
        out = _write(root, "S", "/tmp/../Users/someone/project/app.py")  # no traversal around it
        assert out and out["hookSpecificOutput"]["permissionDecision"] == "deny", out
        _ctx(root, "S", "no")                                            # "no" keeps the gate
        out = _write(root, "S", "/Users/someone/project/app.py")
        assert out and out["hookSpecificOutput"]["permissionDecision"] == "deny", out
        ctx = _ctx(root, "S", "go")                                      # the owner's go signal
        assert "DISCUSS mode" not in ctx
        assert _write(root, "S", "/Users/someone/project/app.py") is None
    finally:
        rm(d)


def test_build_order_is_not_gated():
    d, root = _fresh()
    try:
        ctx = _ctx(root, "S", "fix the typo in the footer text")
        assert "DISCUSS mode" not in ctx
        assert _write(root, "S", "/Users/someone/project/footer.py") is None
    finally:
        rm(d)


def test_gate_can_be_turned_off():
    d, root = _fresh()
    try:
        p = os.path.join(root, "config", "auto.json")
        cfg = json.load(open(p)); cfg["discuss_gate"] = "off"; json.dump(cfg, open(p, "w"))
        assert "DISCUSS mode" not in _ctx(root, "S", "what if the queue had priorities?")
        assert _write(root, "S", "/Users/someone/project/app.py") is None
    finally:
        rm(d)


def test_short_discuss_prompt_is_gated_too():
    d, root = _fresh()
    try:
        assert "DISCUSS mode" in _ctx(root, "S", "bug?")
        out = _write(root, "S", "/Users/someone/project/app.py")
        assert out and out["hookSpecificOutput"]["permissionDecision"] == "deny", out
        _ctx(root, "S", "go")
        assert _write(root, "S", "/Users/someone/project/app.py") is None
    finally:
        rm(d)
