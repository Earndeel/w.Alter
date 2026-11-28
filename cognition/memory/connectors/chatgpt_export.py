#!/usr/bin/env python3
"""ChatGPT export connector: Monsieur's ChatGPT data export → core.events (source `chatgpt`).

One-shot and idempotent, like legacy_import: run it on an extracted export folder (conversations-NNN.json, or the
older single conversations.json). Each conversation gives conversation.started, then along the branch Monsieur
last saw (current_node back to the root): message.sent for his messages (typed text, voice transcriptions,
attachment names) and message.received for ChatGPT's visible answers — never its hidden reasoning (`thoughts`,
`reasoning_recap`), tool calls/results, system or hidden context messages (custom instructions, memory).
Conversations flagged do-not-remember are skipped.

Attachments stay metadata (name, MIME type, export file id, present in this export or not): the bytes belong to the
Raw Vault, imported separately. Rerunning on a newer export only adds what is new (source_id = message id).

Usage: chatgpt_export.py DIR [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CONNECTOR = "chatgpt_export"
SOURCE = "chatgpt"
ACCOUNT = "monsieur"
MONSIEUR = {"external_id": "monsieur", "display_name": "Monsieur", "is_self": True, "account": ACCOUNT}
CHATGPT = {"external_id": "chatgpt", "display_name": "ChatGPT", "account": ACCOUNT}
USER_TYPES = {"text", "multimodal_text"}
ASSISTANT_TYPES = {"text", "multimodal_text"}
BATCH = 2000


def _iso(ts) -> str | None:
    return datetime.fromtimestamp(float(ts), timezone.utc).isoformat() if ts else None


def load_conversations(folder: str) -> list[dict]:
    files = sorted(glob.glob(os.path.join(folder, "conversations-*.json"))) or \
        [f for f in [os.path.join(folder, "conversations.json")] if os.path.exists(f)]
    if not files:
        raise SystemExit(f"no conversations*.json in {folder}")
    out = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            out += json.load(fh)
    return out


def branch(conv: dict) -> list[dict]:
    """The messages of the branch Monsieur last saw, oldest first (regenerated / edited siblings are left out)."""
    mapping = conv.get("mapping") or {}
    node, seen, path = conv.get("current_node"), set(), []
    while node and node in mapping and node not in seen:
        seen.add(node)
        if mapping[node].get("message"):
            path.append(mapping[node]["message"])
        node = mapping[node].get("parent")
    return path[::-1]


def _parts(content: dict, files: dict[str, str]) -> tuple[str, list[dict]]:
    """Visible text of a message + its attachment pointers (images, audio)."""
    texts, atts = [], []
    for p in content.get("parts") or []:
        if isinstance(p, str):
            texts.append(p)
        elif isinstance(p, dict):
            ct = p.get("content_type")
            if ct == "audio_transcription" and p.get("text"):
                texts.append(p["text"])
            elif ct and ct.endswith("asset_pointer"):
                fid = (p.get("asset_pointer") or "").rsplit("/", 1)[-1] or None
                atts.append({"kind": ct.replace("_asset_pointer", ""), "file_id": fid,
                             "size": p.get("size_bytes"), "in_export": bool(fid and fid in files)})
    return "\n".join(t for t in texts if t).strip(), atts


def parse_conversation(conv: dict, files: dict[str, str] | None = None) -> list[dict]:
    """Pure: one exported conversation → core.events dicts."""
    files = files or {}
    if conv.get("is_do_not_remember"):
        return []
    cid = conv.get("conversation_id") or conv.get("id")
    title = conv.get("title")
    chat = {"id": cid, "type": "agent", "title": title, "network": "chatgpt"}
    base = {"source": SOURCE, "source_account": ACCOUNT, "thread_id": cid}
    msgs = branch(conv)
    started = _iso(conv.get("create_time")) or next((_iso(m.get("create_time")) for m in msgs if m.get("create_time")), None)
    if not cid or not started:
        return []
    out = [{**base, "event_type": "conversation.started", "source_id": f"conv:{cid}:start", "occurred_at": started,
            "content": title, "actor": CHATGPT,
            "payload": {"platform": "chatgpt", "model": conv.get("default_model_slug"), "title": title,
                        "parent_session_id": None}}]
    last_user, last_at = None, started
    for m in msgs:
        role = (m.get("author") or {}).get("role")
        content = m.get("content") or {}
        meta = m.get("metadata") or {}
        if role not in ("user", "assistant") or meta.get("is_visually_hidden_from_conversation"):
            continue
        if m.get("recipient") not in (None, "all"):          # assistant → tool call
            continue
        ctype = content.get("content_type")
        if ctype not in (USER_TYPES if role == "user" else ASSISTANT_TYPES):
            continue
        text, atts = _parts(content, files)
        pointers = {x["file_id"]: x for x in atts if x.get("file_id")}
        for a in meta.get("attachments") or []:
            fid = a.get("id")
            if fid in pointers:                               # same file as an inline pointer: one entry
                pointers[fid].update(name=a.get("name"), mime_type=a.get("mime_type"))
                continue
            atts.append({"kind": (a.get("mime_type") or "file").split("/")[0], "file_id": fid, "name": a.get("name"),
                         "mime_type": a.get("mime_type"), "size": a.get("size"),
                         "in_export": bool(fid and any(k.startswith(fid) for k in files))})
        if not text and not atts:
            continue
        if not text:
            text = "[" + ", ".join(a.get("name") or a["kind"] for a in atts) + "]"
        at = _iso(m.get("create_time")) or last_at
        last_at = at
        mid = m.get("id")
        payload = {"chat": chat, "session_id": cid, "message_id": mid, "role": role, "attachments": atts}
        if role == "user":
            if meta.get("bidi_voice_mode_message") or any(a["kind"] == "audio" for a in atts):
                payload["message_type"] = "voice"
            out.append({**base, "event_type": "message.sent", "source_id": f"msg:{mid}", "occurred_at": at,
                        "content": text, "actor": MONSIEUR, "payload": payload})
            last_user = f"msg:{mid}"
        else:
            payload["model"] = meta.get("model_slug")
            out.append({**base, "event_type": "message.received", "source_id": f"msg:{mid}", "occurred_at": at,
                        "content": text, "reply_to": last_user, "actor": CHATGPT, "payload": payload})
    return out if len(out) > 1 else []


def export_files(folder: str) -> dict[str, str]:
    """file id → file name, for the asset files actually present in this export."""
    return {f.split(".")[0]: f for f in os.listdir(folder) if f.startswith("file") and not f.endswith(".json")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    convs = load_conversations(a.dir)[: a.limit or None]
    files = export_files(a.dir)
    evs, skipped = [], 0
    for c in convs:
        e = parse_conversation(c, files)
        skipped += not e
        evs += e
    kinds: dict[str, int] = {}
    for e in evs:
        kinds[e["event_type"]] = kinds.get(e["event_type"], 0) + 1
    atts = [x for e in evs for x in e["payload"].get("attachments") or []]
    summary = {"conversations": len(convs), "skipped": skipped, "events": kinds,
               "attachments": len(atts), "attachments_in_export": sum(x["in_export"] for x in atts),
               "from": min((e["occurred_at"] for e in evs), default=None),
               "to": max((e["occurred_at"] for e in evs), default=None)}
    if a.dry_run:
        from walter_memory import types
        for e in evs:
            types.validate(e["event_type"], e["payload"])
        print(json.dumps({**summary, "dry_run": True}, indent=1))
        return 0
    from walter_memory import events, ingestion
    from walter_memory.db import connection
    ingestion.register_connector(CONNECTOR, SOURCE, "manual",
                                 "ChatGPT data export (one-shot, idempotent): conversations → core.events")
    inserted = 0
    try:
        with connection() as conn:
            for i in range(0, len(evs), BATCH):
                inserted += events.record_events(evs[i:i + BATCH], conn=conn)["inserted"]
            ingestion.set_checkpoint(CONNECTOR, os.path.abspath(a.dir), {"summary": summary, "inserted": inserted},
                                     last_item_at=summary["to"], conn=conn)
    except Exception as e:
        ingestion.record_failure(CONNECTOR, f"{type(e).__name__}: {e}")
        raise
    ingestion.mark_success(CONNECTOR)
    print(json.dumps({**summary, "inserted": inserted}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
