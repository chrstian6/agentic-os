"""Installation must not depend on one ecosystem."""
import os
import sys

from helpers import DIST, rm, tmpdir, write

sys.path.insert(0, os.path.join(DIST, "installer"))
import installer  # noqa: E402
from runtime import adapter  # noqa: E402

FIXTURES = {
    "frontend-ts": {
        "package.json": '{"name":"web","dependencies":{"next":"14.1.0","react":"18.2.0"},'
                        '"devDependencies":{"vitest":"1.2.0","playwright":"1.4.0"},'
                        '"scripts":{"test":"vitest run","build":"next build","lint":"eslint ."}}',
        "pnpm-lock.yaml": "lockfileVersion: 6.0\n",
        "app/page.tsx": "export default function Page(){return <main/>}\n",
        ".github/workflows/ci.yml": "on: push\n",
        "expect": {"languages": ["javascript"], "frontend": True, "frameworks": ["next.js", "react"],
                   "ci": ["github-actions"]},
    },
    "backend-python": {
        "pyproject.toml": '[project]\nname="api"\ndependencies=["fastapi","sqlalchemy","psycopg"]\n'
                          '[tool.ruff]\n[tool.pytest.ini_options]\n',
        "app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        "tests/test_main.py": "def test_ok():\n    assert True\n",
        "expect": {"languages": ["python"], "backend": True, "frameworks": ["fastapi", "sqlalchemy"],
                   "test_command": "pytest"},
    },
    "compiled-go": {
        "go.mod": "module example.com/svc\n\ngo 1.22\n",
        "main.go": "package main\n\nfunc main() {}\n",
        "expect": {"languages": ["go"], "backend": True, "test_command": "go test ./..."},
    },
    "fullstack-mixed": {
        "package.json": '{"name":"app","workspaces":["web"],"dependencies":{"react":"18"},'
                        '"scripts":{"test":"jest"}}',
        "requirements.txt": "django==5.0\npsycopg2\npytest\n",
        "turbo.json": "{}",
        "Cargo.toml": "[package]\nname = \"engine\"\n",
        "expect": {"monorepo": True, "frontend": True},
    },
}


def build(name, spec):
    d = tmpdir()
    for rel, content in spec.items():
        if rel == "expect":
            continue
        write(os.path.join(d, rel), content)
    return d


def test_adapter_detects_each_ecosystem():
    for name, spec in FIXTURES.items():
        d = build(name, spec)
        try:
            got = adapter.detect(d)
            for key, want in spec["expect"].items():
                if isinstance(want, list):
                    missing = [w for w in want if w not in got[key]]
                    assert not missing, "%s: %s missing %s (got %s)" % (name, key, missing, got[key])
                else:
                    assert got[key] == want, "%s: %s = %r, wanted %r" % (name, key, got[key], want)
        finally:
            rm(d)


def test_installs_into_every_ecosystem():
    for name, spec in FIXTURES.items():
        d = build(name, spec)
        try:
            inst = installer.Install(d, quiet=True)
            inst.install()
            res = inst.doctor()
            assert res["ok"], "%s: %s" % (name, [c for c in res["checks"] if not c["ok"]])
            st = inst.status()
            assert st["skills_installed"] == 51 and len(st["agents"]) == 9, (name, st)
            # the project's own files are untouched
            for rel in spec:
                if rel != "expect":
                    assert os.path.exists(os.path.join(d, rel)), (name, rel)
        finally:
            rm(d)


def test_no_current_project_stack_leaks_into_the_distribution():
    """The portable payload must not hardcode this machine's project."""
    payload = os.path.join(DIST, "payload")
    banned = ("/Users/christian", "gembid", "myjeweler")
    for dirpath, _dirs, files in os.walk(payload):
        for f in files:
            if not f.endswith((".py", ".md", ".json")):
                continue
            p = os.path.join(dirpath, f)
            text = open(p, errors="replace").read().lower()
            for b in banned:
                assert b not in text, "%s leaks %r" % (p, b)
