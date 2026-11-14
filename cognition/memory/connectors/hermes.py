#!/usr/bin/env python3
"""Hermes connector (P2.2, A1/D1): W.Alter conversations → core.events, independent of state.db.

Reads /root/.hermes/state.db read-only (state.db stays Hermes' operational store) and records:
  - conversation.started / conversation.ended for every session (platform, model, title, counts, cost);
  - for interactive sessions (Monsieur talking to W.Alter): one event per message — message.sent (Monsieur) /
    message.received (W.Alter) with session_id, message_id, role, timestamp, text, reply_to, attachments;
  - nothing about tool calls: what the agent executed (calls, arguments, results, skills) is walter_logs' job, the
    canonical journal of agent execution (tool.called / skill.used retired 2026-11-09, cleanup phase 2);
  - attachments referenced in messages ("[Image attached at: …]") stored once in the Raw Vault.
System-injected rows (compaction summaries, delegation/process notices, model switches) are not Monsieur's
words and are skipped. `--export` writes the daily raw JSONL.zst copy of state.db rows into the Raw Vault (D1).

Usage: hermes.py [--max N] [--export]      (idempotent; checkpoints in ingestion.checkpoints)
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import zstandard  # noqa: E402

from walter_memory import events, ingestion, objects  # noqa: E402
from walter_memory.db import connection  # noqa: E402

STATE_DB = "file:/root/.hermes/state.db?mode=ro"
CONNECTOR = "hermes"
PROFILES_DIR = "/root/.hermes/profiles"
# Hermes profiles have their own state.db (the macOS app uses `wild`). Each profile is its own connector checkpoint;
# its source ids are prefixed with the profile name. `wild` (uncensored chats) never leaves the VM: local_only.
PROFILE_PRIVACY = {"wild": "local_only"}
PROFILE = ""  # set by --profile; "" = main profile
INTERACTIVE = {"desktop", "tui", "cli", "telegram", "api_server", "voice-router", "whatsapp", "discord", "signal",
               "slack", "email", "sms", "matrix", "web"}
ATTACH_RE = re.compile(r"\[(?:Image|File|Audio|Voice|Document) attached at: ([^\]]+)\]")
MONSIEUR = {"external_id": "monsieur", "display_name": "Monsieur", "is_self": True}
WALTER = {"external_id": "walter", "display_name": "W.Alter"}
BATCH = 2000


def ts(v) -> datetime:
    return datetime.fromtimestamp(float(v), tz=timezone.utc)


def attachments(text: str, session_id: str, conn) -> tuple[list[str], list[dict]]:
    refs, meta = [], []
    for path in ATTACH_RE.findall(text or ""):
        p = Path(path.strip())
        item = {"name": p.name, "path": str(p)}
        if p.is_file():
            row = objects.put_object(p, "hermes", links=[("hermes_session", session_id)],
                                     source_ref={"state_db_session": session_id, "profile": PROFILE or None},
                                     privacy_class=PROFILE_PRIVACY.get(PROFILE), conn=conn)
            refs.append(str(row["id"])); item["object_id"] = str(row["id"])
        else:
            item["missing"] = True
        meta.append(item)
    return refs, meta


def _sid(x: str) -> str:
    return f"{PROFILE}:{x}" if PROFILE else x


def _acct(platform: str) -> str:
    return f"{PROFILE}/{platform}" if PROFILE else platform


def _finish(e: dict) -> dict:
    if PROFILE:
        e["payload"] = {**(e.get("payload") or {}), "profile": PROFILE}
        if PROFILE in PROFILE_PRIVACY:
            e["privacy_class"] = PROFILE_PRIVACY[PROFILE]
    return e


def sync_sessions(db, conn) -> int:
    cur = ingestion.get_checkpoint(CONNECTOR, "sessions")
    since = float(cur.get("activity", 0))
    rows = db.execute("""select id, source, model, title, parent_session_id, started_at, ended_at, end_reason,
                                message_count, tool_call_count, coalesce(actual_cost_usd, estimated_cost_usd) cost,
                                coalesce(last_activity_at, ended_at, started_at) act
                         from sessions where coalesce(last_activity_at, ended_at, started_at) > ? order by act""",
                      (since,)).fetchall()
    batch, top = [], since
    for r in rows:
        account = _acct(r["source"] or "unknown")
        batch.append({"event_type": "conversation.started", "source": "hermes", "source_account": account,
                      "source_id": _sid(f"session:{r['id']}:start"), "occurred_at": ts(r["started_at"]), "thread_id": r["id"],
                      "content": r["title"], "actor": {**WALTER, "account": account},
                      "payload": {"platform": account, "model": r["model"], "title": r["title"],
                                  "parent_session_id": r["parent_session_id"]}})
        if r["ended_at"]:
            batch.append({"event_type": "conversation.ended", "source": "hermes", "source_account": account,
                          "source_id": _sid(f"session:{r['id']}:end"), "occurred_at": ts(r["ended_at"]), "thread_id": r["id"],
                          "actor": {**WALTER, "account": account},
                          "payload": {"end_reason": r["end_reason"], "message_count": r["message_count"],
                                      "tool_call_count": r["tool_call_count"],
                                      "cost_usd": float(r["cost"]) if r["cost"] is not None else None}})
        top = max(top, float(r["act"] or 0))
    batch = [_finish(e) for e in batch]
    for i in range(0, len(batch), BATCH):
        events.record_events(batch[i:i + BATCH], conn=conn)
    ingestion.set_checkpoint(CONNECTOR, "sessions", {"activity": top}, conn=conn)
    return len(batch)


def sync_messages(db, conn, max_rows: int) -> tuple[int, int]:
    cur = ingestion.get_checkpoint(CONNECTOR, "messages")
    last_id = int(cur.get("last_id", 0))
    sessions = {r["id"]: r["source"] for r in db.execute("select id, source from sessions")}
    rows = db.execute("""select id, session_id, role, content, timestamp, display_kind, _compressed_summary, finish_reason
                         from messages where id > ? order by id limit ?""", (last_id, max_rows)).fetchall()
    batch, seen, last_user = [], 0, {}
    for m in rows:
        seen += 1
        sid, platform = m["session_id"], sessions.get(m["session_id"]) or "unknown"
        interactive = platform in INTERACTIVE
        base = {"source": "hermes", "source_account": _acct(platform), "thread_id": sid, "occurred_at": ts(m["timestamp"])}
        if not interactive or m["role"] not in ("user", "assistant"):
            continue
        text = m["content"] or ""
        if (m["display_kind"] or m["_compressed_summary"] in ("1", 1) or text.startswith("[CONTEXT COMPACTION]")
                or not text.strip()):
            continue  # system-injected rows or tool-call-only assistant turns
        refs, att = attachments(text, sid, conn) if m["role"] == "user" else ([], [])
        is_user = m["role"] == "user"
        batch.append({**base, "event_type": "message.sent" if is_user else "message.received",
                      "source_id": _sid(f"msg:{m['id']}"), "content": text, "object_refs": refs,
                      "reply_to": None if is_user else last_user.get(sid),
                      "actor": {**(MONSIEUR if is_user else WALTER), "account": platform},
                      "payload": {"chat": {"id": sid, "type": "agent", "network": platform}, "session_id": sid,
                                  "message_id": m["id"], "role": m["role"], "attachments": att,
                                  "finish_reason": m["finish_reason"]}})
        if is_user:
            last_user[sid] = _sid(f"msg:{m['id']}")
    batch = [_finish(e) for e in batch]
    inserted = 0
    for i in range(0, len(batch), BATCH):
        inserted += events.record_events(batch[i:i + BATCH], conn=conn)["inserted"]
    if rows:
        ingestion.set_checkpoint(CONNECTOR, "messages", {"last_id": rows[-1]["id"]}, last_item_at=ts(rows[-1]["timestamp"]),
                                 conn=conn)
    return seen, inserted


def export_days(db) -> dict:
    """Compatibility entrypoint; the shared exporter owns profile/privacy/checkpoints."""
    from walter_memory.hermes_export import VaultExports, export_profile
    profile = PROFILE or "main"
    with VaultExports(profile, not PROFILE) as store:
        return export_profile(db, profile, store, temp_root="/var/tmp", default_profile=not PROFILE)


def run_one(state_db: str, max_rows: int, export: bool) -> dict:
    db = sqlite3.connect(state_db, uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        with connection() as conn:
            s = sync_sessions(db, conn)
        total_seen = total_ins = 0
        while True:
            with connection() as conn:
                seen, ins = sync_messages(db, conn, min(max_rows - total_seen, 20000))
            total_seen += seen; total_ins += ins
            if seen == 0 or total_seen >= max_rows:
                break
        exported = export_days(db) if export else []
        return {"session_events": s, "rows_seen": total_seen, "events_inserted": total_ins,
                "exported_days": exported["exported_days"] if export else 0}
    finally:
        db.close()


def main() -> None:
    global CONNECTOR, PROFILE
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=50000, help="max state.db message rows per run")
    ap.add_argument("--export", action="store_true", help="also write the daily raw export to the Raw Vault")
    ap.add_argument("--export-only", action="store_true", help="export without canonical ingestion")
    ap.add_argument("--export-days", type=int, default=31, help="maximum nonempty past days per profile/run")
    ap.add_argument("--export-seconds", type=int, default=900, help="time budget per profile")
    ap.add_argument("--all-profiles", action="store_true", help="also every ~/.hermes/profiles/<name>/state.db")
    a = ap.parse_args()
    targets = [("", STATE_DB)]
    if a.all_profiles:
        import os
        for name in sorted(os.listdir(PROFILES_DIR)):
            path = f"{PROFILES_DIR}/{name}/state.db"
            if os.path.exists(path):
                targets.append((name, f"file:{path}?mode=ro"))
    report = {}
    failed = False
    if a.export_only:
        ingestion.register_connector("hermes_raw_export", "hermes", "pull",
                                     "Encrypted raw daily archives of all Hermes profiles", timedelta(hours=26))
    for name, state_db in targets:
        label = "main" if not name else "profile:" + name
        PROFILE, CONNECTOR = name, f"hermes:{name}" if name else "hermes"
        ingestion.register_connector(CONNECTOR, "hermes", "pull",
                                     f"W.Alter conversations from Hermes {'profile ' + name if name else 'main'} "
                                     "state.db (read-only)", timedelta(minutes=10))
        try:
            if a.export_only:
                from walter_memory.hermes_export import run
                result = run(state_db, name or "main", default_profile=not name, max_days=a.export_days, max_seconds=a.export_seconds)
                report[label] = result
                failed = failed or bool(result["remaining_days"])
            else:
                report[name or "main"] = run_one(state_db, a.max, a.export)
                ingestion.mark_success(CONNECTOR)
        except Exception as e:
            if a.export_only:
                # Raw rows can contain secrets: exception values never go to logs/model output.
                failed = True
                ingestion.record_failure("hermes_raw_export", type(e).__name__)
                report[label] = {"error": type(e).__name__}
            else:
                ingestion.record_failure(CONNECTOR, f"{type(e).__name__}: {e}")
                if not name:
                    raise
                report[name] = {"error": f"{type(e).__name__}: {e}"[:200]}
    if a.export_only:
        if not failed:
            ingestion.mark_success("hermes_raw_export")
        else:
            ingestion.record_failure("hermes_raw_export", "raw export incomplete; retry resumes checkpoints")
    print(json.dumps(report))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
