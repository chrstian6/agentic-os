"""`aos` - the Agentic OS runtime command line. Everything prints JSON."""
import argparse
import json
import os
import sys
import tempfile

if __package__ in (None, ""):  # allow `python3 runtime/cli.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "runtime"

from . import (adapter, artifacts, classify, evals, guards, learning, memlint, metrics,  # noqa: E402
               models, paths, queue, registry, router, util, vault, workflow)


def out(obj):
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def _policies():
    try:
        con = learning.connect()
        return learning.active(con)
    except Exception:
        return []


def _adapter():
    try:
        return adapter.load(paths.p("adapter.json"))
    except Exception:
        return {}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="aos", description="Agentic OS runtime")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("classify", help="difficulty + risk + workflow depth")
    p.add_argument("task")
    p.add_argument("--files", type=int, default=0)

    p = sub.add_parser("route", help="select the minimum sufficient skill set")
    p.add_argument("task")
    p.add_argument("--agent")
    p.add_argument("--budget", type=int, default=6)

    # The header a writer dispatch must open with (guard-delegation.py checks it).
    p = sub.add_parser("brief", help="MISSION line + one `aos skills show` line per routed skill")
    p.add_argument("mission")
    p.add_argument("--agent", required=True)
    p.add_argument("--budget", type=int, default=6)

    p = sub.add_parser("plan", help="full execution plan for a task")
    p.add_argument("task")
    p.add_argument("--files", type=int, default=0)

    p = sub.add_parser("guard", help="evaluate a shell command against the guards")
    p.add_argument("command")

    p = sub.add_parser("guard-path", help="evaluate a write to a path")
    p.add_argument("path")

    p = sub.add_parser("audit", help="completion audit")
    p.add_argument("task_id", type=int)
    p.add_argument("--criteria", default="")

    p = sub.add_parser("queue")
    p.add_argument("action", choices=["add", "list", "ready", "set", "get", "stats", "record", "stale", "cancel-stale", "plan"])
    p.add_argument("args", nargs="*")
    p.add_argument("--depends-on", default="")
    p.add_argument("--body", default="")

    p = sub.add_parser("mode", help="show or set agent mode: multi (delegate) | single (all in one)")
    p.add_argument("value", nargs="?", choices=list(workflow.MODES))

    p = sub.add_parser("artifact")
    p.add_argument("action", choices=["write", "read"])
    p.add_argument("task_id", type=int)
    p.add_argument("agent", nargs="?")
    p.add_argument("--json", default="{}")

    p = sub.add_parser("learn")
    p.add_argument("action", choices=["observe", "patterns", "hypothesize", "propose", "active",
                                      "challengers", "compare", "promote", "reject", "rollback",
                                      "history", "record-metric", "cycle", "tune"])
    p.add_argument("args", nargs="*")
    p.add_argument("--json", default="{}")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="learn cycle: report what it would do, promote nothing")
    p.add_argument("--apply", action="store_true",
                   help="learn tune: write the winning value (default: report only)")

    p = sub.add_parser("eval", help="score the harness on the fixed eval; exit 1 if below baseline")
    p.add_argument("--save-baseline", dest="save_baseline", action="store_true")
    p = sub.add_parser("memory", help="lint instruction files for facts the tree has moved past")
    p.add_argument("action", choices=["lint"], nargs="?", default="lint")
    p.add_argument("files", nargs="*", help="default: CLAUDE.md and .claude/rules/*.md")
    p = sub.add_parser("label", help="list recent prompts, or turn one into an eval case")
    p.add_argument("action", choices=["list", "route", "risk", "delegate"], nargs="?", default="list")
    p.add_argument("index", nargs="?", type=int, help="index from `aos label list`")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--must", action="append", default=[])
    p.add_argument("--mustnot", action="append", default=[])
    p.add_argument("--min")
    p.add_argument("--max")
    p.add_argument("--delegate", choices=["yes", "no"])
    p.add_argument("--mode", choices=list(workflow.MODES))

    sub.add_parser("models", help="show tier -> model mapping and availability")
    p = sub.add_parser("adapter")
    p.add_argument("action", choices=["show", "refresh"], nargs="?", default="show")
    p = sub.add_parser("registry")
    p.add_argument("action", choices=["show", "build", "validate"], nargs="?", default="show")
    sub.add_parser("metrics")

    # The catalogue an agent browses for itself. `aos route` RECOMMENDS a set
    # by score; this lists everything that agent may read, so choosing is the
    # agent's to do rather than the router's to finish. Names + one-line
    # descriptions only — cheap enough to hold, and `show` fetches the body.
    p = sub.add_parser("skills", help="list or show the skills an agent may use")
    p.add_argument("action", choices=["list", "show", "search"], nargs="?", default="list")
    p.add_argument("args", nargs="*", help="show: skill name; search: query words")
    p.add_argument("--agent", help="only skills this agent may load (default: all)")

    # The Obsidian vault link. `status` is first so a bare `aos vault` answers
    # the only question most people have, which is whether the link is live at
    # all. Inert until config/memory.json names a vault_root.
    p = sub.add_parser("vault", help="the Obsidian vault link: index, search, write-back")
    p.add_argument("action", choices=["status", "index", "search", "selftest"],
                   nargs="?", default="status")
    p.add_argument("args", nargs="*")

    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 2

    if a.cmd == "skills":
        reg = router.load_registry()
        skills = reg.get("skills", {})
        # An agent knows itself by its INSTALLED name — its own frontmatter says
        # `name: aos-builder` — but skill frontmatter is keyed on the short
        # config name. Fold, rather than expecting every caller to know which
        # vocabulary it is holding: `--agent aos-builder` returned 1 skill where
        # `--agent builder` returned 73, which is a dead end that looks like an
        # empty library.
        if a.agent and a.agent.startswith("aos-"):
            a.agent = {"aos-analyst": "analyst"}.get(a.agent, a.agent[4:])

        def visible(meta):
            # No declaration means any agent — the same rule the router applies.
            return not (a.agent and meta.get("agents") and a.agent not in meta["agents"])

        if a.action == "show":
            name = " ".join(a.args)
            meta = skills.get(name)
            if not meta:
                return out({"error": "no such skill", "name": name,
                            "hint": "aos skills search <words>"})
            try:
                with open(meta["path"], errors="replace") as fh:
                    body = fh.read()
            except (IOError, OSError) as exc:
                return out({"error": str(exc), "name": name})
            return out({"name": name, "path": meta["path"], "body": body})

        rows = [{"name": n, "description": m.get("description", "")[:160],
                 "agents": m.get("agents") or ["any"], "source": m.get("source", "os"),
                 "path": m.get("path", "")}
                for n, m in sorted(skills.items()) if visible(m)]
        if a.action == "search":
            q = " ".join(a.args).lower().split()
            rows = [r for r in rows
                    if all(w in (r["name"] + " " + r["description"]).lower() for w in q)]
        return out({"count": len(rows), "agent": a.agent, "skills": rows})

    if a.cmd == "vault":
        cfg = vault.load_config()
        if a.action == "index":
            built = vault.build(cfg)
            return out({"indexed": built["count"], "vault": built["vault"]})
        if a.action == "search":
            return out({"matches": vault.search(" ".join(a.args))})
        if a.action == "selftest":
            return out(vault.selftest())
        return out({
            "linked": vault.is_linked(cfg),
            "vault": vault.project_dir(cfg),
            "read_folders": (cfg.get("read") or {}).get("folders", []),
            "write_enabled": vault.write_enabled(cfg),
            "indexed": len(vault.load_index().get("notes", [])),
        })

    if a.cmd == "classify":
        return out(classify.classify(a.task, a.files, _policies()))
    if a.cmd == "route":
        return out(router.route(a.task, agent=a.agent, budget=a.budget,
                                adapter=_adapter(), policies=_policies()))
    if a.cmd == "brief":
        # Same router.route call as `aos route`, which is what the guard runs. Fold
        # `aos-builder` to `builder`: route with an unknown agent returns nothing.
        agent = a.agent[4:] if a.agent.startswith("aos-") else a.agent
        # The guard reads only the first line after MISSION:, so a multi-line mission
        # would route differently there, and a blank one is refused by it outright.
        if not a.mission.strip() or "\n" in a.mission or "\r" in a.mission:
            print("aos brief: mission must be non-blank and a single line", file=sys.stderr)
            return 1
        try:
            loaded = router.route(a.mission, agent=agent, budget=a.budget,
                                  adapter=_adapter(), policies=_policies())["loaded"]
        except Exception as exc:
            print("aos brief: routing failed: %s" % exc, file=sys.stderr)
            return 1
        if not loaded:
            print("aos brief: no skills routed for agent %r" % agent, file=sys.stderr)
            return 1
        print("MISSION: %s" % a.mission)
        for name in loaded:
            print("aos skills show %s" % name)
        return 0
    if a.cmd == "plan":
        return out(workflow.plan(a.task, a.files, policies=_policies(), adapter_data=_adapter()))
    if a.cmd == "guard":
        res = guards.check(a.command)
        out(res)
        return 0 if res["action"] in ("ALLOW", "CONFIRM") else 1
    if a.cmd == "guard-path":
        return out(guards.check_path_write(a.path))
    if a.cmd == "models":
        return out({"validation": models.validate(),
                    "example": {lvl: models.route(lvl) for lvl in range(1, 6)}})
    if a.cmd == "adapter":
        if a.action == "refresh":
            return out(adapter.write(paths.project_root(), paths.p("adapter.json")))
        return out(_adapter())
    if a.cmd == "registry":
        reg_path = paths.p("skills", "registry.json")
        if a.action == "build":
            # Rebuild BOTH libraries. The project registry used to be written
            # only by the installer, so editing a project skill's frontmatter —
            # or adding a skill at all — left the router reading a stale index
            # until the next install. "I added a skill and it cannot see it" is
            # not a debugging session anyone should have.
            built = registry.build(paths.p("skills"), reg_path)["count"]
            # install_root() is <project>/.claude/agentic-os; the project's own
            # skills sit beside it at <project>/.claude/skills. (paths.p("")
            # would leave a trailing separator and dirname would then hand back
            # the install root itself.)
            project_dir = os.path.join(os.path.dirname(paths.install_root()), "skills")
            project_out = paths.p("skills", "project-registry.json")
            try:
                # build() returns the registry dict; build_project() returns the
                # skills mapping itself. len() is right for both.
                project = len(registry.build_project(project_dir, project_out))
            except (IOError, OSError):
                project = None
            return out({"built": built, "project": project})
        reg = registry.load(reg_path)
        if a.action == "validate":
            return out({"problems": registry.validate(reg), "count": len(reg.get("skills", {}))})
        return out({"count": len(reg.get("skills", {})), "skills": sorted(reg.get("skills", {}))})
    if a.cmd == "metrics":
        con = metrics.connect()
        return out({"champion": metrics.aggregate(con, arm="champion"),
                    "challenger": metrics.aggregate(con, arm="challenger")})

    if a.cmd == "eval":
        cases = evals.load_cases()
        if not cases:
            out({"error": "no eval cases loaded (missing or corrupt evals/cases.json?)"})
            return 1
        res = evals.run(cases)
        if a.save_baseline:
            evals.save_baseline(res)
        res["baseline"] = evals.compare(res)
        out(res)
        return 1 if res["baseline"]["regressed"] else 0

    if a.cmd == "memory":
        proj = paths.project_root()
        count, version = memlint.installed_facts()
        probs = memlint.lint(a.files or memlint.default_files(proj), proj, count, version)
        out({"problems": probs, "count": len(probs)})
        return 1 if probs else 0

    if a.cmd == "label":
        recent = evals.traces(max(a.n, (a.index or 0) + 1))
        if a.action == "list":
            return out([dict(t, index=i) for i, t in enumerate(recent[:a.n])])
        if a.index is None or a.index >= len(recent):
            print("label %s needs an index from `aos label list`" % a.action, file=sys.stderr)
            return 2
        try:
            case = evals.label(recent[a.index], a.action, must=a.must, mustnot=a.mustnot,
                               min=a.min, max=a.max, mode=a.mode,
                               delegate=None if a.delegate is None else a.delegate == "yes")
        except (ValueError, KeyError) as exc:
            print("label refused: %s" % exc, file=sys.stderr)
            return 2
        return out(case)

    if a.cmd == "mode":
        if a.value:
            path = paths.config("auto.json")
            cfg = util.load_json(path)
            cfg["agent_mode"] = a.value
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as fh:
                    json.dump(cfg, fh, indent=2)
                os.chmod(tmp, os.stat(path).st_mode & 0o777)  # mkstemp is 0600; keep auto.json's mode
                os.replace(tmp, path)
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        return out({"agent_mode": workflow.agent_mode()})

    if a.cmd == "queue":
        con = queue.connect()
        act, args = a.action, a.args
        if act == "plan":
            return out(workflow.queue_waves(queue.ready(con), _policies()))
        if act == "add":
            title = args[0]
            cls = classify.classify(title, policies=_policies())
            deps = [int(x) for x in a.depends_on.split(",") if x.strip()]
            tid = queue.add(con, title, a.body, deps, cls["depth"], cls["risk"]["level"],
                            classification=cls)
            return out({"id": tid, "depth": cls["depth"], "risk": cls["risk"]["level"],
                        "blockers": [b["id"] for b in queue.blockers(con, tid)]})
        if act == "list":
            return out(queue.listing(con, args[0] if args else None))
        if act == "ready":
            return out(queue.ready(con))
        if act == "get":
            return out(queue.get(con, int(args[0])))
        if act == "set":
            queue.set_status(con, int(args[0]), args[1], " ".join(args[2:]))
            return out(queue.get(con, int(args[0])))
        if act in ("stale", "cancel-stale"):
            days = float(args[0]) if args else 7
            rows = queue.stale(con, days)
            if act == "cancel-stale":
                for r in rows:
                    queue.set_status(con, r["id"], "CANCELLED", "stale >%gd" % days)
            return out([{k: r[k] for k in ("id", "title", "status", "updated_at")} for r in rows])
        if act == "record":
            queue.record(con, int(args[0]), **json.loads(a.body or "{}"))
            return out(queue.get(con, int(args[0])))
        return out(queue.stats(con))

    if a.cmd == "artifact":
        if a.action == "write":
            path = artifacts.write(a.task_id, a.agent, json.loads(a.json))
            return out({"written": path})
        return out(artifacts.read(a.task_id, a.agent))

    if a.cmd == "audit":
        con = queue.connect()
        task = queue.get(con, a.task_id) or {"id": a.task_id, "title": ""}
        crit = [c.strip() for c in a.criteria.split("|") if c.strip()]
        res = workflow.completion_audit(task, artifacts.read(a.task_id), crit)
        out(res)
        return 0 if res["verdict"] == "COMPLETED" else 1

    if a.cmd == "learn":
        con = learning.connect()
        act, args = a.action, a.args
        if act == "observe":
            learning.observe(con, int(args[0]) if args[0].isdigit() else None, args[1], args[2],
                             json.loads(a.json))
            return out({"observed": args[1:3]})
        if act == "tune":
            knobs = args or sorted(evals.KNOBS)
            unknown = [k for k in knobs if k not in evals.KNOBS]
            if unknown:
                return out({"error": "unknown knob(s) %s; known: %s" % (unknown, sorted(evals.KNOBS))}) or 2
            cases = evals.load_cases()
            if not cases:
                out({"error": "no eval cases loaded; nothing to tune against"})
                return 1
            return out([evals.tune(cases, k, apply=a.apply) for k in knobs])
        if act == "cycle":
            return out(learning.cycle(con, metrics.connect(), auto_promote=not a.dry_run))
        if act == "patterns":
            return out(learning.patterns(con))
        if act == "hypothesize":
            return out(learning.hypothesize(con))
        if act == "propose":
            d = json.loads(a.json)
            return out(learning.propose(con, d["kind"], d["key"], d.get("scope", ""), d["value"],
                                        d.get("reason", ""), d.get("evidence"), d.get("source_task")))
        if act == "active":
            return out(learning.active(con))
        if act == "challengers":
            return out(learning.challengers(con))
        if act == "compare":
            return out(learning.compare(metrics.connect(), int(args[0])))
        if act == "promote":
            cmp_ = learning.compare(metrics.connect(), int(args[0]))
            if cmp_["decision"] != "promote" and "--force" not in args:
                return out({"promoted": False, "comparison": cmp_})
            return out(learning.promote(con, int(args[0]), cmp_))
        if act == "reject":
            return out(learning.reject(con, int(args[0]), " ".join(args[1:]) or "rejected"))
        if act == "rollback":
            return out(learning.rollback(con, int(args[0]), " ".join(args[1:]) or "manual rollback"))
        if act == "record-metric":
            d = json.loads(a.json)
            return out(metrics.record(metrics.connect(), int(args[0]), **d))
        return out(learning.history(con))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
