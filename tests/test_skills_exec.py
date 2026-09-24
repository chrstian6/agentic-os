"""Skill-level executable tests, run as part of the distribution suite."""
import os
import subprocess
import sys

from helpers import PAYLOAD

SKILL_TESTS = [
    os.path.join(PAYLOAD, "skills", "builder", "anti-ai-slop", "tests", "test_check.py"),
    os.path.join(PAYLOAD, "skills", "builder", "design-taste", "tests", "test_check.py"),
]


def test_skill_test_suites_pass():
    for path in SKILL_TESTS:
        assert os.path.exists(path), path
        r = subprocess.run([sys.executable, path], capture_output=True, text=True)
        assert r.returncode == 0, "%s failed:\n%s%s" % (path, r.stdout, r.stderr)


def test_anti_slop_checker_is_wired_to_the_skill():
    skill = open(os.path.join(PAYLOAD, "skills", "builder", "anti-ai-slop", "SKILL.md")).read()
    assert "tells" in skill.lower()
    check = os.path.join(PAYLOAD, "skills", "builder", "anti-ai-slop", "check.py")
    r = subprocess.run([sys.executable, check, check], capture_output=True, text=True)
    assert r.returncode in (0, 1) and "reports" in r.stdout
