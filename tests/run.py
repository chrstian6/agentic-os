#!/usr/bin/env python3
"""Agentic OS test runner. No framework: `python3 tests/run.py [pattern]`."""
import glob
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(DIST, "payload"))
sys.path.insert(0, HERE)
os.environ.setdefault("AOS_HOME", os.path.join(DIST, "payload"))


PAYLOAD = os.path.join(DIST, "payload")


def _reset_runtime():
    """Installer tests import a runtime from a temp installation; undo that leak."""
    for name in [k for k in list(sys.modules) if k == "runtime" or k.startswith("runtime.")]:
        mod = sys.modules[name]
        path = getattr(mod, "__file__", "") or ""
        if not path.startswith(PAYLOAD):
            del sys.modules[name]
    sys.path[:] = [p for p in sys.path if ".claude/agentic-os" not in p]
    if sys.path[0] != PAYLOAD:
        sys.path.insert(0, PAYLOAD)
    os.environ["AOS_HOME"] = PAYLOAD


def main(pattern=None):
    files = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    if pattern:
        files = [f for f in files if pattern in os.path.basename(f)]
    passed = failed = 0
    failures = []
    for path in files:
        name = os.path.basename(path)[:-3]
        _reset_runtime()
        mod = __import__(name)
        for attr in sorted(dir(mod)):
            if not attr.startswith("test_"):
                continue
            fn = getattr(mod, attr)
            try:
                _reset_runtime()
                fn()
                passed += 1
                print("  ok   %s.%s" % (name, attr))
            except Exception:
                failed += 1
                failures.append((name, attr, traceback.format_exc()))
                print("  FAIL %s.%s" % (name, attr))
    print("\n%d passed, %d failed" % (passed, failed))
    for name, attr, tb in failures:
        print("\n--- %s.%s\n%s" % (name, attr, tb))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
