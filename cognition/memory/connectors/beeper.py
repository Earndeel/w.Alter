#!/usr/bin/env python3
"""Beeper connector (P2.1): every chat of Beeper Desktop (WhatsApp, Instagram, Messenger, Telegram, LINE, Signal…)
→ core.events, read-only. Replaces the Mac → webhook path (which lost 85 % of the text, then jammed on HTTP 413).

API: Beeper Client API on Monsieur's Mac (Tailscale), token from `vault get beeper/token`. Only GET endpoints are
used, plus /v1/assets/download + /v1/assets/serve to fetch media bytes. Never sends, edits or marks anything.

Per chat (stream = chatID) the checkpoint keeps the newest sortKey seen and the backfill cursor:
  - incremental: newest pages until the known sortKey;
  - backfill: older pages (direction=before) until the beginning of the chat, a few pages per run.
Messages → message.sent (isSender) / message.received; reactions → reaction.added; deletion flag → message.deleted;
edits seen on refetch → message.edited. Groups are stored raw like everything else (D4).
Media are queued (ingestion.jobs 'beeper_media') and stored in the Raw Vault's encrypted zone (third-party media).

Usage: beeper.py [--backfill-pages N] [--media N] [--chats N]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_memory import events, ingestion, objects  # noqa: E402
from walter_memory.db import connection  # noqa: E402

API = os.environ.get("BEEPER_API", "http://100.127.150.1:23373")
CONNECTOR = "beeper"
MEDIA_QUEUE = "beeper_media"
MAX_MEDIA_BYTES = int(os.environ.get("BEEPER_MAX_MEDIA_MB", "200")) * 1024 * 1024


class Beeper:
    def __init__(self):
        token = subprocess.run(["vault", "get", "beeper/token"], capture_output=True, text=True, check=True).stdout.strip()
        self.http = httpx.Client(base_url=API, headers={"Authorization": f"Bearer {token}"}, timeout=60)

    def get(self, path: str, **params) -> dict:
        for attempt in range(4):
            try:
                r = self.http.get(path, params={k: v for k, v in params.items() if v is not None})
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError(str(r.status_code), request=r.request, response=r)
                r.raise_for_status()
                return r.json()
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))

    def chats(self) -> list[dict]:
        out, cursor = [], None
        while True:
            d = self.get("/v1/chats", limit=200, cursor=cursor, direction="before" if cursor else None)
            out += d["items"]
            if not d.get("hasMore") or not d.get("oldestCursor"):
                return out
            cursor = d["oldestCursor"]

    def messages(self, chat_id: str, cursor: str | None = None, direction: str | None = None) -> dict:
        return self.get(f"/v1/chats/{urllib.parse.quote(chat_id, safe='')}/messages", cursor=cursor, direction=direction)

    def fetch_asset(self, url: str, dest: Path) -> Path:
        src = url
        if not url.startswith("file://"):          # mxc:// / localmxc:// must first be cached by Beeper Desktop
            r = self.http.post("/v1/assets/download", json={"url": url})
            r.raise_for_status()
            src = r.json().get("srcURL")
            if not src:
                raise RuntimeError(f"asset not downloadable: {r.json().get('error')}")
        with self.http.stream("GET", "/v1/assets/serve", params={"url": src}) as s:
            s.raise_for_status()
            with dest.open("wb") as f:
                for chunk in s.iter_bytes(1 << 20):
                    f.write(chunk)
        return dest


def identity(user: dict | None, sender_id: str, sender_name: str | None, account: str, is_self: bool) -> dict:
    u = user or {}
    return {"account": account, "external_id": sender_id, "display_name": u.get("fullName") or sender_name,
            "phones": [u["phoneNumber"]] if u.get("phoneNumber") else [],
            "emails": [u["email"]] if u.get("email") else [],
            "handles": {account: u["username"]} if u.get("username") else {}, "is_self": is_self or bool(u.get("isSelf"))}


def to_events(chat: dict, msgs: list[dict], people: dict) -> tuple[list[dict], list[dict]]:
    """Map Beeper messages to events; returns (events, media jobs)."""
    out, media = [], []
    account = chat.get("accountID") or ""
    chat_info = {"id": chat["id"], "title": chat.get("title"), "type": chat.get("type"), "network": chat.get("network")}
    for m in msgs:
        sid = f"{chat['id']}|{m['id']}"
        is_self = bool(m.get("isSender"))
        actor = identity(people.get(m.get("senderID")), m.get("senderID") or "unknown", m.get("senderName"), account, is_self)
        atts = []
        for a in m.get("attachments") or []:
            item = {k: a.get(k) for k in ("id", "type", "mimeType", "fileName", "fileSize", "isGif", "isSticker",
                                          "isVoiceNote", "duration", "srcURL")}
            if a.get("transcription"):
                item["transcription"] = a["transcription"].get("transcription")
            atts.append(item)
            if a.get("srcURL") and not a.get("isSticker") and (a.get("fileSize") or 0) <= MAX_MEDIA_BYTES:
                media.append({"chat_id": chat["id"], "message_id": m["id"], "source_id": sid, "url": a["srcURL"],
                              "name": a.get("fileName"), "mime": a.get("mimeType"), "ts": m.get("timestamp"),
                              "account": account})
        text = m.get("text") or None
        if not text and atts and atts[0].get("transcription"):
            text = atts[0]["transcription"]           # voice note: Beeper's own transcription is the content
        base = {"source": "beeper", "source_account": account, "thread_id": chat["id"], "occurred_at": m["timestamp"]}
        out.append({**base, "event_type": "message.sent" if is_self else "message.received", "source_id": sid,
                    "content": text, "actor": actor,
                    "reply_to": f"{chat['id']}|{m['linkedMessageID']}" if m.get("linkedMessageID") else None,
                    "payload": {"chat": chat_info, "sender_name": m.get("senderName"), "message_type": m.get("type"),
                                "attachments": atts, "mentions": m.get("mentions") or [], "links": m.get("links") or [],
                                "edited_at": m.get("editedTimestamp"), "is_deleted": bool(m.get("isDeleted")),
                                "sort_key": m.get("sortKey")}})
        if m.get("editedTimestamp"):
            out.append({**base, "event_type": "message.edited", "source_id": f"{sid}|edit|{m['editedTimestamp']}",
                        "occurred_at": m["editedTimestamp"], "content": text, "actor": actor,
                        "payload": {"target_source_id": sid}})
        if m.get("isDeleted"):
            out.append({**base, "event_type": "message.deleted", "source_id": f"{sid}|deleted", "actor": actor,
                        "payload": {"target_source_id": sid}})
        for r in m.get("reactions") or []:
            who = r.get("participantID") or "unknown"
            out.append({**base, "event_type": "reaction.added", "source_id": f"{sid}|react|{r.get('id') or who + r.get('reactionKey', '')}",
                        "content": r.get("reactionKey"),
                        "actor": identity(people.get(who), who, None, account, who == m.get("senderID") and is_self),
                        "payload": {"target_source_id": sid, "emoji": r.get("reactionKey")}})
    return out, media


def sync_chat(bp: Beeper, chat: dict, backfill_pages: int) -> tuple[int, int]:
    cp = ingestion.get_checkpoint(CONNECTOR, chat["id"])
    people = {p["id"]: p for p in ((chat.get("participants") or {}).get("items") or [])}
    newest_known = int(cp.get("newest_sort_key") or 0)
    inserted = media_n = 0

    def write(msgs, cursor_update):
        nonlocal inserted, media_n
        evs, media = to_events(chat, msgs, people)
        with connection() as conn:
            if evs:
                inserted += events.record_events(evs, conn=conn)["inserted"]
            ingestion.set_checkpoint(CONNECTOR, chat["id"], {**cp, **cursor_update},
                                     last_item_at=max((m["timestamp"] for m in msgs), default=None), conn=conn)
        cp.update(cursor_update)
        for job in media:
            if ingestion.enqueue(MEDIA_QUEUE, job, dedupe_key=f"beeper_media:{job['source_id']}:{job['url']}", priority=200):
                media_n += 1

    # 1) newest pages until the known sortKey
    page = bp.messages(chat["id"])
    first_oldest = page.get("oldestCursor")
    newest = max((int(m.get("sortKey") or 0) for m in page["items"]), default=newest_known)
    while page["items"]:
        fresh = [m for m in page["items"] if int(m.get("sortKey") or 0) > newest_known]
        upd = {"newest_sort_key": max(newest, newest_known)}
        if "backfill_cursor" not in cp:
            upd["backfill_cursor"] = page.get("oldestCursor")
        write(fresh, upd)
        if len(fresh) < len(page["items"]) or not page.get("hasMore") or newest_known == 0:
            break                          # reached known history (or first run: backfill continues below)
        page = bp.messages(chat["id"], cursor=page["oldestCursor"], direction="before")
    if newest_known == 0 and "backfill_cursor" not in cp:
        cp["backfill_cursor"] = first_oldest
    # 2) backfill older pages
    for _ in range(backfill_pages):
        if cp.get("backfill_done") or not cp.get("backfill_cursor"):
            break
        page = bp.messages(chat["id"], cursor=cp["backfill_cursor"], direction="before")
        done = not page.get("hasMore") or not page["items"]
        write(page["items"], {"backfill_cursor": page.get("oldestCursor") or cp["backfill_cursor"], "backfill_done": done})
    return inserted, media_n


def run_media(bp: Beeper, limit: int) -> int:
    def handle(job: dict) -> None:
        with tempfile.TemporaryDirectory(dir="/var/tmp") as d:
            name = objects.safe_name(job.get("name") or job["url"].rsplit("/", 1)[-1] or "media")
            path = bp.fetch_asset(job["url"], Path(d) / name)
            when = datetime.fromisoformat(job["ts"].replace("Z", "+00:00")) if job.get("ts") else None
            with connection() as conn:
                objects.put_object(path, "beeper", captured_at=when, original_name=name, zone="secure",
                                         source_ref={"chat_id": job["chat_id"], "message_id": job["message_id"],
                                                     "account": job.get("account")},
                                         links=[("beeper_message", job["source_id"])], conn=conn)
    done = 0
    while done < limit:
        n = ingestion.work(MEDIA_QUEUE, handle, batch=min(10, limit - done))
        if not n:
            break
        done += n
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill-pages", type=int, default=20, help="older pages per chat per run (20 msgs/page)")
    ap.add_argument("--media", type=int, default=50, help="media downloads per run")
    ap.add_argument("--chats", type=int, default=0, help="limit number of chats (testing)")
    a = ap.parse_args()
    ingestion.register_connector(CONNECTOR, "beeper", "pull", "Beeper Desktop API on Monsieur's Mac (read-only)",
                                 timedelta(minutes=10))
    try:
        bp = Beeper()
        chats = bp.chats()
        if a.chats:
            chats = chats[:a.chats]
        total_ins = total_media = 0
        for n, chat in enumerate(chats, 1):
            try:
                ins, med = sync_chat(bp, chat, a.backfill_pages)
                total_ins += ins; total_media += med
            except Exception as e:
                ingestion.record_failure(CONNECTOR, f"{type(e).__name__}: {e}", stream=chat["id"])
            if n % 25 == 0:
                ingestion.mark_success(CONNECTOR)   # long backfill runs still report liveness
        media_done = run_media(bp, a.media) if a.media else 0
        ingestion.mark_success(CONNECTOR)
        with connection() as conn:
            pending = conn.execute("""select count(*) filter (where not coalesce((cursor->>'backfill_done')::boolean, false)) n
                                      from ingestion.checkpoints where connector = %s""", (CONNECTOR,)).fetchone()["n"]
        print(json.dumps({"chats": len(chats), "events_inserted": total_ins, "media_queued": total_media,
                          "media_stored": media_done, "chats_backfilling": pending}))
    except Exception as e:
        ingestion.record_failure(CONNECTOR, f"{type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
