"""Walter Engine — taking over the conversations DSH ran (2026-11-17).

The switch to the native engine keeps every conversation where it was: each DSH session journal
(`<dsh_home>/sessions/<cwd>/session-<id>/session.v4.jsonl.zstd`) becomes a native journal with the SAME id and the
SAME seq numbers (a client resumes at the seq it had; the Walter key stays `dsh/vm/<id>` in runs, walter_logs and
skills), translated to the native vocabulary:

  turn/start, turn/end            kept (status from the end reason)
  user/message                    text of its blocks; DSH's per-turn system copies (agent-instructions,
                                  runtime-context) are dropped: the native engine writes its own system prompt
  assistant/message               text, reasoning, tool calls
  tool/call, tool/result          kept (the result carries its call's name)
  compaction/summary + the        one compaction/window: cut after the shadowed range, content = the checkpoint text
  compact-checkpoint message      the model saw
  session/title, approval/*       kept

Everything else DSH journaled for its own machinery (steps, hooks, requests, permission presets, model selection…)
stays in the DSH file, which is never modified (walter_logs already holds it in full under runtime `dsh`).

Also taken over: the Engine API bindings (door ↔ session), the web interface's browser-session secret (signed-in
browsers stay signed in; never printed), and the DSH web sessions that had no binding (they become `web/owner/<id>`).
Idempotent: a session already imported is skipped unless its DSH file has grown since (then re-imported, only when
the native engine has not written to it yet).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

DROP_SOURCES = {"agent-instructions", "runtime-context"}
KEEP_TYPES = {"turn/start", "turn/end", "user/message", "assistant/message", "tool/call", "tool/result",
              "session/title", "compaction/summary", "approval/asked", "approval/decided"}
STATUS = {"completed": "ok", "forked": "ok", "max-tokens": "ok", "aborted": "cancelled", "blocked": "budget_exhausted",
          "error": "error", "interrupted": "interrupted"}


def read_dsh(path: Path) -> list[dict]:
    import zstandard
    with open(path, "rb") as fh:
        raw = zstandard.ZstdDecompressor().stream_reader(fh, read_across_frames=True).read()
    out = []
    for line in raw.split(b"\n"):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue                        # a torn last frame: what was written before stays readable
    return out


def _texts(blocks, kind: str = "text") -> str:
    return "\n".join(b.get("text") or "" for b in blocks or [] if isinstance(b, dict) and b.get("type") == kind).strip()


def convert(lines: list[dict]) -> tuple[dict, list[dict], dict]:
    """DSH journal lines → (native header fields, native events, stats)."""
    head = lines[0] if lines and lines[0].get("type") == "session" else {}
    events: list[dict] = []
    names: dict[str, str] = {}
    pending_cut: int | None = None
    stats = {"kept": 0, "dropped": 0, "windows": 0}
    for e in lines[1:]:
        t, d, seq, at = e.get("type"), e.get("data") or {}, e.get("seq"), e.get("time")
        if t not in KEEP_TYPES or not isinstance(seq, int):
            stats["dropped"] += 1
            continue
        nd: dict | None = None
        nt = t
        if t == "turn/start":
            nd = {"turn": d.get("turn")}
        elif t == "turn/end":
            reason = d.get("reason") if isinstance(d.get("reason"), dict) else {"kind": d.get("reason") or "completed"}
            nd = {"turn": d.get("turn"), "status": STATUS.get(reason.get("kind"), "unknown_outcome"), "reason": reason}
        elif t == "user/message":
            src = d.get("source") or {}
            kind = src.get("kind")
            if kind in DROP_SOURCES:
                stats["dropped"] += 1
                continue
            text = _texts(d.get("content"))
            if kind == "compact-checkpoint":
                if pending_cut is None:
                    stats["dropped"] += 1
                    continue
                nt, nd = "compaction/window", {"cut_seq": pending_cut, "content": text, "reason": "dsh-compaction",
                                               "imported": True}
                pending_cut = None
                stats["windows"] += 1
            else:
                s2 = {"kind": kind or "user"}
                if src.get("rpcId"):
                    s2["rpcId"] = src["rpcId"]
                nd = {"text": text, "turn": d.get("turn"), "source": s2}
        elif t == "assistant/message":
            msg = d.get("message") or {}
            blocks = msg.get("content") or []
            calls = [{"id": b.get("id"), "name": b.get("name"),
                      "arguments": b.get("arguments") if isinstance(b.get("arguments"), str)
                      else json.dumps(b.get("arguments") or {}, ensure_ascii=False)}
                     for b in blocks if isinstance(b, dict) and b.get("type") == "tool-call"]
            for c in calls:
                names[c["id"]] = c["name"]
            nd = {"turn": d.get("turn"), "step": d.get("step"), "text": _texts(blocks),
                  "reasoning": _texts(blocks, "reasoning") or None, "tool_calls": calls,
                  **({"usage": d["usage"]} if d.get("usage") else {})}
        elif t == "tool/call":
            names[d.get("callId")] = d.get("name")
            args = d.get("arguments")
            nd = {"turn": d.get("turn"), "step": d.get("step"), "callId": d.get("callId"), "name": d.get("name"),
                  "arguments": args if isinstance(args, str) else json.dumps(args or {}, ensure_ascii=False)}
        elif t == "tool/result":
            msg = d.get("message") or {}
            cid = msg.get("toolCallId")
            nd = {"turn": d.get("turn"), "step": d.get("step"), "callId": cid, "name": names.get(cid),
                  "content": _texts(msg.get("content")), "isError": bool(msg.get("isError"))}
        elif t == "session/title":
            nd = {"title": d.get("title"), "by": (d.get("source") or "dsh") if isinstance(d.get("source"), str) else "dsh"}
        elif t == "compaction/summary":
            rng = d.get("shadowedRange") or {}
            if isinstance(rng.get("end"), int):
                pending_cut = rng["end"] + 1
            stats["dropped"] += 1
            continue
        elif t == "approval/asked":
            nd = {"request_id": d.get("id"), "tool": d.get("toolName"), "reason": d.get("reason"), "callId": d.get("callId")}
        elif t == "approval/decided":
            nd = {"request_id": d.get("id"), "outcome": d.get("outcome")}
        events.append({"type": nt, "seq": seq, "time": at, "data": nd})
        stats["kept"] += 1
    events.sort(key=lambda x: x["seq"])
    created = head.get("createdAt")
    if isinstance(created, str):
        try:
            created = int(time.mktime(time.strptime(created[:19], "%Y-%m-%dT%H:%M:%S")) * 1000)
        except ValueError:
            created = None
    hdr = {"created_at": created or (events[0]["time"] if events else None), "cwd": head.get("cwd") or "/",
           "depth": int(head.get("delegationDepth") or 0), "parent": head.get("parentSession"),
           "seq_base": max((e.get("seq") or 0 for e in lines[1:] if isinstance(e.get("seq"), int)), default=0)}
    return hdr, events, stats


def _principal(row: dict) -> dict:
    """The row's principal as Core's identity resolves it now (`e2e` is a test account on every door)."""
    from .api import principal_of
    try:
        return principal_of(row)
    except Exception:  # noqa: BLE001 — unresolvable: never the owner
        return {"kind": "machine", "id": str((row.get("principal") or {}).get("id") or "unknown")}


def _open_turn(events: list[dict]) -> bool:
    open_ = None
    for e in events:
        if e["type"] == "turn/start":
            open_ = e["data"].get("turn")
        elif e["type"] == "turn/end" and e["data"].get("turn") == open_:
            open_ = None
    return open_ is not None


def _dsh_files(dsh_home: Path) -> dict[str, Path]:
    out = {}
    for f in (dsh_home / "sessions").glob("*/session-*/session.v4.jsonl.zstd"):
        out[f.parent.name] = f
    return out


def import_sessions(dsh_home: Path, store_root: Path, bindings_file: Path, *, only: set | None = None,
                    workspace: str | None = None) -> dict:
    """Import every bound session (and the unbound DSH web sessions of the main workspace). Returns a report."""
    store_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    rows = {}
    if bindings_file.exists():
        rows = (json.loads(bindings_file.read_text()) or {}).get("sessions") or {}
    by_kernel = {r.get("kernel"): r for r in rows.values() if r.get("kernel")}
    files = _dsh_files(dsh_home)
    report = {"imported": 0, "skipped": 0, "refreshed": 0, "kept_events": 0, "dropped_events": 0, "windows": 0,
              "new_bindings": 0, "missing": [], "errors": []}
    new_rows = {}
    for sid, f in sorted(files.items()):
        if only is not None and sid not in only:
            continue
        lines = None
        row = by_kernel.get(sid)
        if row is None:
            # a DSH web session without a binding: taken over only from the main workspace, and only if it has turns
            try:
                lines = read_dsh(f)
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"{sid}: {type(e).__name__}")
                continue
            head = lines[0] if lines else {}
            if (workspace and head.get("cwd") != workspace) or not any(x.get("type") == "turn/start" for x in lines[1:]):
                continue
            row = {"session_id": f"web/owner/{sid}", "kernel": sid, "interface": "web", "door": "web",
                   "mode": "interactive", "principal": {"kind": "owner", "id": "owner"},
                   "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime((head.get("createdAt") or 0) / 1000))
                   if isinstance(head.get("createdAt"), (int, float)) else None, "imported_from": "dsh"}
            new_rows[row["session_id"]] = row
        dst = store_root / f"{sid}.jsonl"
        src_mtime = f.stat().st_mtime
        if dst.exists():
            try:
                with open(dst, encoding="utf-8") as fh:
                    h = json.loads(fh.readline())
                    native_written = any(json.loads(x).get("seq", 0) > h.get("seq_base", 0) for x in fh if x.strip())
            except (OSError, ValueError):
                native_written, h = True, {}
            if native_written or h.get("dsh_mtime", 0) >= src_mtime:
                report["skipped"] += 1
                continue
            report["refreshed"] += 1
        try:
            lines = lines or read_dsh(f)
            hdr, events, st = convert(lines)
        except Exception as e:  # noqa: BLE001 — one unreadable journal never stops the others
            report["errors"].append(f"{sid}: {type(e).__name__}: {str(e)[:120]}")
            continue
        principal = _principal(row)
        header = {"type": "session", "version": 1, "engine": "walter", "id": sid, **hdr,
                  "origin": principal.get("kind", "owner"), "door": row.get("door"),
                  "walter_key": f"dsh/vm/{sid}", "principal": principal, "interface": row.get("interface"),
                  "imported_from": "dsh", "dsh_file": str(f), "dsh_mtime": src_mtime}
        tmp = dst.with_name(dst.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(header, ensure_ascii=False) + "\n")
            for ev in events:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dst)
        report["imported"] += 1
        if _open_turn(events):
            report.setdefault("open_turns", []).append(sid)   # closed `interrupted` (and resumed) by the engine at start
        report["kept_events"] += st["kept"]
        report["dropped_events"] += st["dropped"]
        report["windows"] += st["windows"]
    for row in rows.values():
        if row.get("kernel") and row["kernel"] not in files:
            report["missing"].append(row["session_id"])
    if new_rows:
        rows.update(new_rows)
        report["new_bindings"] = len(new_rows)
        tmp = bindings_file.with_name(bindings_file.name + f".tmp-{os.getpid()}")
        bindings_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps({"version": 1, "sessions": rows}, indent=1, ensure_ascii=False) + "\n")
        os.replace(tmp, bindings_file)
    return report


def import_web_secret(dsh_home: Path, state: Path) -> bool:
    """DSH's browser-session secret → the native web's cookie secret (browsers stay signed in). Never printed."""
    import yaml
    try:
        doc = yaml.safe_load((dsh_home / ".credentials.yaml").read_text()) or {}
    except (OSError, ValueError):
        return False
    secret = (((doc.get("records") or {}).get("client-connection/browser-session") or {}).get("payload") or {}).get("secret")
    if not isinstance(secret, str) or len(secret) < 40:
        return False
    d = state / "web"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = d / "cookie.secret.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(secret.strip() + "\n")
    os.replace(tmp, d / "cookie.secret")
    return True
