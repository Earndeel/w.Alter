#!/usr/bin/env python3
"""Memory Autopilot: daily supervisor of Walter Memory (canonical events, logs, Raw Vault).

Observes and scores; `--autofix safe` only restarts dead memory services and rotates the Postgres
container logs. Everything is read through module interfaces: `walter modules` (registry),
`walter-memory health`, and the memory gateway for recall probes. Hindsight was retired on
2026-10-19 (DECISIONS.md); its checks, dedup and cleanup are gone with it.

Report format is unchanged (latest.json with summary.severity/score/errors/warnings), as read by
the walter_health MCP tool.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def _log_dir() -> Path:
    """@instance/logs/memory-autopilot (the instance's logs; /root/.hermes/logs is only a compat link to it)."""
    try:
        out = subprocess.run(["walter", "instance", "path", "logs", "memory-autopilot"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
        if out.startswith("/"):
            return Path(out)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return Path("/root/.hermes/logs/memory-autopilot")


LOG_DIR = _log_dir()
DEFAULT_OUTPUT = LOG_DIR / "latest.json"
ALERT_REPORT = LOG_DIR / "alert-latest.json"
ROTATE_DOCKER_LOGS = Path("/root/.hermes/scripts/rotate_docker_logs.py")
PG_CONTAINER = "hindsight-pg"          # historical name: it hosts every Walter schema
MEMORY_MODULES = ("memory", "logs", "bus", "raw-vault")
MODEL_CALL_PREFIX = "model_calls:"                         # walter_memory.health: severity error
FALLBACK_PREFIXES = ("triage:", "assimilation ")            # decisions by fallback, processing errors

SECRET_RE = re.compile(
    r"(?i)("
    r"sk-[A-Za-z0-9_\-]{16,}|"
    r"rk_live_[A-Za-z0-9_\-]+|"
    r"gh[pousr]_[A-Za-z0-9_]+|"
    r"xox[baprs]-[A-Za-z0-9\-]+|"
    r"AIza[A-Za-z0-9_\-]{20,}|"
    r"\d{7,}:[A-Za-z0-9_\-]{25,}|"
    r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}|"
    r"((api[_-]?key|token|secret|password|database_url)\s*[=:]\s*)\S+"
    r")"
)

# Canonical recall must answer these from Monsieur's own history; a probe passes on any result
# without secret-like strings, and records which expected terms appeared.
RECALL_PROBES = [
    {"query": "Comment Monsieur veut-il être appelé ?", "expect_any": ["Monsieur", "vouvoiement", "vous"]},
    {"query": "Walter Router choix du modèle par tâche", "expect_any": ["Router", "modèle", "poste"]},
    {"query": "Scena Factory vidéo Cloudflare", "expect_any": ["Scena", "vidéo", "Cloudflare"]},
]


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, str):
        return value

    def repl(match: re.Match[str]) -> str:
        text = match.group(0)
        if "=" in text or ":" in text:
            sep = "=" if "=" in text else ":"
            prefix = text.split(sep, 1)[0]
            if len(prefix) <= 64 and re.search(r"(?i)(key|token|secret|password|database_url)", prefix):
                return f"{prefix}{sep}[REDACTED]"
        return "[REDACTED]"

    return SECRET_RE.sub(repl, value)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"ok": p.returncode == 0, "exit_code": p.returncode, "ms": round((time.perf_counter() - start) * 1000, 1),
                "stdout": redact((p.stdout or "")[-200000:]), "stderr": redact((p.stderr or "")[-6000:])}
    except subprocess.TimeoutExpired:
        return {"ok": False, "timeout": timeout, "ms": round((time.perf_counter() - start) * 1000, 1)}
    except Exception as e:
        return {"ok": False, "error": redact(str(e)), "ms": round((time.perf_counter() - start) * 1000, 1)}


def _json(res: dict[str, Any]) -> Any:
    try:
        return json.loads(res.get("stdout") or "")
    except (TypeError, ValueError):
        return None


def memory_units() -> list[str]:
    """Services owned by the memory modules, as declared in the Walter registry."""
    registry = _json(run(["walter", "modules"], timeout=30)) or {}
    return sorted({u for m in registry.get("modules", []) if m.get("id") in MEMORY_MODULES for u in m.get("services", [])})


def unit_state(unit: str) -> dict[str, Any]:
    res = run(["systemctl", "show", unit, "--property=ActiveState,SubState,UnitFileState"], timeout=5)
    props = dict(line.split("=", 1) for line in str(res.get("stdout", "")).splitlines() if "=" in line)
    return {"unit": unit, "active": props.get("ActiveState") == "active", "properties": props}


def postgres() -> dict[str, Any]:
    res = run(["docker", "inspect", "-f", "{{.State.Running}}", PG_CONTAINER], timeout=10)
    return {"container": PG_CONTAINER, "running": str(res.get("stdout", "")).strip() == "true"}


def recall_probe(probe: dict[str, Any]) -> dict[str, Any]:
    sys.path.insert(0, "/walter/cognition/memory")
    from walter_memory import client

    start = time.perf_counter()
    result = client.call("recall", {"query": probe["query"], "budget": "low", "max_tokens": 1024},
                         caller="memory-autopilot", timeout=20)
    ms = round((time.perf_counter() - start) * 1000, 1)
    records = result.get("records") or []
    text = str(result.get("text") or "")
    blob = text + "\n" + "\n".join(str(r.get("text", "")) for r in records[:5] if isinstance(r, dict))
    out = {"query": probe["query"], "status": result.get("status"), "ms": ms, "result_count": len(records),
           "matched_terms": [t for t in probe["expect_any"] if t.lower() in blob.lower()],
           "secret_leak_detected": bool(SECRET_RE.search(blob)),
           "top_snippets": [redact(" ".join(str(r.get("text", "")).split())[:180]) for r in records[:3] if isinstance(r, dict)]}
    out["ok"] = result.get("status") == "ok" and bool(records) and not out["secret_leak_detected"]
    return out


def recall_probes() -> dict[str, Any]:
    probes = [recall_probe(p) for p in RECALL_PROBES]
    latencies = [p["ms"] for p in probes]
    ok_count = sum(1 for p in probes if p["ok"])
    return {"ok": ok_count >= 2, "ok_count": ok_count, "total": len(probes),
            "avg_ms": round(sum(latencies) / len(latencies), 1) if latencies else None, "probes": probes}


def autofix(report: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"enabled": True, "level": "safe", "restarted": {}}
    for item in report["checks"]["systemd"]:
        if not item["active"]:
            out["restarted"][item["unit"]] = run(["systemctl", "restart", item["unit"]], timeout=45)
    if ROTATE_DOCKER_LOGS.exists():
        out["log_rotation"] = run([sys.executable, str(ROTATE_DOCKER_LOGS), "--containers", PG_CONTAINER,
                                   "--max-mb", "50", "--keep", "5"], timeout=60)
    return out


def evaluate(report: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    score = 100
    checks = report["checks"]

    if not checks["postgres"]["running"]:
        errors.append(f"PostgreSQL container {PG_CONTAINER} not running"); score -= 50
    if not checks["systemd"]:
        errors.append("no memory service found in the Walter registry"); score -= 25
    for item in checks["systemd"]:
        if not item["active"]:
            errors.append(f"{item['unit']} not active"); score -= 25

    health = checks["walter_memory"].get("report")
    if not isinstance(health, dict):
        errors.append("walter-memory health command failed"); score -= 40
    elif health.get("status") != "ok":
        problems = [str(p) for p in (health.get("problems") or ["Walter Memory reports problems"])]
        # SOCLE A8 (2026-11-11): failing model calls are an outage, not a warning; decisions taken by fallback and
        # processing errors weigh more than a stale connector. The outage of 2026-11-11 scored 100 twice.
        failing = [p for p in problems if p.startswith(MODEL_CALL_PREFIX)]
        fallback = [p for p in problems if p.startswith(FALLBACK_PREFIXES) and p not in failing]
        other = [p for p in problems if p not in failing and p not in fallback]
        errors.extend("Walter Memory: " + p for p in failing); score -= min(60, 25 * len(failing))
        warnings.extend("Walter Memory: " + p for p in fallback); score -= min(20, 10 * len(fallback))
        warnings.extend("Walter Memory: " + p for p in other); score -= min(20, 5 * len(other))

    recall = checks["recall_probes"]
    if not recall["ok"]:
        errors.append(f"recall probes weak: {recall['ok_count']}/{recall['total']} passed"); score -= 30
    if isinstance(recall.get("avg_ms"), (int, float)) and recall["avg_ms"] > 3500:
        warnings.append(f"recall probe latency high: avg {recall['avg_ms']} ms"); score -= 6
    for probe in recall["probes"]:
        if probe["secret_leak_detected"]:
            errors.append(f"secret-like string in recalled memory for query: {probe['query']}"); score -= 50

    severity = "error" if errors else ("warning" if warnings or score < 92 else "ok")
    actions = ([f"Inspect {LOG_DIR / 'latest.json'} and the services' journals."] if errors
               else ["No urgent action; keep observing."] if warnings else [])
    return {"ok": not errors, "severity": severity, "score": max(0, min(100, score)),
            "errors": errors, "warnings": warnings, "recommended_actions": actions}


def write_reports(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    safe = redact(report)
    text = json.dumps(safe, ensure_ascii=False, indent=2) + "\n"
    output.write_text(text)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (LOG_DIR / f"run-{stamp}.json").write_text(text)
    summary = safe["summary"]
    with (LOG_DIR / "status.log").open("a") as f:
        f.write(json.dumps({"ts": safe["ts"], "severity": summary["severity"], "score": summary["score"],
                            "errors": len(summary["errors"]), "warnings": len(summary["warnings"])}) + "\n")
    ALERT_REPORT.write_text(json.dumps({"ts": safe["ts"], "summary": summary}, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Walter Memory autopilot")
    parser.add_argument("--mode", choices=["quick", "standard"], default="standard")
    parser.add_argument("--json", action="store_true", help="print full JSON report")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="latest JSON report path")
    parser.add_argument("--autofix", choices=["off", "safe"], default="off")
    args = parser.parse_args()

    start = time.perf_counter()
    report: dict[str, Any] = {"ts": now_iso(), "mode": args.mode, "autofix_level": args.autofix,
                              "host": os.uname().nodename, "checks": {}}
    report["checks"]["postgres"] = postgres()
    report["checks"]["systemd"] = [unit_state(u) for u in memory_units()]
    wm = run(["/usr/local/bin/walter-memory", "health"], timeout=60)
    report["checks"]["walter_memory"] = {"ok": wm.get("ok"), "ms": wm.get("ms"), "report": _json(wm)}
    report["checks"]["recall_probes"] = recall_probes() if args.mode == "standard" else {
        "ok": True, "ok_count": 0, "total": 0, "avg_ms": None, "probes": [], "skipped": "quick mode"}
    report["autofix"] = autofix(report) if args.autofix == "safe" else {"enabled": False}
    report["summary"] = evaluate(report)
    report["elapsed_s"] = round(time.perf_counter() - start, 2)
    write_reports(report, Path(args.output))

    if args.json:
        print(json.dumps(redact(report), ensure_ascii=False, indent=2))
    else:
        s = report["summary"]
        print(f"Memory autopilot: {s['severity'].upper()} score={s['score']} errors={len(s['errors'])} "
              f"warnings={len(s['warnings'])} elapsed={report['elapsed_s']}s report={args.output}")
    return 0 if report["summary"]["severity"] != "error" else 2


if __name__ == "__main__":
    raise SystemExit(main())
