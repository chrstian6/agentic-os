"""The Obsidian vault, linked to the runtime in both directions.

Owner-directed 2026-09-12: "link the obsidian vault to our agentic-os",
bidirectional, built ON TOP of .claude/rules/memory.md rather than replacing it.

── WHAT THIS DOES AND DELIBERATELY DOES NOT DO ───────────────────────────────
Agentic OS owns routing and learning. The vault owns memory. The link is two
narrow things:

  IN   an index of note TITLES AND PATHS, so `aos route` can name the note
       worth reading for a task, alongside the skills it already picks.
  OUT  `aos learn observe` mirrors the observation into the vault's own
       Agent Learnings folder, so what the runtime learns survives the
       state/learning.db it would otherwise die in.

⚠️ THE INDEX HOLDS NO NOTE BODIES, on purpose. Copying content here would make
a second source of truth that is stale within a day, and .claude/rules/memory.md
is explicit that content reads go through the obsidian-memory MCP. So this
answers "which note?" and the MCP answers "what does it say?". Keeping that
split is what lets the vault be edited in Obsidian without this ever lying —
the worst a stale index can do is miss a new note, never misquote an old one.
"""
import os
import re
import time

from . import paths, util

DEFAULT_CONFIG = {
    "vault_root": "",
    "project_folder": "",
    "read": {"folders": [], "max_notes": 2000},
    "write": {"folder": "Agent Learnings", "enabled": False},
}

# Words carried by nearly every note in a software vault. Left in the index but
# ignored when scoring, or "the" and "design" would rank everything equally.
STOPWORDS = frozenset("""
a an and are as at be by for from has have how in into is it its of on or that the
this to was what when where which with we our us you your not no do does done
note notes doc docs page md project projects
""".split())


def load_config():
    """Read config/memory.json. Absent or malformed is not an error — the link
    is optional, and a runtime that refuses to start without a vault would make
    Agentic OS unusable on any machine that has no Obsidian."""
    cfg = util.load_json(paths.config("memory.json"), default=None)
    if not isinstance(cfg, dict):
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update({k: v for k, v in cfg.items() if not k.startswith("_")})
    return merged


def project_dir(cfg=None):
    """Absolute path to the vault's project folder, or "" when unconfigured."""
    cfg = cfg or load_config()
    root = (cfg.get("vault_root") or "").strip()
    if not root:
        return ""
    folder = (cfg.get("project_folder") or "").strip()
    return os.path.join(root, folder) if folder else root


def _excerpt(path, limit):
    """A note's text without frontmatter, whitespace collapsed, cut to `limit` chars."""
    try:
        with open(path, errors="replace") as fh:
            text = fh.read()
    except (IOError, OSError):
        return ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        text = text[end + 4:] if end != -1 else text
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:max(limit - 3, 0)].rstrip() + "..."


def session_brief(cfg=None):
    """Owner memory for session start: named notes plus the newest handoff, under a budget.

    Config `brief` in memory.json: {"notes": [vault-relative paths], "handoff_dir": folder
    of date-named handoffs, "max_chars": total budget}. Off when vault_root is empty. The
    note bodies are read live from disk, never cached, so the vault stays the one source.
    """
    cfg = cfg or load_config()
    root = (cfg.get("vault_root") or "").strip()
    brief = cfg.get("brief") or {}
    if not root or not os.path.isdir(root) or not brief:
        return ""
    budget = int(brief.get("max_chars", 1500))
    parts = []
    hdir = os.path.join(root, brief.get("handoff_dir") or "")
    if brief.get("handoff_dir") and os.path.isdir(hdir):
        names = sorted(n for n in os.listdir(hdir) if n.endswith(".md"))
        if names:
            path = os.path.join(hdir, names[-1])
            parts.append((path, "Newest handoff %s (read it in full before new work)" % path,
                          budget // 2))
    notes = [os.path.join(root, n) for n in brief.get("notes", [])]
    notes = [n for n in notes if os.path.isfile(n)]
    for n in notes:
        share = (budget - sum(x[2] for x in parts)) // max(len(notes), 1)
        parts.append((n, os.path.splitext(os.path.basename(n))[0], share))
    out = []
    for path, label, share in parts:
        room = share - len(label) - 3
        if room > 40:
            out.append("%s: %s" % (label, _excerpt(path, room)))
    return ("Owner memory (vault %s): " % root + " | ".join(out)) if out else ""


def is_linked(cfg=None):
    """True only when the configured vault actually exists on this machine."""
    d = project_dir(cfg)
    return bool(d) and os.path.isdir(d)


def _title_of(path, text):
    """First H1 wins; the filename is the fallback. Obsidian users title notes
    with the filename far more often than with an H1, so neither alone is
    reliable."""
    for line in text.split("\n", 40)[:40]:
        if line.startswith("# "):
            return line[2:].strip()
    return os.path.splitext(os.path.basename(path))[0]


def _tokens(s):
    return {w for w in re.split(r"[^a-z0-9]+", s.lower()) if len(w) > 2 and w not in STOPWORDS}


def index(cfg=None):
    """Walk the configured folders and return a list of note descriptors.

    Reads each file's HEAD only — enough for the title and headings, which is
    all discovery needs. A vault can hold thousands of notes and this runs on
    demand; reading whole bodies would make it slow enough that nobody would.
    """
    cfg = cfg or load_config()
    base = project_dir(cfg)
    if not base or not os.path.isdir(base):
        return []
    read_cfg = cfg.get("read") or {}
    folders = read_cfg.get("folders") or []
    cap = int(read_cfg.get("max_notes") or 2000)

    notes = []
    for rank, folder in enumerate(folders):
        start = os.path.join(base, folder)
        if not os.path.isdir(start):
            continue
        for dirpath, _dirs, files in os.walk(start):
            for name in sorted(files):
                if not name.endswith(".md") or len(notes) >= cap:
                    continue
                full = os.path.join(dirpath, name)
                try:
                    with open(full, "r", errors="replace") as fh:
                        head = fh.read(4096)
                except OSError:
                    continue
                headings = [
                    ln.lstrip("# ").strip()
                    for ln in head.split("\n")
                    if ln.startswith("#")
                ][:12]
                notes.append({
                    # Vault-relative, so the path is what a human pastes into
                    # Obsidian and what the MCP takes.
                    "path": os.path.relpath(full, base).replace(os.sep, "/"),
                    "folder": folder,
                    # Authority order comes from the config's folder order: a
                    # Decision binds harder than a Gotcha, which binds harder
                    # than a Learning. Lower is stronger.
                    "authority": rank,
                    "title": _title_of(full, head),
                    "headings": headings,
                })
    return notes


def build(cfg=None):
    """Write the index to state/vault-index.json and return it."""
    cfg = cfg or load_config()
    notes = index(cfg)
    payload = {
        "schema_version": 1,
        "generated_at": int(time.time()),
        "vault": project_dir(cfg),
        "count": len(notes),
        "notes": notes,
    }
    util.save_json(paths.state("vault-index.json"), payload)
    return payload


def load_index():
    return util.load_json(paths.state("vault-index.json"), default={"notes": []})


def search(task, limit=3, idx=None):
    """Return the notes most likely to bind on this task.

    Scoring is title-and-heading overlap, tie-broken by folder authority. It is
    deliberately dumb: the index has no bodies to be clever with, and a wrong
    guess here costs one line of output, not a wrong action. The MCP's semantic
    search is the right tool once you know roughly where to look — this exists
    to make "look in the vault at all" the default rather than an afterthought.
    """
    idx = idx if idx is not None else load_index()
    wanted = _tokens(task or "")
    if not wanted:
        return []
    scored = []
    for note in idx.get("notes", []):
        hay = _tokens(note.get("title", "")) | _tokens(" ".join(note.get("headings", [])))
        overlap = len(wanted & hay)
        if overlap:
            # Authority breaks ties only — a strongly-matching Learning should
            # still outrank a barely-matching Decision.
            scored.append((overlap, -int(note.get("authority", 9)), note))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [note for _score, _auth, note in scored[:limit]]


def note_path_for(slug, when=None, cfg=None):
    """Where an outgoing learning note belongs.

    `<date>-<slug>.md` matches the vault's existing convention, so notes written
    by the runtime sort alongside notes written by hand instead of forming a
    visibly separate species.
    """
    cfg = cfg or load_config()
    base = project_dir(cfg)
    if not base:
        return ""
    folder = ((cfg.get("write") or {}).get("folder") or "Agent Learnings")
    day = time.strftime("%Y-%m-%d", time.localtime(when or time.time()))
    safe = re.sub(r"[^a-z0-9]+", "-", (slug or "observation").lower()).strip("-")[:60]
    return os.path.join(base, folder, "%s-%s.md" % (day, safe or "observation"))


def write_enabled(cfg=None):
    cfg = cfg or load_config()
    return bool((cfg.get("write") or {}).get("enabled")) and is_linked(cfg)


def write_note(slug, body, when=None, cfg=None):
    """Mirror an observation into the vault. Returns the path written, or "".

    Never raises: a memory write failing must not fail the work that produced
    the memory. That is the same posture `emitActivity` takes in the product
    itself, and for the same reason.
    """
    cfg = cfg or load_config()
    if not write_enabled(cfg):
        return ""
    path = note_path_for(slug, when=when, cfg=cfg)
    if not path:
        return ""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(body)
        return path
    except OSError as exc:
        print("[vault] could not write %s: %s" % (path, exc))
        return ""


def render_note(text, task=None, when=None):
    """The note body. Frontmatter first, so Obsidian's own tooling sees it."""
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(when or time.time()))
    lines = [
        "---",
        "source: agentic-os",
        "kind: agent-learning",
        "created: %s" % stamp,
        "---",
        "",
        "# %s" % (text.strip().split("\n")[0][:80] or "Observation"),
        "",
        text.strip(),
        "",
    ]
    if task:
        lines += ["## Task in hand", "", task.strip(), ""]
    lines += [
        "> Written by `aos learn observe`. The runtime's own copy is in",
        "> `state/learning.db`; this is the durable one.",
        "",
    ]
    return "\n".join(lines)


def selftest():
    """Drive the real call sites against a synthetic vault.

    ⚠️ THROUGH THE CALL SITE, WITH ASYMMETRIC FIXTURES — both required by
    .claude/rules/verification.md, which records three guards that shipped
    unable to fail. A symmetric fixture lets an argument reversal through, and
    a direct-value test never exercises the path the CLI actually takes. So the
    Decision note here is the one that must win, and it wins on BOTH score and
    authority; the Gotcha is deliberately the weaker match.
    """
    import json as _json
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="aos-vault-selftest-")
    failures = []
    try:
        proj = os.path.join(tmp, "Vault", "Proj")
        for folder, name, text in [
            ("Decisions", "Decision - neon http driver.md",
             "# Decision - neon http driver\n\n## Batching transactions\n"),
            ("Gotchas", "tailwind tokens.md",
             "# Tailwind bare HSL tokens\n\n## Portal scope\n"),
            ("Agent Learnings", "old note.md", "# Something unrelated entirely\n"),
        ]:
            d = os.path.join(proj, folder)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "w") as fh:
                fh.write(text)

        cfg = {
            "vault_root": os.path.join(tmp, "Vault"),
            "project_folder": "Proj",
            "read": {"folders": ["Decisions", "Gotchas", "Agent Learnings"], "max_notes": 50},
            "write": {"folder": "Agent Learnings", "enabled": True},
        }

        notes = index(cfg)
        if len(notes) != 3:
            failures.append("index found %d notes, expected 3" % len(notes))

        # Positive assertion that the walk REACHED something, not merely that
        # it did not crash — a zero-note index would otherwise "pass".
        if not any(n["folder"] == "Decisions" for n in notes):
            failures.append("index never reached the Decisions folder")

        hits = search("neon driver transactions", limit=2, idx={"notes": notes})
        if not hits:
            failures.append("search returned nothing for a term that is present")
        elif "neon" not in hits[0]["title"].lower():
            failures.append("search ranked '%s' above the Decision" % hits[0]["title"])

        # The negative case: a term in NO note must return nothing rather than
        # the first note it happens to walk past.
        if search("kubernetes helm", limit=2, idx={"notes": notes}):
            failures.append("search invented a match for an absent term")

        written = write_note("selftest observation", render_note("hello", task="t"), cfg=cfg)
        if not written or not os.path.isfile(written):
            failures.append("write_note did not produce a file")
        elif not os.path.basename(written).endswith("-selftest-observation.md"):
            failures.append("write_note named the file '%s'" % os.path.basename(written))

        # Disabled write must be a no-op, or "enabled: false" means nothing.
        off = dict(cfg, write={"folder": "Agent Learnings", "enabled": False})
        if write_note("should not exist", "x", cfg=off):
            failures.append("write_note wrote despite write.enabled=false")

        # An unconfigured vault must degrade to silence, never raise: Agentic OS
        # has to run on a machine with no Obsidian at all.
        empty = {"vault_root": "", "project_folder": ""}
        if index(empty) != [] or is_linked(empty) or write_note("x", "y", cfg=empty):
            failures.append("an unconfigured vault was not inert")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    _json  # noqa: B018 - imported for parity with the CLI's output path
    return {"ok": not failures, "failures": failures}
