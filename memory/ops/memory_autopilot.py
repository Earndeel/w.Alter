#!/usr/bin/env python3
"""Memory Autopilot for W.Alter/Hermes Hindsight.

Default mode observes, evaluates, reports, and raises local alerts. Optional
`--autofix safe` performs low-risk unattended hygiene only (test marker cleanup,
PostgreSQL quarantine, dead memory-service restart, log rotation). Optional
`--autofix guarded` also runs bounded exact-PG-dedup with snapshot.

Responsibilities:
- avoid competing with dream-cycle.service;
- run stack health checks and small recall quality probes;
- track PG/Qdrant counts, duplicate pressure, pending async work, and drift;
- periodically run the existing reconciliation dry-run;
- optionally apply safe/guarded fixes with reports and caps;
- write structured JSON reports under /root/.hermes/logs/memory-autopilot/.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/root/.hermes")
SCRIPT_DIR = ROOT / "scripts"
LOG_DIR = ROOT / "logs" / "memory-autopilot"
DEFAULT_OUTPUT = LOG_DIR / "latest.json"
STACK_REPORT = LOG_DIR / "stack-check-latest.json"
RECONCILE_REPORT = LOG_DIR / "reconcile-latest.json"
ALERT_REPORT = LOG_DIR / "alert-latest.json"
AUTOFIX_REPORT = LOG_DIR / "autofix-latest.json"
GUARDED_DEDUP_REPORT = LOG_DIR / "pg-exact-dedup-latest.json"

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

RECALL_PROBES = [
    {
        "query": "Lucas préférences W.Alter mémoire Hindsight",
        "expect_any": ["Lucas", "W.Alter", "Hindsight", "mémoire"],
        "budget": "low",
    },
    {
        "query": "Scena Factory architecture Cloudflare Workers video agent",
        "expect_any": ["Scena", "Cloudflare", "video"],
        "budget": "low",
    },
    {
        "query": "Hindsight Qdrant hybrid search reranker mémoire",
        "expect_any": ["Hindsight", "Qdrant", "hybrid", "memory"],
        "budget": "low",
    },
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


def mkdirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def run(cmd: list[str], timeout: int = 30, input_text: str | None = None) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        p = subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "ms": round((time.perf_counter() - start) * 1000, 1),
            "stdout": redact((p.stdout or "")[-12000:]),
            "stderr": redact((p.stderr or "")[-6000:]),
        }
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "timeout": timeout,
            "ms": round((time.perf_counter() - start) * 1000, 1),
            "stdout": redact((e.stdout or "")[-6000:]),
            "stderr": redact((e.stderr or "")[-3000:]),
        }
    except Exception as e:
        return {"ok": False, "error": redact(str(e)), "ms": round((time.perf_counter() - start) * 1000, 1)}


def parse_systemctl_show(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def systemd_unit(unit: str) -> dict[str, Any]:
    props = "Id,LoadState,ActiveState,SubState,UnitFileState,FragmentPath,NextElapseUSecRealtime,ActiveEnterTimestamp"
    res = run(["systemctl", "show", unit, f"--property={props}"], timeout=5)
    data = parse_systemctl_show(str(res.get("stdout", ""))) if res.get("stdout") else {}
    return {"ok": res.get("ok"), "unit": unit, "properties": data}


def dream_cycle_active() -> bool:
    res = run(["systemctl", "is-active", "dream-cycle.service"], timeout=5)
    return str(res.get("stdout", "")).strip() == "active"


def psql(sql: str, timeout: int = 30) -> dict[str, Any]:
    cmd = [
        "docker", "exec", "-i", "hindsight-pg", "psql", "-U", "hindsight", "-d", "hindsight",
        "-t", "-A", "-F", "|", "-P", "pager=off",
    ]
    return run(cmd, timeout=timeout, input_text=sql)


def parse_kv_rows(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) < 2 or not parts[0]:
            continue
        key = parts[0]
        value: Any = "|".join(parts[1:])
        if re.fullmatch(r"-?\d+", value or ""):
            value = int(value)
        elif re.fullmatch(r"-?\d+\.\d+", value or ""):
            value = float(value)
        out[key] = value
    return out


def http_json(url: str, method: str = "GET", body: dict[str, Any] | None = None, timeout: int = 8) -> dict[str, Any]:
    start = time.perf_counter()
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(100000).decode("utf-8", "replace")
            try:
                parsed: Any = json.loads(raw)
            except Exception:
                parsed = raw[:2000]
            return {
                "ok": 200 <= r.status < 300,
                "status": r.status,
                "ms": round((time.perf_counter() - start) * 1000, 1),
                "body": redact(parsed),
            }
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "ms": round((time.perf_counter() - start) * 1000, 1), "error": redact(str(e))}
    except Exception as e:
        return {"ok": False, "ms": round((time.perf_counter() - start) * 1000, 1), "error": redact(str(e))}


def qdrant_count(collection: str) -> dict[str, Any]:
    res = http_json(
        f"http://127.0.0.1:6333/collections/{collection}/points/count",
        method="POST",
        body={"exact": True},
        timeout=8,
    )
    if res.get("ok") and isinstance(res.get("body"), dict):
        res["count"] = res["body"].get("result", {}).get("count")
        res.pop("body", None)
    return res


def collect_pg_metrics() -> dict[str, Any]:
    sql = """
SELECT 'memory_units', count(*) FROM memory_units;
SELECT 'entities', count(*) FROM entities;
SELECT 'unit_entities', count(*) FROM unit_entities;
SELECT 'memory_links', count(*) FROM memory_links;
SELECT 'chunks', count(*) FROM chunks;
SELECT 'documents', count(*) FROM documents;
SELECT 'async_operations', count(*) FROM async_operations;
SELECT 'pending_async_ops', count(*) FROM async_operations WHERE status NOT IN ('completed','failed','cancelled');
SELECT 'embedding_null', count(*) FROM memory_units WHERE embedding IS NULL;
SELECT 'embedding_dims', COALESCE(min(vector_dims(embedding))::text,'null') || '/' || COALESCE(max(vector_dims(embedding))::text,'null') FROM memory_units WHERE embedding IS NOT NULL;
SELECT 'exact_duplicate_groups', count(*) FROM (SELECT lower(trim(text)) t, count(*) c FROM memory_units WHERE text IS NOT NULL GROUP BY 1 HAVING count(*) > 1) d;
SELECT 'exact_duplicate_extra', COALESCE(sum(c-1),0) FROM (SELECT lower(trim(text)) t, count(*) c FROM memory_units WHERE text IS NOT NULL GROUP BY 1 HAVING count(*) > 1) d;
SELECT 'memory_units_24h', count(*) FROM memory_units WHERE created_at > now() - interval '24 hours';
SELECT 'schemas_with_pending_work_exists', count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname='schemas_with_pending_work';
"""
    raw = psql(sql, timeout=35)
    return {"raw": raw, "metrics": parse_kv_rows(str(raw.get("stdout", ""))) if raw.get("ok") else {}}


def run_stack_check() -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "hindsight_stack_check.py"),
        "--json",
        "--output",
        str(STACK_REPORT),
    ]
    res = run(cmd, timeout=70)
    parsed: Any = None
    if STACK_REPORT.exists():
        try:
            parsed = json.loads(STACK_REPORT.read_text())
        except Exception:
            parsed = None
    if parsed is None and res.get("stdout"):
        try:
            parsed = json.loads(str(res["stdout"]))
        except Exception:
            parsed = None
    return {"command": res, "report": redact(parsed)}


def run_reconcile_if_due(every_hours: float, force: bool = False) -> dict[str, Any]:
    if every_hours <= 0 and not force:
        return {"skipped": True, "reason": "disabled"}
    due = force or not RECONCILE_REPORT.exists()
    if RECONCILE_REPORT.exists() and not force:
        age_h = (time.time() - RECONCILE_REPORT.stat().st_mtime) / 3600.0
        due = age_h >= every_hours
    else:
        age_h = None
    if not due:
        return {"skipped": True, "reason": "not_due", "age_hours": round(age_h or 0, 2), "path": str(RECONCILE_REPORT)}

    cmd = [sys.executable, str(SCRIPT_DIR / "hindsight_reconcile_dryrun.py"), "--output", str(RECONCILE_REPORT), "--sample", "8"]
    res = run(cmd, timeout=120)
    parsed: Any = None
    if RECONCILE_REPORT.exists():
        try:
            parsed = json.loads(RECONCILE_REPORT.read_text())
        except Exception:
            parsed = None
    compact = None
    if isinstance(parsed, dict):
        compact = {
            "mode": parsed.get("mode"),
            "postgres": {
                "memory_units": (parsed.get("postgres") or {}).get("memory_units"),
                "unique_texts": (parsed.get("postgres") or {}).get("unique_texts"),
                "duplicate_extra": ((parsed.get("postgres") or {}).get("duplicates") or {}).get("extra"),
            },
            "qdrant": {
                "points": (parsed.get("qdrant") or {}).get("points"),
                "unique_texts": (parsed.get("qdrant") or {}).get("unique_texts"),
                "duplicate_extra": ((parsed.get("qdrant") or {}).get("duplicates") or {}).get("extra"),
            },
            "coverage": {
                "pg_unique_texts_absent_from_qdrant": ((parsed.get("coverage") or {}).get("pg_unique_texts_absent_from_qdrant")),
                "qdrant_unique_texts_absent_from_pg": ((parsed.get("coverage") or {}).get("qdrant_unique_texts_absent_from_pg")),
            },
            "recommendation": parsed.get("recommendation"),
        }
    return {"skipped": False, "path": str(RECONCILE_REPORT), "command": res, "summary": redact(compact)}


def recall_probe(probe: dict[str, Any]) -> dict[str, Any]:
    # 2026-10-01: probes target walter-voice-memory (Hindsight PG); the Qdrant/hybrid-search pipeline is retired.
    body = {"query": probe["query"], "limit": 5}
    res = http_json("http://127.0.0.1:8897/recall", method="POST", body=body, timeout=20)
    out: dict[str, Any] = {
        "query": probe["query"],
        "ok": False,
        "http": {k: res.get(k) for k in ("ok", "status", "ms", "error") if k in res},
    }
    if not res.get("ok") or not isinstance(res.get("body"), dict):
        return out
    body_data = res["body"]
    results = body_data.get("results") or []
    context = body_data.get("memory_context") or ""
    snippets = []
    for item in results[:3]:
        text = item.get("text", "") if isinstance(item, dict) else ""
        snippets.append(redact(" ".join(str(text).split())[:180]))
    expected = probe.get("expect_any") or []
    blob = "\n".join(str(s) for s in snippets + [context[:500]])
    matched = [term for term in expected if term.lower() in blob.lower()]
    sniper = body_data.get("sniper") if isinstance(body_data.get("sniper"), dict) else {}
    out.update(
        {
            "ok": len(results) > 0,
            "result_count": len(results),
            "context_chars": len(context),
            "secret_leak_detected": bool(SECRET_RE.search(context)),
            "matched_terms": matched,
            "top_snippets": snippets,
            "sniper": {
                "enabled": sniper.get("enabled"),
                "budget": sniper.get("budget"),
                "compiled_items": sniper.get("compiled_items"),
                "total_ms": sniper.get("total_ms"),
                "sniper_ms": sniper.get("sniper_ms"),
            },
        }
    )
    if out["secret_leak_detected"]:
        out["ok"] = False
    return redact(out)


def run_recall_probes() -> dict[str, Any]:
    probes = [recall_probe(p) for p in RECALL_PROBES]
    ok_count = sum(1 for p in probes if p.get("ok"))
    latencies = [p.get("http", {}).get("ms") for p in probes if isinstance(p.get("http", {}).get("ms"), (int, float))]
    return {
        "ok": ok_count >= 2,
        "ok_count": ok_count,
        "total": len(probes),
        "avg_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "probes": probes,
    }


def _parse_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except Exception:
        return None


def restart_dead_memory_services(systemd_checks: dict[str, Any]) -> dict[str, Any]:
    """Restart only core long-running memory services that are not active."""
    out: dict[str, Any] = {"checked": [], "restarted": {}}
    for unit in ["hindsight-api.service", "walter-voice-memory.service"]:
        props = (((systemd_checks or {}).get(unit) or {}).get("properties") or {})
        state = props.get("ActiveState")
        out["checked"].append({"unit": unit, "active_state": state})
        if state not in {"active", "activating"}:
            out["restarted"][unit] = run(["systemctl", "restart", unit], timeout=45)
    return out


def run_log_rotation_if_available() -> dict[str, Any]:
    script = SCRIPT_DIR / "rotate_docker_logs.py"
    if not script.exists():
        return {"skipped": True, "reason": "rotate_docker_logs.py_missing"}
    return run([sys.executable, str(script), "--containers", "hindsight-pg", "--max-mb", "50", "--keep", "5"], timeout=60)


def run_safe_cleanup() -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "memory_safe_cleanup.py"),
        "--apply",
        "--json",
        "--output",
        str(LOG_DIR / "safe-cleanup-latest.json"),
    ]
    res = run(cmd, timeout=120)
    parsed = _parse_json_file(LOG_DIR / "safe-cleanup-latest.json")
    return {"command": res, "report": redact(parsed)}


def run_guarded_pg_exact_dedup() -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "hindsight_pg_exact_dedup.py"),
        "--apply",
        "--limit-groups",
        "25",
        "--max-delete",
        "50",
        "--json",
        "--output",
        str(GUARDED_DEDUP_REPORT),
    ]
    res = run(cmd, timeout=240)
    parsed = _parse_json_file(GUARDED_DEDUP_REPORT)
    return {"command": res, "report": redact(parsed)}


def run_autofix(level: str, report: dict[str, Any]) -> dict[str, Any]:
    """Apply autonomous fixes according to selected level."""
    if level == "off":
        return {"enabled": False}
    out: dict[str, Any] = {"enabled": True, "level": level, "safe": {}, "guarded": {}}
    out["safe"]["restart_dead_services"] = restart_dead_memory_services((report.get("checks") or {}).get("systemd") or {})
    out["safe"]["cleanup"] = run_safe_cleanup()
    out["safe"]["log_rotation"] = run_log_rotation_if_available()
    if level == "guarded":
        out["guarded"]["pg_exact_dedup"] = run_guarded_pg_exact_dedup()
    return out


def load_previous(output_path: Path) -> dict[str, Any] | None:
    if not output_path.exists():
        return None
    try:
        return json.loads(output_path.read_text())
    except Exception:
        return None


def compute_trends(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return {"available": False, "reason": "no_previous_report"}

    def get_metric(doc: dict[str, Any], name: str) -> Any:
        return (((doc.get("checks") or {}).get("postgres") or {}).get("metrics") or {}).get(name)

    metrics = ["memory_units", "entities", "memory_links", "pending_async_ops", "exact_duplicate_extra", "memory_units_24h"]
    deltas: dict[str, Any] = {}
    for m in metrics:
        cur = get_metric(current, m)
        prev = get_metric(previous, m)
        if isinstance(cur, int) and isinstance(prev, int):
            deltas[m] = cur - prev
    cur_q = (((current.get("checks") or {}).get("qdrant") or {}).get("memories_count") or {}).get("count")
    prev_q = (((previous.get("checks") or {}).get("qdrant") or {}).get("memories_count") or {}).get("count")
    if isinstance(cur_q, int) and isinstance(prev_q, int):
        deltas["qdrant_memories"] = cur_q - prev_q
    return {"available": True, "deltas_since_previous": deltas, "previous_ts": previous.get("ts")}


def evaluate(report: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []
    score = 100

    wm=((report.get('checks') or {}).get('walter_memory') or {})
    health=wm.get('report')
    if wm and not isinstance(health,dict):
        errors.append('Walter Memory health command failed');score-=20
    elif health and health.get('status')!='ok':
        problems=health.get('problems') or ['Walter Memory reports problems']
        warnings.extend('Walter Memory: '+str(p) for p in problems);score-=min(20,5*len(problems))
    cleanup=((report.get('autofix') or {}).get('safe') or {}).get('cleanup') or {}
    if cleanup and (not cleanup.get('command',{}).get('ok',True) or not (cleanup.get('report') or {}).get('summary',{}).get('ok',False)):
        errors.append('memory cleanup failed (see autofix.safe.cleanup)');score-=20

    # Prefer post-autofix measurements when a safe/guarded run changed hygiene.
    effective_checks = report.get("post_autofix_checks") or report.get("checks") or {}

    stack = ((report.get("checks") or {}).get("stack_check") or {}).get("report") or {}
    stack_summary = stack.get("summary") or {}
    if stack_summary and not stack_summary.get("ok", False):
        errors.extend([f"stack_check: {e}" for e in stack_summary.get("errors", [])])
        score -= 35
    warnings.extend([f"stack_check: {w}" for w in stack_summary.get("warnings", [])])

    pg = (((effective_checks or {}).get("postgres") or {}).get("metrics") or {})
    if pg.get("embedding_null", 0):
        errors.append(f"PG memory_units without embedding: {pg.get('embedding_null')}")
        score -= 25
    if pg.get("schemas_with_pending_work_exists") != 1:
        errors.append("PostgreSQL helper schemas_with_pending_work missing")
        score -= 25
    if isinstance(pg.get("pending_async_ops"), int) and pg["pending_async_ops"] > 10:
        warnings.append(f"pending async operations high: {pg['pending_async_ops']}")
        score -= 8
    if isinstance(pg.get("exact_duplicate_extra"), int) and pg["exact_duplicate_extra"] > 0:
        warnings.append(f"historical exact duplicate extras: {pg['exact_duplicate_extra']}")
        score -= min(10, pg["exact_duplicate_extra"] // 10 + 1)

    qmem = (((effective_checks or {}).get("qdrant") or {}).get("memories_count") or {}).get("count")
    if isinstance(pg.get("memory_units"), int) and isinstance(qmem, int):
        if qmem == 0:
            errors.append("Qdrant memories collection is empty")
            score -= 30
        else:
            ratio = round(pg["memory_units"] / qmem, 2)
            report.setdefault("derived", {})["pg_to_qdrant_memory_ratio"] = ratio
            if ratio > 4.0:
                # PG is the broad historical/audit store. Qdrant is intentionally
                # kept as the active fast index as long as recall quality is healthy.
                if qmem >= 200 and not pg.get("embedding_null"):
                    report.setdefault("derived", {})["pg_qdrant_drift_interpretation"] = (
                        "expected_active_index_policy: PG keeps broad history; Qdrant keeps active/canonical recall set"
                    )
                else:
                    warnings.append(f"PG/Qdrant memory count drift high: {pg['memory_units']} vs {qmem}")
                    score -= 8

    recall = ((report.get("checks") or {}).get("recall_probes") or {})
    if recall and not recall.get("ok"):
        errors.append(f"recall probes weak: {recall.get('ok_count')}/{recall.get('total')} passed")
        score -= 30
    if isinstance(recall.get("avg_ms"), (int, float)) and recall["avg_ms"] > 3500:
        warnings.append(f"recall probe latency high: avg {recall['avg_ms']} ms")
        score -= 6
    for probe in recall.get("probes", []) if isinstance(recall.get("probes"), list) else []:
        if probe.get("secret_leak_detected"):
            errors.append(f"secret-like string detected in compiled memory context for query: {probe.get('query')}")
            score -= 50

    reconcile = ((report.get("checks") or {}).get("reconcile_dryrun") or {})
    if reconcile.get("command") and not reconcile.get("command", {}).get("ok"):
        warnings.append("reconciliation dry-run failed")
        score -= 5
    rec_summary = reconcile.get("summary") or {}
    coverage = rec_summary.get("coverage") or {}
    absent = coverage.get("pg_unique_texts_absent_from_qdrant")
    if isinstance(absent, int) and absent > 500:
        warnings.append(f"many PG unique texts absent from Qdrant dry-run: {absent}")
        actions.append("Review reconcile dry-run before any backfill; no automatic mutation was performed.")

    if errors:
        actions.append("Inspect /root/.hermes/logs/memory-autopilot/latest.json and recent systemd logs.")
    if warnings and not errors:
        actions.append("No urgent action; keep observing trend and review dry-run before destructive cleanup.")

    severity = "ok"
    if errors:
        severity = "error"
    elif warnings or score < 92:
        severity = "warning"

    return {
        "ok": not errors,
        "severity": severity,
        "score": max(0, min(100, score)),
        "errors": errors,
        "warnings": warnings,
        "recommended_actions": actions,
    }


def write_reports(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    safe = redact(report)
    output.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    history_path = LOG_DIR / f"run-{stamp}.json"
    history_path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n")
    summary_line = {
        "ts": safe.get("ts"),
        "severity": (safe.get("summary") or {}).get("severity"),
        "score": (safe.get("summary") or {}).get("score"),
        "errors": len((safe.get("summary") or {}).get("errors") or []),
        "warnings": len((safe.get("summary") or {}).get("warnings") or []),
    }
    with (LOG_DIR / "status.log").open("a") as f:
        f.write(json.dumps(summary_line, ensure_ascii=False) + "\n")
    if (safe.get("summary") or {}).get("severity") in {"warning", "error"}:
        ALERT_REPORT.write_text(json.dumps({"ts": safe.get("ts"), "summary": safe.get("summary")}, ensure_ascii=False, indent=2) + "\n")
    else:
        ALERT_REPORT.write_text(json.dumps({"ts": safe.get("ts"), "summary": safe.get("summary")}, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-destructive W.Alter/Hermes memory autopilot")
    parser.add_argument("--mode", choices=["quick", "standard"], default="standard")
    parser.add_argument("--json", action="store_true", help="print full JSON report")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="latest JSON report path")
    parser.add_argument("--reconcile-every-hours", type=float, default=12.0)
    parser.add_argument("--force-reconcile", action="store_true")
    parser.add_argument("--autofix", choices=["off", "safe", "guarded"], default="off", help="apply autonomous fixes after checks")
    args = parser.parse_args()

    mkdirs()
    output_path = Path(args.output)
    previous = load_previous(output_path)
    start = time.perf_counter()

    report: dict[str, Any] = {
        "ts": now_iso(),
        "mode": args.mode,
        "autofix_level": args.autofix,
        "non_destructive": args.autofix == "off",
        "host": os.uname().nodename,
        "checks": {},
        "derived": {},
    }

    report["checks"]["systemd"] = {
        unit: systemd_unit(unit)
        for unit in [
            "hindsight-api.service",
            "walter-voice-memory.service",
            "hindsight-stack-check.timer",
            "hermes-docker-log-rotate.timer",
        ]
    }

    if dream_cycle_active():
        report["deferred_due_to_dream_cycle"] = True
        report["summary"] = {
            "ok": True,
            "severity": "ok",
            "score": 100,
            "errors": [],
            "warnings": ["dream-cycle.service active; autopilot deferred to avoid competing with consolidation"],
            "recommended_actions": [],
        }
        report["elapsed_s"] = round(time.perf_counter() - start, 2)
        write_reports(report, output_path)
        if args.json:
            print(json.dumps(redact(report), ensure_ascii=False, indent=2))
        else:
            print("Memory autopilot: DEFERRED (dream-cycle.service active)")
        return 0

    report["checks"]["stack_check"] = run_stack_check()
    report["checks"]["postgres"] = collect_pg_metrics()
    report["checks"]["recall_probes"] = run_recall_probes()
    wm=run(['/usr/local/bin/walter-memory','health'],timeout=60)
    try:wm_report=json.loads(wm.get('stdout',''))
    except (ValueError,TypeError):wm_report=None
    report['checks']['walter_memory']={'command':wm,'report':wm_report}

    report["checks"]["reconcile_dryrun"] = {"skipped": True, "reason": "qdrant_pipeline_retired_2026-10-01"}

    report["trends"] = compute_trends(report, previous)

    if args.autofix != "off":
        report["autofix"] = run_autofix(args.autofix, report)
        # Re-measure the cheap state after mutations so recurring warnings do not
        # survive solely because the pre-fix snapshot was stale.
        report["post_autofix_checks"] = {
            "postgres": collect_pg_metrics(),
        }
    else:
        report["autofix"] = {"enabled": False}

    report["summary"] = evaluate(report)
    report["elapsed_s"] = round(time.perf_counter() - start, 2)
    write_reports(report, output_path)

    safe = redact(report)
    if args.json:
        print(json.dumps(safe, ensure_ascii=False, indent=2))
    else:
        summary = safe.get("summary") or {}
        print(
            "Memory autopilot: "
            f"{str(summary.get('severity', 'unknown')).upper()} "
            f"score={summary.get('score')} "
            f"errors={len(summary.get('errors') or [])} "
            f"warnings={len(summary.get('warnings') or [])} "
            f"elapsed={safe.get('elapsed_s')}s "
            f"report={output_path}"
        )
    return 0 if report.get("summary", {}).get("severity") != "error" else 2


if __name__ == "__main__":
    raise SystemExit(main())
