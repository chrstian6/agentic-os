"""Harness eval: fixed cases -> one 0-100 score (the autoresearch "fixed evaluator").

Cases live in evals/cases.json (shipped) plus state/evals/labeled.jsonl (labelled from real
prompts on this machine). The score is the share of cases whose routed skills, risk level
or delegation decision match the expectation. A change to the router, risk rules or
workflow is kept only if this score does not drop.
"""
import hashlib
import json
import os

from . import classify, paths, util, workflow

RISK_ORDER = ["normal", "elevated", "high", "critical"]


def _cases_path():
    return paths.p("evals", "cases.json")


def _labeled_path():
    return paths.state("evals", "labeled.jsonl")


def load_cases(cases_path=None, labeled_path=None):
    cases = []
    try:
        with open(cases_path or _cases_path()) as fh:
            cases.extend(json.load(fh)["cases"])
    except (IOError, OSError, ValueError, KeyError):
        pass
    lab = labeled_path or _labeled_path()
    if os.path.exists(lab):
        with open(lab) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        cases.append(json.loads(line))
                    except ValueError:
                        continue
    return cases


def _skills(plan):
    out = set()
    for s in plan["stages"]:
        out.update(s["skills"])
    return out


def _check_route(case):
    got = _skills(workflow.plan(case["prompt"]))
    miss = [m for m in case.get("must", []) if not set(m) & got]
    bad = sorted(set(case.get("mustnot", [])) & got)
    if miss or bad:
        return False, "missing=%s wrong=%s" % (miss, bad)
    return True, ""


def _check_risk(case):
    level = classify.risk(case["prompt"])["level"]
    lo, hi = RISK_ORDER.index(case["min"]), RISK_ORDER.index(case["max"])
    ok = lo <= RISK_ORDER.index(level) <= hi
    return ok, "" if ok else "got %s, want %s..%s" % (level, case["min"], case["max"])


def _check_delegate(case):
    real = workflow.agent_mode
    workflow.agent_mode = lambda: case.get("mode", "single")
    try:
        kw = {"file_count": case["file_count"]} if "file_count" in case else {}
        p = workflow.plan(case["prompt"], **kw)
    finally:
        workflow.agent_mode = real
    wrong = [k for k in ("delegate", "fan_out") if k in case and p.get(k) != case[k]]
    if wrong:
        return False, "; ".join("%s=%s want %s" % (k, p.get(k), case[k]) for k in wrong)
    return True, ""


CHECKS = {"route": _check_route, "risk": _check_risk, "delegate": _check_delegate}


def run(cases):
    if not cases:  # "nothing measured" must never read as a score
        raise ValueError("no eval cases loaded (missing or corrupt evals/cases.json?)")
    by_kind, failures, passed = {}, [], 0
    for c in cases:
        kind = c.get("kind")
        fn = CHECKS.get(kind)
        try:
            ok, why = fn(c) if fn else (False, "unknown kind %r" % kind)
        except Exception as exc:  # a broken case is a failure, never a skip
            ok, why = False, "error: %s" % exc
        tally = by_kind.setdefault(kind, [0, 0])
        tally[1] += 1
        if ok:
            tally[0] += 1
            passed += 1
        else:
            failures.append({"id": c.get("id"), "kind": kind, "prompt": c.get("prompt"), "why": why})
    total = len(cases)
    return {"score": round(100.0 * passed / total, 1) if total else 0.0,
            "passed": passed, "total": total, "by_kind": by_kind, "failures": failures}


def _traces_path():
    return paths.state("evals", "traces.jsonl")


def record_trace(entry, path=None, cap=2000):
    """Append one prompt's routing decision; keep only the newest `cap` lines (local only)."""
    path = path or _traces_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(entry) + "\n")
    with open(path) as fh:
        lines = fh.readlines()
    if len(lines) > cap:
        with open(path, "w") as fh:
            fh.writelines(lines[-cap:])


def traces(n=20, path=None):
    """Newest first."""
    try:
        with open(path or _traces_path()) as fh:
            lines = fh.readlines()
    except (IOError, OSError):
        return []
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
        if len(out) >= n:
            break
    return out


def label(trace, kind, path=None, **expect):
    """Turn a real prompt into an eval case. The expectation is the human's, never the trace's."""
    digest = hashlib.sha1(trace["prompt"].encode("utf-8")).hexdigest()[:8]
    case = {"id": "lab-%s-%s" % (kind, digest),
            "kind": kind, "prompt": trace["prompt"]}
    if kind == "route":
        if not expect.get("must") and not expect.get("mustnot"):
            raise ValueError("route label needs --must or --mustnot")
        case.update(must=[[s] for s in expect.get("must") or []], mustnot=expect.get("mustnot") or [])
    elif kind == "risk":
        if expect.get("min") not in RISK_ORDER or expect.get("max") not in RISK_ORDER:
            raise ValueError("risk label needs --min and --max from %s" % RISK_ORDER)
        case.update(min=expect["min"], max=expect["max"])
    elif kind == "delegate":
        if expect.get("delegate") not in (True, False):
            raise ValueError("delegate label needs --delegate yes|no")
        case.update(mode=expect.get("mode") or trace.get("mode") or "single", delegate=expect["delegate"])
    else:
        raise ValueError("unknown kind %r" % kind)
    path = path or _labeled_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(case) + "\n")
    return case


def _baseline_path():
    return paths.state("evals", "baseline.json")


def save_baseline(result, path=None):
    path = path or _baseline_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({k: result[k] for k in ("score", "passed", "total")}, fh)
    return path


def compare(result, path=None):
    try:
        with open(path or _baseline_path()) as fh:
            base = json.load(fh)["score"]
    except (IOError, OSError, ValueError, KeyError):
        return {"baseline": None, "delta": None, "regressed": False}
    return {"baseline": base, "delta": round(result["score"] - base, 1),
            "regressed": result["score"] < base}


# One knob = (config file, key path, default, candidate values). Fixed grids, not
# open search: few cases make a wide search overfit.
KNOBS = {
    "router.min_score": ("router.json", ("min_score",), 2.5, [1.5, 2.0, 2.5, 3.0, 3.5]),
    "risk.elevated": ("risk.json", ("level_thresholds", "elevated"), 2, [1, 2, 3]),
    "risk.high": ("risk.json", ("level_thresholds", "high"), 5, [3, 4, 5, 6, 7]),
    "risk.critical": ("risk.json", ("level_thresholds", "critical"), 9, [7, 8, 9, 10, 11]),
}


def _get(cfg, keys, default):
    for k in keys:
        if not isinstance(cfg, dict) or k not in cfg:
            return default
        cfg = cfg[k]
    return cfg


def _set(cfg, keys, value):
    for k in keys[:-1]:
        cfg = cfg.setdefault(k, {})
    cfg[keys[-1]] = value


def _score_with(cases, name, data):
    """Run the eval with config `name` replaced in memory; the file is untouched."""
    target = os.path.abspath(paths.config(name))
    real = util.load_json
    cache = classify._load.__defaults__[0]
    saved = cache.pop(name, None)
    util.load_json = lambda path, default=None: (
        json.loads(json.dumps(data)) if os.path.abspath(path) == target else real(path, default))
    try:
        return run(cases)["score"]
    finally:
        util.load_json = real
        cache.pop(name, None)
        if saved is not None:
            cache[name] = saved


def tune(cases, knob, apply=False, start=None, config_path=None, log_path=None):
    """Try each candidate of one knob; keep the best only if it strictly beats the
    current score. Every try is logged. Writes config only with apply=True."""
    name, keys, default, grid = KNOBS[knob]
    config_path = config_path or paths.config(name)
    cfg = util.load_json(config_path, default={}) or {}
    if start is not None:
        _set(cfg, keys, start)
    current = _get(cfg, keys, default)
    base = _score_with(cases, name, cfg)
    log_path = log_path or paths.state("evals", "tune.jsonl")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    tries, best, best_score = [], current, base
    for value in grid:
        if value == current:
            continue
        trial = json.loads(json.dumps(cfg))
        _set(trial, keys, value)
        score = _score_with(cases, name, trial)
        tries.append({"value": value, "score": score})
        with open(log_path, "a") as fh:
            fh.write(json.dumps({"knob": knob, "from": current, "value": value, "score": score,
                                 "base": base}) + "\n")
        closer = abs(value - current) < abs(best - current)
        if score > best_score or (score == best_score and best != current and closer):
            best, best_score = value, score
    kept = best_score > base
    written = False
    if kept and apply:
        _set(cfg, keys, best)
        with open(config_path + ".tmp", "w") as fh:
            json.dump(cfg, fh, indent=2)
            fh.write("\n")
        os.replace(config_path + ".tmp", config_path)
        written = True
    return {"knob": knob, "current": current, "base_score": base, "best": best,
            "best_score": best_score, "kept": kept, "written": written, "tries": tries}
