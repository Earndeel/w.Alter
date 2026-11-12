"""walter-context-preflight: one request (JSON on stdin) → one ContextPlan (JSON on stdout).

    {"turn_id": "...", "message": "...", "previous": {"message", "answer", "age_s", "thread_id"},
     "candidates": [{"id", "title", ...}], "privacy_class": "cloud_allowed", "default_thread": "session:<id>",
     "runtime": "claude_code", "session_id": "..."}

--shadow: the plan is only recorded (instance state, context/shadow/preflight-<day>.jsonl, private), nothing is
printed for injection. Used by the hook while lot 4 is in shadow mode. Fail-open: exit 0, a line in the record.
--refresh-router: refresh the cached Walter Router answers (task families, decision chain) and exit.
--report [--days N]: what the recorded plans say (walter_context.shadow), degraded plans counted apart; read-only.

A request without `previous` but with a session (the engine's native intake) gets the session's last owner/assistant
exchange from walter_logs (Walter Memory's logs API, cloud-safe, bounded, [preflight] previous_*), so short replies,
the plan floor and the intent are judged in their conversation. A degraded plan (decision failure, SOCLE A2) is
recorded with `decision.degraded`, announced on the Walter bus (`context.degraded`) and returned with `degraded: true`.
--serve: the warm service (walter_context.preflight.service, 127.0.0.1:8897) the bin script tries first.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import SETTINGS, Exchange, Request, refresh_router, run


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


# A machine turn (a sub-agent's mission, a delegated sub-task) is bounded work: one text tier below what the same
# words would get from the owner, never under L1 (2026-11-10: three L2 sub-agents of one V1 turn made 84 Opus calls).
SUBTASK_TIER = {"L3": "L2", "L2": "L1"}


def requested(plan: dict, message: str, channel: str | None = None) -> dict:
    """What this turn asks of Walter Router (lot 2, 2026-11-07): read by the model gateway from the run. A rule's
    answer travels with the hash of the owner's message it answers, so it is only ever returned for that message."""
    profile = plan.get("model_profile") or {}
    level = profile.get("level")
    if channel == "machine":
        level = SUBTASK_TIER.get(level, level)
    out = {"task": profile.get("task"), "level": level, "require": profile.get("require") or None,
           "fast_path": plan.get("fast_path")}
    if (plan.get("decision") or {}).get("degraded"):
        out["degraded"] = True          # Run Plane: needs `degraded` in walter_memory.runs.REQUESTED_KEYS to be kept
    work = (plan.get("decision") or {}).get("work")
    if isinstance(work, (int, float)) and not isinstance(work, bool):
        out["work"] = work >= 0.5       # the Run Plane opens a durable task on it (walter_memory.runs.actionable)
    if plan.get("answer"):
        out.update(answer=plan["answer"], message_sha=hashlib.sha256(message.strip().encode()).hexdigest())
    return out


def _attach_run(run_id: str, plan: dict, message: str = "", channel: str | None = None) -> None:
    """Walter Memory's Run Plane through its command (declared interface); never blocks the preflight."""
    import subprocess
    thread = (plan.get("thread") or {}).get("id")
    try:
        subprocess.run(["walter-memory", "runs", "update"], input=json.dumps(
            {"run_id": run_id, "level": plan.get("level"), "act": plan.get("act"),
             "thread_id": thread if thread and thread != "new" else None,
             "requested": requested(plan, message, channel)}),
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pass


_POOL: list = []


def _bounded(fn, timeout: float):
    """fn() within timeout seconds, on a shared worker thread (a slow database never holds the plan)."""
    from concurrent.futures import ThreadPoolExecutor
    if not _POOL:
        _POOL.append(ThreadPoolExecutor(max_workers=4, thread_name_prefix="preflight-io"))
    return _POOL[0].submit(fn).result(timeout=timeout)


def last_exchange(key: str, message: str, reader=None, now: float | None = None) -> dict | None:
    """The session's last owner message and the answer to it (walter_logs through Walter Memory's logs API, cloud-safe:
    a local_only event comes back masked). The new message itself, if already journaled, is skipped."""
    n = SETTINGS["previous_chars"]
    if reader is None:
        def reader():
            from walter_memory import logs
            from walter_memory.db import connection
            with connection() as conn:
                return logs.timeline(conn, key, before=8, after=0, types=["user/message", "assistant/message"],
                                     max_chars=n, max_privacy="cloud_allowed")
    res = reader() or {}
    evs = [e for e in res.get("events") or [] if e.get("text")]
    head = re.sub(r"\s+", " ", message or "").strip()[:200]
    owner = [i for i, e in enumerate(evs) if e.get("type") == "user/message"
             and re.sub(r"\s+", " ", e["text"]).strip()[:200] != head]
    if not owner:
        return None
    i = owner[-1]
    answer = next((e for e in evs[i + 1:] if e.get("type") == "assistant/message"), None)
    last = answer or evs[i]
    at = last.get("occurred_at")
    if isinstance(at, str):
        at = datetime.fromisoformat(at)
    age = ((now or time.time()) - at.timestamp()) if at is not None else None
    return {"message": evs[i]["text"][:n], "answer": (answer or {}).get("text", "")[:n],
            "age_s": round(age, 1) if age is not None else None}


_PROFILES: dict[str, tuple[float, dict]] = {}       # session key → (time, model profile) of its last decided plan


def previous_profile(key: str | None, now: float | None = None) -> dict | None:
    """The model profile of the session's previous decided plan when recent ([preflight] degraded_profile_max_age_s):
    this process's memory first, then today's journal (a restarted service)."""
    if not key:
        return None
    now = now or time.time()
    hit = _PROFILES.get(key)
    if hit is None:
        folder = _instance_state()
        path = folder / f"preflight-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl" if folder else None
        try:
            lines = path.read_text().splitlines()[-400:] if path and path.exists() else []
        except OSError:
            lines = []
        for line in reversed(lines):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            plan = r.get("plan") or {}
            if r.get("session_id") and session_key(r) == key and plan.get("model_profile") \
                    and not (plan.get("decision") or {}).get("degraded"):
                hit = (datetime.fromisoformat(r["at"]).timestamp(), plan["model_profile"])
                break
    if hit and now - hit[0] <= SETTINGS["degraded_profile_max_age_s"]:
        return hit[1]
    return None


def _signal_degraded(d: dict, plan: dict) -> None:
    """Walter bus `context.degraded` (Walter Memory's bus library, the same public client the hook uses); never raises.
    Numbers and identifiers only: no message text."""
    try:
        from walter_memory import bus
        bus.emit("context.degraded", "walter-context", session_key(d) or d.get("session_id"),
                 {"turn_id": plan.get("turn_id"), "run_id": d.get("run_id"), "runtime": d.get("runtime"),
                  "error": (plan.get("decision") or {}).get("error"), "level": plan.get("level"),
                  "profile_from": (plan.get("decision") or {}).get("profile_from")},
                 dedupe_key=f"context.degraded:{plan.get('turn_id')}")
    except Exception:  # noqa: BLE001 — the signal never blocks the turn
        pass


def handle(d: dict, shadow: bool, want_pack: bool = False, warm: bool = False) -> tuple[dict | None, dict]:
    """One request → (plan or None, record row). Shared by the CLI and the service; never raises. `warm`: the
    service's own start-up request (nothing recorded, nothing signalled).
    Without candidates in the request, the subjects come from Walter Memory (step D). In shadow mode the context
    pack the plan asks for is assembled and recorded next to the host's current injection, nothing is injected."""
    t0 = time.time()
    try:
        prev = dict(d.get("previous") or {}) or None
        prev_note = None
        key = session_key(d)
        if prev is None and key:
            try:
                prev = _bounded(lambda: last_exchange(key, str(d.get("message") or "")), SETTINGS["previous_timeout_s"])
                prev_note = "fetched" if prev else "none"
            except Exception as exc:  # noqa: BLE001 — the plan is made without it, noted in the journal
                prev_note = f"failed: {type(exc).__name__}"
        cands, waiting, waiting_age = (list(d.get("candidates") or []), None, None)
        if not cands:
            cands, waiting, waiting_age = subjects(d)
            if waiting and prev:
                prev["thread_id"] = waiting
        req = Request(turn_id=str(d.get("turn_id") or f"t{int(t0 * 1000)}"), message=str(d.get("message") or ""),
                      previous=Exchange(**{k: prev.get(k) for k in ("message", "answer", "age_s", "thread_id")})
                      if prev else None,
                      candidates=cands, privacy_class=d.get("privacy_class") or "cloud_allowed",
                      default_thread=waiting or d.get("default_thread"), waiting_age_s=waiting_age,
                      previous_profile=previous_profile(key))
        plan_obj = run(req, purpose="walter-context preflight" + (" (shadow)" if shadow else ""))
        plan = plan_obj.to_dict()
        degraded = bool(plan_obj.decision.get("degraded"))
        if key and not degraded and not plan_obj.fast_path and plan_obj.decision.get("model"):
            _PROFILES[key] = (time.time(), plan["model_profile"])
        row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "runtime": d.get("runtime"),
               "session_id": d.get("session_id"), "message_sha": hashlib.sha256(req.message.encode()).hexdigest()[:16],
               "message_head": req.message[:160], "plan": plan,
               "subjects": {"candidates": [c.get("id") for c in cands], "waiting": waiting,
                            "waiting_age_s": waiting_age}, "plan_ms": round((time.time() - t0) * 1000)}
        if prev_note:
            row["previous"] = prev_note
        if degraded:
            row["degraded"] = True
            if not shadow and not warm:  # an observation never reaches the production bus
                _signal_degraded(d, plan)
        if d.get("run_id"):                 # Walter Run Plane: the plan's level and thread belong to the run
            row["run_id"] = d["run_id"]
            _attach_run(d["run_id"], plan, req.message, d.get("channel"))
        if (shadow or want_pack) and req.privacy_class != "local_only":
            from ..assembly import pack
            from ..retrieval import gather
            blocks, notes = gather(plan_obj, req.message, session_key=key,
                                   native_history=d.get("runtime") in ("claude_code", "codex", "dsh"))
            skip = set(d.get("exclude_blocks") or [])      # what the host already shows natively (its profile)
            blocks = [b for b in blocks if b.id not in skip]
            row["mode"] = "inject" if want_pack else "shadow"
            p = pack(plan_obj, blocks, notes)
            cur = d.get("current_injection") or {}
            row["pack"] = p.summary()
            row["pack_text"] = p.text()
            row["current"] = {"tokens": len(cur.get("text") or "") // 4 + (1 if cur.get("text") else 0),
                              "parts": cur.get("parts"), "text": cur.get("text")}
    except Exception as exc:  # noqa: BLE001 — fail-open
        row, plan = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "error": f"{type(exc).__name__}: {str(exc)[:200]}"}, None
    if (shadow or want_pack) and not warm:
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
