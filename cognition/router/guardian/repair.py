"""Repair of one incident by the guardians' common repair agent (2026-11-20).

Owner, 2026-11-20: « les guardians des modules doivent pouvoir agir comme moi je le ferais » — an alert, one
message to Opus in a Claude Code session, problem solved. The Router no longer runs its own agent on a read-only copy
behind file gates (that agent could not run a single command once `walter_run` went through the engine, and the
copy's read-only mounts no longer protected anything). It hands the incident to `walter-guardian repair` (walter-core,
a command on the PATH): one Walter Engine delegation as `guardian-router`, poste coding/L3, with the rights of a
development session (shell and files; outgoing messages never), the module's notes from `guardian/playbook.json`.
Whatever the agent says, run.py checks the incident again before calling it fixed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from walter_router import instance, paths
from walter_router.guardian import checks

AGENT_TIMEOUT_S = 3600 + 600     # the engine caps a delegation at one hour


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", "-c", "user.name=Walter Router Guardian", *args], cwd=cwd, capture_output=True,
                          text=True, timeout=120, check=check).stdout


def agent(incident: dict, tried: str = "") -> dict:
    """The common repair agent on this incident (blocking): {ok, verdict, model, engine…}."""
    inc = {"module": "router", "key": incident["key"], "kind": incident["kind"], "subject": incident["subject"],
           "severity": "high", "summary": f'{incident["kind"]} {incident["subject"]}',
           "evidence": incident.get("detail") or {}, "opened_at": str(incident.get("opened_at"))}
    work = instance.state_file("guardian") / "repair"
    work.mkdir(parents=True, exist_ok=True)
    f = work / f'{incident["incident_id"]}.json'
    f.write_text(json.dumps({"incident": inc, "tried": tried}, ensure_ascii=False, default=str))
    try:
        proc = subprocess.run(["walter-guardian", "repair", "--module", "router", "--incident-file", str(f), "--wait"],
                              capture_output=True, text=True, timeout=AGENT_TIMEOUT_S)
        out = json.loads(proc.stdout or "{}")
    except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
        return {"ok": False, "error": type(exc).__name__, "verdict": {"outcome": "unknown"}}
    eng = out.get("engine") or {}
    return {"ok": bool(eng.get("ok")), "error": eng.get("error") or out.get("error"),
            "verdict": out.get("verdict") or {"outcome": "unknown"}, "poste": out.get("poste"),
            "walter_session": eng.get("walter_session"), "tools": eng.get("tools"), "seconds": out.get("seconds")}


def regenerate_docs(message: str) -> dict:
    """Generated reference out of date: regenerate it (no model), and commit the regenerated files alone, unless one
    of them is someone's uncommitted work."""
    busy = checks.dirty_paths()
    stale = checks.docs_check().get("stale") or []
    blocked = [p for p in stale if p in busy]
    if blocked:
        return {"applied": False, "deferred": True, "blocked": blocked}
    proc = subprocess.run(["walter-router", "docs", "--write"], capture_output=True, text=True, timeout=600)
    after = checks.docs_check()
    if proc.returncode or not after.get("ok"):
        return {"applied": False, "error": (proc.stderr or proc.stdout)[-500:] or after.get("error"), "check": after}
    changed = sorted(checks.dirty_paths() - busy)
    if not changed:
        return {"applied": True, "files": [], "commit": None}
    if any(not p.startswith("docs/reference/") for p in changed):
        return {"applied": True, "files": changed, "commit": None, "note": "files outside docs/reference left uncommitted"}
    root = paths.ROOT
    _git(root, "add", "--", *changed)
    email = _git(root, "config", "user.email", check=False).strip() or "guardian@localhost"
    _git(root, "-c", f"user.email={email}", "commit", "-q", "-m", message, "--", *changed)
    return {"applied": True, "files": changed, "commit": _git(root, "rev-parse", "--short", "HEAD").strip()}


def prune(days: int = 7, keep: set[str] = frozenset()) -> int:
    """Old work folders of the guardian go (the former copies of the module included)."""
    root = instance.state_file("guardian")
    if not root.exists():
        return 0
    n = 0
    for d in root.iterdir():
        if d.is_dir() and d.name != "repair" and str(d) not in keep and time.time() - d.stat().st_mtime > days * 86400:
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return n
