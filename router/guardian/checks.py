"""Deterministic detection: what is wrong with the module right now. No model is called here.

Each problem is a dict {key, kind, subject, detail}; `key` is stable across checks so one incident follows it.
"""
from __future__ import annotations

import os
import re
import subprocess

from walter_router import paths
from walter_router.analysis import alerts

RUN_MAX_AGE_H = 54        # the cycle runs every 48 h
TEST_TIMEOUT = 600

# A provider answer that says the request itself is wrong (renamed model, changed API): worth a look at our side.
# Anything else (5xx, 429, a stream ending on a provider error, a timeout) is the provider's outage: wait.
_OUR_SIDE = re.compile(r"^HTTP (400|404|405|410|415|422)\b")
_ACCOUNT = re.compile(r"^HTTP (401|402|403)\b|crédit épuisé")


def sources(conn) -> list[dict]:
    out = []
    for r in conn.execute("""select kind, extract(epoch from now() - fetched_at) / 3600 as age_h
                             from models.latest_snapshots"""):
        limit = alerts.STALE_HOURS.get(r["kind"], 48)
        if float(r["age_h"]) > limit:
            out.append({"key": f'source:{r["kind"]}', "kind": "source_stale", "subject": r["kind"],
                        "detail": {"age_h": round(float(r["age_h"]), 1), "limit_h": limit}})
    last = conn.execute("select summary from models.runs order by run_id desc limit 1").fetchone()
    for kind, info in (((last or {}).get("summary") or {}).get("sources") or {}).items():
        if "error" in info and not any(p["subject"] == kind for p in out):
            out.append({"key": f"source:{kind}", "kind": "source_error", "subject": kind,
                        "detail": {"error": str(info["error"])[:500]}})
    return out


def cycle(conn) -> list[dict]:
    last = conn.execute("""select run_id, status, summary, now() - coalesce(finished_at, started_at) as age
                           from models.runs order by run_id desc limit 1""").fetchone()
    ok = conn.execute("""select extract(epoch from now() - finished_at) / 3600 as h from models.runs
                         where status = 'ok' order by run_id desc limit 1""").fetchone()
    if last and last["status"] == "failed":
        return [{"key": "cycle", "kind": "cycle_failed", "subject": f'run {last["run_id"]}',
                 "detail": {"error": str((last["summary"] or {}).get("error", "?"))[:500]}}]
    if ok and float(ok["h"]) > RUN_MAX_AGE_H:
        return [{"key": "cycle", "kind": "cycle_failed", "subject": "no successful cycle",
                 "detail": {"hours_since_ok": round(float(ok["h"]), 1)}}]
    return []


def provider_side(detail: str) -> str:
    """'ours' (the request looks wrong: repairable here), 'account' (key, credit: the owner's), 'external'."""
    if _ACCOUNT.search(detail or ""):
        return "account"
    return "ours" if _OUR_SIDE.search(detail or "") else "external"


def providers(conn) -> list[dict]:
    return [{"key": f'provider:{r["provider"]}', "kind": "provider_down", "subject": r["provider"],
             "detail": {"probe": r["detail"], "checked_at": str(r["checked_at"]), "side": provider_side(r["detail"])}}
            for r in conn.execute("select provider, detail, checked_at from models.provider_status where not ok")]


def dirty_paths(root=None) -> set[str]:
    """Files with uncommitted changes in the live module (someone's work in progress), relative to its root."""
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root or paths.ROOT,
                         capture_output=True, text=True, timeout=60)
    return {line[3:].split(" -> ")[-1].strip() for line in out.stdout.splitlines() if line.strip()}


_FAILED = re.compile(r"^(FAILED|ERROR) (\S+?)(?: - (.*))?$")


def run_tests(root, timeout: int = TEST_TIMEOUT) -> dict:
    """The module's test suite in `root`: {ok, failures: {node id: one-line reason}, tail}."""
    proc = subprocess.run([str(root / "venv" / "bin" / "python"), "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider",
                           "--continue-on-collection-errors", "tests"], cwd=root, capture_output=True, text=True,
                          timeout=timeout, env={**os.environ, "COLUMNS": "400"})
    failures = {}
    for line in proc.stdout.splitlines():
        m = _FAILED.match(line.strip())
        if m:
            failures[m.group(2)] = (m.group(3) or m.group(1))[:300]
    return {"ok": proc.returncode == 0, "failures": failures, "tail": proc.stdout[-3000:]}


def tests(root=None) -> list[dict]:
    """Failing tests, except those whose test file is itself someone's uncommitted work (still being written)."""
    root = root or paths.ROOT
    res = run_tests(root)
    busy = dirty_paths(root)
    return [{"key": f"test:{node}", "kind": "test_failure", "subject": node, "detail": {"reason": why}}
            for node, why in res["failures"].items() if node.split("::")[0] not in busy]


def detect(conn, with_tests: bool = True) -> list[dict]:
    found = sources(conn) + cycle(conn) + providers(conn)
    return found + (tests() if with_tests else [])
