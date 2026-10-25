"""walter-context-preflight: one request (JSON on stdin) → one ContextPlan (JSON on stdout).

    {"turn_id": "...", "message": "...", "previous": {"message", "answer", "age_s", "thread_id"},
     "candidates": [{"id", "title", ...}], "privacy_class": "cloud_allowed", "default_thread": "session:<id>",
     "runtime": "claude_code", "session_id": "..."}

--shadow: the plan is only recorded (instance state, context/shadow/preflight-<day>.jsonl, private), nothing is
printed for injection. Used by the hook while lot 4 is in shadow mode. Fail-open: exit 0, a line in the record.
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

from . import Exchange, Request, run


def _instance_state() -> Path | None:
    try:
        root = subprocess.run(["walter", "instance", "path"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(root) / "state" / "context" / "shadow" if root else None


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


def main(argv: list[str]) -> int:
    shadow = "--shadow" in argv
    t0 = time.time()
    try:
        d = json.loads(sys.stdin.read() or "{}")
        prev = d.get("previous") or None
        req = Request(turn_id=str(d.get("turn_id") or f"t{int(t0 * 1000)}"), message=str(d.get("message") or ""),
                      previous=Exchange(**{k: prev.get(k) for k in ("message", "answer", "age_s", "thread_id")})
                      if prev else None,
                      candidates=list(d.get("candidates") or []),
                      privacy_class=d.get("privacy_class") or "cloud_allowed",
                      default_thread=d.get("default_thread"))
        plan = run(req, purpose="walter-context preflight" + (" (shadow)" if shadow else "")).to_dict()
        row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "runtime": d.get("runtime"),
               "session_id": d.get("session_id"), "message_sha": hashlib.sha256(req.message.encode()).hexdigest()[:16],
               "message_head": req.message[:160], "plan": plan}
    except Exception as exc:  # noqa: BLE001 — fail-open
        row, plan = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "error": f"{type(exc).__name__}: {str(exc)[:200]}"}, None
    if shadow:
        try:
            _record(row)
        except OSError:
            pass
        return 0
    print(json.dumps(plan if plan is not None else row, ensure_ascii=False))
    return 0 if plan is not None else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
