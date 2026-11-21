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


def turn_path(root, session_id=None):
    """Per-session turn file. One global file let concurrent sessions clobber each
    other's plan and measure each other's tool calls."""
    if not session_id:
        return os.path.join(root, "state", "current_turn.json")
    safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_")[:80] or "anon"
    return os.path.join(root, "state", "turns", safe + ".json")


def read_turn(root, session_id=None):
    try:
        with open(turn_path(root, session_id)) as fh:
            return json.load(fh)
    except (IOError, OSError, ValueError):
        return None


def write_turn(root, session_id, turn):
    path = turn_path(root, session_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w") as fh:
            json.dump(turn, fh)
        os.replace(path + ".tmp", path)
    except (IOError, OSError):
        pass


def drop_turn(root, session_id=None):
    try:
        os.remove(turn_path(root, session_id))
    except OSError:
        pass


def session_events(root, session_id=None, since=0, agent_id=None, main_only=False):
    """Tool events for one session (and optionally one subagent) since a timestamp."""
    out = []
    try:
        with open(os.path.join(root, "state", "events.jsonl")) as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("at", 0) < since:
                    continue
                if session_id and rec.get("session") not in (session_id, None):
                    continue
                if agent_id and rec.get("agent_id") != agent_id:
                    continue
                if main_only and rec.get("agent_id"):
                    continue
                out.append(rec)
    except (IOError, OSError):
        pass
    return out


def payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()
