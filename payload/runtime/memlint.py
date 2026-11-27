"""Memory lint (Karpathy's LLM-wiki "lint" pass): find facts in instruction files that the
tree has moved past. Three mechanical checks, each conservative so a clean file stays quiet:

- path:    a backticked repo path whose first folder exists but whose file does not
- count:   "N skills" that disagrees with the installed registry
- version: an agentic-os version on the same line as "agentic"/"aos" that is not VERSION
"""
import glob
import os
import re

from . import paths

TICK = re.compile(r"`([^`\s]+)`")
# a claim about the library size, not "load 3 skills max"
COUNT = re.compile(r"\b(\d+) skills (?:live|are installed|installed|in the library)\b", re.I)
VERSION = re.compile(r"\bversion\b\W{0,3}(\d+\.\d+\.\d+)", re.I)
OS_NAME = re.compile(r"agentic|\baos\b", re.I)
SKIP = set("<>*{}$~?[]|")
# a line recording that a file is gone is history, not a stale claim
GONE = re.compile(r"\b(delet|remov|retir|gone|supersed|no longer|was renamed|record only)", re.I)


def _path_problem(token, project):
    if any(c in SKIP for c in token) or "://" in token or "/" not in token:
        return None
    rel = re.sub(r"^\./", "", re.sub(r":\d+(-\d+)?$", "", token))
    first = rel.split("/")[0]
    if not first or not os.path.isdir(os.path.join(project, first)):
        return None  # another repo, a placeholder, or a path outside this tree
    return None if os.path.exists(os.path.join(project, rel.rstrip("/"))) else rel


def lint(files, project, skill_count=None, version=None):
    problems = []
    for f in files:
        try:
            lines = open(f, encoding="utf-8").read().splitlines()
        except (IOError, OSError, UnicodeDecodeError):
            continue
        history = False  # inside a section whose heading marks it superseded / a record
        fence = False    # "# comment" inside a code block is not a heading
        for n, line in enumerate(lines, 1):
            where = "%s:%d" % (os.path.relpath(f, project), n)
            if line.lstrip().startswith("```"):
                fence = not fence
            if line.startswith("#") and not fence:
                history = bool(GONE.search(TICK.sub("", line)))
            near = TICK.sub("", line + " " + (lines[n] if n < len(lines) else ""))
            for tok in ([] if history or GONE.search(near) else TICK.findall(line)):
                bad = _path_problem(tok, project)
                if bad:
                    problems.append({"kind": "path", "where": where, "detail": "%s does not exist" % bad})
            if skill_count is not None:
                for m in COUNT.finditer(line):
                    if int(m.group(1)) != skill_count:
                        problems.append({"kind": "count", "where": where,
                                         "detail": "says %s skills, registry has %d" % (m.group(1), skill_count)})
            if version and OS_NAME.search(line):
                for v in VERSION.findall(line):
                    if v != version:
                        problems.append({"kind": "version", "where": where,
                                         "detail": "says %s, installed %s" % (v, version)})
    return problems


def default_files(project):
    out = [os.path.join(project, "CLAUDE.md")]
    out += sorted(glob.glob(os.path.join(project, ".claude", "rules", "*.md")))
    return [f for f in out if os.path.isfile(f)]


def installed_facts(root=None):
    root = root or paths.install_root()
    try:
        version = open(os.path.join(root, "VERSION")).read().strip()
    except (IOError, OSError):
        version = None
    # same count the installer writes into CLAUDE.md: SKILL.md files under skills/
    count = sum(1 for _dp, _d, fs in os.walk(os.path.join(root, "skills")) if "SKILL.md" in fs) or None
    return count, version
