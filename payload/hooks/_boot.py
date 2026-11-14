"""Shared hook bootstrap: locate the installation and import the runtime safely."""
import json
import os
import sys


def shadowed(root):
    """A project with its own install runs its own hooks; this one must stand down.

    Measured: a global install and a project install both fired, so every prompt carried
    two plans and every tool call paid for two hook sets.
    """
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if not proj:
        return False
    local = os.path.join(proj, ".claude", "agentic-os")
    return os.path.isdir(os.path.join(local, "hooks")) and \
        os.path.realpath(local) != os.path.realpath(root)


def load():
    explicit = os.environ.get("AOS_HOME")
    root = explicit or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # An explicit AOS_HOME is the caller choosing this installation; never stand down then.
    if not explicit and shadowed(root):
        sys.exit(0)
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("AOS_HOME", root)
    return root


def is_delegation(tool_name):
    """The subagent tool is "Agent" now, "Task" in older Claude Code."""
    return tool_name in ("Agent", "Task")


def payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()
