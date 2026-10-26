"""walter-context-preflight: one request (JSON on stdin) → one ContextPlan (JSON on stdout).

    {"turn_id": "...", "message": "...", "previous": {"message", "answer", "age_s", "thread_id"},
     "candidates": [{"id", "title", ...}], "privacy_class": "cloud_allowed", "default_thread": "session:<id>",
     "runtime": "claude_code", "session_id": "..."}

--shadow: the plan is only recorded (instance state, context/shadow/preflight-<day>.jsonl, private), nothing is
printed for injection. Used by the hook while lot 4 is in shadow mode. Fail-open: exit 0, a line in the record.
--refresh-router: refresh the cached Walter Router answers (task families, decision chain) and exit.
--report [--days N]: what the recorded shadow plans say (walter_context.shadow), read-only.
--serve: the warm service (walter_context.preflight.service, 127.0.0.1:8897) the bin script tries first.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import Exchange, Request, refresh_router, run


_STATE: list[Path | None] = []


def _instance_state() -> Path | None:
    if not _STATE:                                        # once per process: the service records many plans
        try:
            root = subprocess.run(["walter", "instance", "path"], capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return None
        _STATE.append(Path(root) / "state" / "context" / "shadow" if root else None)
    return _STATE[0]


def _record(row: dict) -> None:
    folder = _instance_state()
    if folder is None:
        return
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    path = folder / f"preflight-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def session_key(d: dict) -> str | None:
    """The walter_logs / Walter Memory key of the caller's session (Claude Code: claude_code/vm/<id>)."""
    sid, runtime = d.get("session_id"), d.get("runtime")
    if not sid or not runtime:
        return None
    return sid if "/" in sid else f"{runtime}/vm/{sid}"


def subjects(d: dict) -> tuple[list[dict], str | None, float | None]:
    """Candidate subjects from Walter Memory's views (local embeddings, warm in the service): (cards, waiting, age)."""
    try:
        from walter_memory import views
        r = views.subject_candidates(str(d.get("message") or "")[:4000], session_key(d))
        return r["candidates"], r["waiting"], r["waiting_age_s"]
    except Exception:  # noqa: BLE001 — no views: the preflight still runs, on the session alone
        return [], None, None


def handle(d: dict, shadow: bool) -> tuple[dict | None, dict]:
    """One request → (plan or None, record row). Shared by the CLI and the service; never raises.
    Without candidates in the request, the subjects come from Walter Memory (step D). In shadow mode the context
    pack the plan asks for is assembled and recorded next to the host's current injection, nothing is injected."""
    t0 = time.time()
    try:
        prev = dict(d.get("previous") or {}) or None
        cands, waiting, waiting_age = (list(d.get("candidates") or []), None, None)
        if not cands:
            cands, waiting, waiting_age = subjects(d)
            if waiting and prev:
                prev["thread_id"] = waiting
        req = Request(turn_id=str(d.get("turn_id") or f"t{int(t0 * 1000)}"), message=str(d.get("message") or ""),
                      previous=Exchange(**{k: prev.get(k) for k in ("message", "answer", "age_s", "thread_id")})
                      if prev else None,
                      candidates=cands, privacy_class=d.get("privacy_class") or "cloud_allowed",
                      default_thread=waiting or d.get("default_thread"))
        plan_obj = run(req, purpose="walter-context preflight" + (" (shadow)" if shadow else ""))
        plan = plan_obj.to_dict()
        row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "runtime": d.get("runtime"),
               "session_id": d.get("session_id"), "message_sha": hashlib.sha256(req.message.encode()).hexdigest()[:16],
               "message_head": req.message[:160], "plan": plan,
               "subjects": {"candidates": [c.get("id") for c in cands], "waiting": waiting,
                            "waiting_age_s": waiting_age}, "plan_ms": round((time.time() - t0) * 1000)}
        if shadow and req.privacy_class != "local_only":
            from ..assembly import pack
            from ..retrieval import gather
            blocks, notes = gather(plan_obj, req.message, session_key=session_key(d),
                                   native_history=d.get("runtime") in ("claude_code", "codex", "dsh"))
            p = pack(plan_obj, blocks, notes)
            cur = d.get("current_injection") or {}
            row["pack"] = p.summary()
            row["pack_text"] = p.text()
            row["current"] = {"tokens": len(cur.get("text") or "") // 4 + (1 if cur.get("text") else 0),
                              "parts": cur.get("parts"), "text": cur.get("text")}
    except Exception as exc:  # noqa: BLE001 — fail-open
        row, plan = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "error": f"{type(exc).__name__}: {str(exc)[:200]}"}, None
    if shadow:
        try:
            _record(row)
        except OSError:
            pass
    return plan, row


def main(argv: list[str]) -> int:
    if "--refresh-router" in argv:
        return 0 if refresh_router()["tasks"] else 1
    if "--report" in argv:
        from ..shadow import report
        days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 1
        folder = _instance_state()
        print(json.dumps(report(folder, days) if folder else {"error": "no instance"}, ensure_ascii=False, indent=1))
        return 0
    if "--serve" in argv:
        from .service import serve
        return serve()
    shadow = "--shadow" in argv
    try:
        d = json.loads(sys.stdin.read() or "{}")
    except ValueError as exc:
        if not shadow:
            print(json.dumps({"error": f"invalid request: {exc}"[:200]}))
        return 0 if shadow else 1
    plan, row = handle(d, shadow)
    if shadow:
        return 0
    print(json.dumps(plan if plan is not None else row, ensure_ascii=False))
    return 0 if plan is not None else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
