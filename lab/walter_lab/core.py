"""walter-lab — does a variant do better than what runs today? Measured on the shared bench, never by opinion.

Owner decisions (2026-10-27/28): Lab looks for better ways even when a module works; Guardian keeps a module working;
Curator organises skills — no overlap. An experiment can conclude that nothing should change. Lab never applies a
change: it records a proposal with its evidence; the module's owner (or the owner of the instance) decides. Experiments run on the
same end-to-end scenarios as the bench (walter-scenario), with each variant expressed as environment switches the
modules already honour (WALTER_RUN_CONTEXT, WALTER_RUN_TOOLS, …). External code found by a scout is untrusted and
will need a sandbox without secrets nor production data before any experiment runs it (not built yet).

Experiment v1 (experiments/<name>.yaml):
  name, hypothesis, scenario (a walter-scenario name), repeats,
  variants: {<id>: {env: {VAR: value}, note}}            the first variant is the current behaviour (baseline)
  metrics: [ok, task_seconds, model_calls, tool_calls, …]  keys of walter-scenario's report metrics, plus ok
  decision: {prefer: <variant>, if: ["ok_rate >= baseline", "median model_calls <= baseline", …]}
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

MODULE = Path(__file__).resolve().parent.parent


def instance_root() -> Path:
    root = os.environ.get("WALTER_INSTANCE")
    if not root:
        try:
            root = Path("/etc/walter/instance").read_text().strip()
        except OSError:
            root = str(MODULE)
    return Path(root)


def load(name: str) -> dict:
    p = Path(name) if Path(name).exists() else MODULE / "experiments" / f"{name}.yaml"
    exp = yaml.safe_load(p.read_text())
    for k in ("name", "hypothesis", "scenario", "variants"):
        if not exp.get(k):
            raise ValueError(f"experiment lacks {k}")
    return exp


def run_scenario(scenario: str, env: dict, variant: str, timeout: int = 1800) -> dict:
    e = {**os.environ, **{k: str(v) for k, v in (env or {}).items()}, "WALTER_LAB_VARIANT": variant}
    try:
        out = subprocess.run(["walter-scenario", "run", scenario, "--json"], capture_output=True, text=True,
                             timeout=timeout, env=e)
        rep = json.loads(out.stdout[out.stdout.find("{"):])
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "metrics": {}}
    return {"ok": rep.get("ok"), "run_id": rep.get("run_id"), "metrics": rep.get("metrics") or {},
            "failed": [a["detail"] for a in rep.get("assertions") or [] if not a.get("ok")]}


def summarise(results: list[dict], metrics: list[str]) -> dict:
    out = {}
    for variant in dict.fromkeys(r["variant"] for r in results):
        rs = [r for r in results if r["variant"] == variant]
        s = {"n": len(rs), "ok_rate": round(sum(1 for r in rs if r["ok"]) / len(rs), 2)}
        for m in metrics:
            if m == "ok":
                continue
            vals = [r["metrics"].get(m) for r in rs if r["ok"] and r["metrics"].get(m) is not None]
            s[f"median {m}"] = statistics.median(vals) if vals else None
        out[variant] = s
    return out


def decide(exp: dict, summary: dict) -> dict:
    """The rule written before the runs, evaluated mechanically: `<stat> <op> baseline`."""
    rule = exp.get("decision") or {}
    variants = list(exp["variants"])
    base, cand = variants[0], rule.get("prefer") or (variants[1] if len(variants) > 1 else variants[0])
    checks = []
    for cond in rule.get("if") or []:
        stat, op, _ = cond.rsplit(" ", 2)
        a, b = summary.get(cand, {}).get(stat), summary.get(base, {}).get(stat)
        ok = a is not None and b is not None and {"<=": a <= b, ">=": a >= b, "<": a < b, ">": a > b}[op]
        checks.append({"condition": cond, cand: a, base: b, "holds": ok})
    holds = bool(checks) and all(c["holds"] for c in checks)
    return {"baseline": base, "candidate": cand, "checks": checks,
            "proposal": f"adopter {cand}" if holds and cand != base else f"ne rien changer (garder {base})",
            "applied": False, "note": "Lab propose ; le propriétaire du module ou de l'instance décide."}


def run(name: str, repeats: int | None = None) -> dict:
    exp = load(name)
    n = int(repeats or exp.get("repeats") or 3)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = instance_root() / "state" / "lab" / exp["name"]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stamp}.json"
    results = []
    for i in range(n):                               # interleaved, so drift (load, provider) hits every variant
        for vid, v in exp["variants"].items():
            r = run_scenario(exp["scenario"], v.get("env") or {}, vid)
            results.append({"variant": vid, "repeat": i + 1, **r})
            path.write_text(json.dumps({"experiment": exp, "at": stamp, "results": results}, ensure_ascii=False,
                                       indent=1, default=str))
    summary = summarise(results, exp.get("metrics") or ["ok"])
    report = {"experiment": exp["name"], "hypothesis": exp["hypothesis"], "at": stamp, "repeats": n,
              "summary": summary, "decision": decide(exp, summary), "results": results}
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    report["file"] = str(path)
    return report


def history(name: str) -> list[dict]:
    d = instance_root() / "state" / "lab" / name
    out = []
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        r = json.loads(p.read_text())
        out.append({"at": r.get("at"), "summary": r.get("summary"), "decision": (r.get("decision") or {}).get("proposal")})
    return out
