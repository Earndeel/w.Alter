#!/usr/bin/env python3
"""Beeper connector (P2.1): every chat of native Beeper Server (WhatsApp, Instagram, Messenger, Telegram, LINE…)
→ core.events, read-only. Replaces the Mac → webhook path (which lost 85 % of the text, then jammed on HTTP 413).

API: native Server through core's public BeeperClient; token from Walter Secrets' named grant. Only GET endpoints are
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
import html
import json
import os
import sys
import tempfile
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_memory import events, ingestion, objects  # noqa: E402
from walter_memory.db import connection  # noqa: E402
from walter_beeper import BeeperClient  # noqa: E402

CONNECTOR = "beeper"
MEDIA_QUEUE = "beeper_media"
MAX_MEDIA_BYTES = int(os.environ.get("BEEPER_MAX_MEDIA_MB", "200")) * 1024 * 1024


class Beeper(BeeperClient):
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
    selves = owner_ids(chat, msgs)
    for m in msgs:
        sid = m.get("_canonical_source_id") or f"{chat['id']}|{m['id']}"
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
        # the native Server returns text HTML-escaped (« & » → « &amp; »): history keeps what was written
        text = html.unescape(m["text"]) if m.get("text") else None
        if not text and atts and atts[0].get("transcription"):
            text = atts[0]["transcription"]           # voice note: Beeper's own transcription is the content
        base = {"source": "beeper", "source_account": account, "thread_id": chat["id"], "occurred_at": m["timestamp"]}
        out.append({**base, "event_type": "message.sent" if is_self else "message.received", "source_id": sid,
                    "content": text, "actor": actor,
                    "reply_to": m.get('_canonical_reply_to') if m.get('_canonical_source_id') else
                        (f"{chat['id']}|{m['linkedMessageID']}" if m.get("linkedMessageID") else None),
                    "payload": {"chat": chat_info, "native_message_id": m['id'], "sender_name": m.get("senderName"), "message_type": m.get("type"),
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
            out.append({**base, "event_type": "reaction.added", "source_id": r.get('_canonical_source_id') or f"{sid}|react|{r.get('id') or who + r.get('reactionKey', '')}",
                        "content": r.get("reactionKey"),
                        "actor": identity(people.get(who), who, None, account, who in selves),
                        "payload": {"target_source_id": sid, "emoji": r.get("reactionKey")}})
    return out, media


def attach_known_objects(conn, evs: list[dict]) -> int:
    """Best-effort object_refs (A5): files of these messages already in the Raw Vault (stored by an earlier run, e.g.
    for an edit of an older message) are referenced on the new events. A brand-new message's media are fetched after
    its event is written (append-only: never updated), so its files are found at read time through core.object_links
    (beeper_message → source_id), like the whole history. Never fails the sync."""
    keys = {e.get("payload", {}).get("target_source_id") or e["source_id"] for e in evs}
    try:
        with conn.transaction():         # a savepoint: a failed lookup never aborts the events' transaction
            rows = conn.execute("""select target_id, array_agg(object_id::text order by object_id) ids
                                   from core.object_links where target_type = 'beeper_message' and target_id = any(%s)
                                   group by 1""", (list(keys),)).fetchall()
    except Exception:  # noqa: BLE001
        return 0
    found = {r["target_id"]: r["ids"] for r in rows}
    n = 0
    for e in evs:
        ids = found.get(e.get("payload", {}).get("target_source_id") or e["source_id"])
        if ids and e["event_type"] in ("message.sent", "message.received", "message.edited"):
            e["object_refs"] = ids
            n += 1
    return n


class SyncBusy(RuntimeError):
    pass


def owner_ids(chat: dict, msgs: list[dict]) -> set[str]:
    """IDs under which the account owner appears in this chat: participants flagged isSelf + senders of own messages."""
    ids={p['id'] for p in ((chat.get('participants') or {}).get('items') or []) if p.get('isSelf') and p.get('id')}
    return ids|{m['senderID'] for m in msgs if m.get('isSender') and m.get('senderID')}


def canonical_messages(chat: dict, msgs: list[dict], scope: str, *, conn) -> list[dict]:
    """API message IDs are LOCAL. Resolve by chat + server sortKey, validated against time/sender/side.

    Reuse checkpoint metadata for the small identity projection, no second event store or schema. Existing
    canonical source IDs win (including the old Mac's IDs); new ones use the unique server order key.
    Projection + canonical event + media + page cursor commit in the same transaction.
    """
    if not scope or not msgs:
        return msgs
    def stamp(m):return datetime.fromisoformat(m['timestamp'].replace('Z','+00:00'))
    for m in msgs:
        if not str(m.get('sortKey') or '').isdigit() or int(m['sortKey']) <= 0:
            raise ValueError('No positive server message order key; retain job for retry')
    streams = ['@identity:'+chat['id']+'|'+str(m['sortKey']) for m in msgs]
    known = {r['stream']:r['cursor'] for r in conn.execute(
        "select stream,cursor from ingestion.checkpoints where connector=%s and stream=any(%s)",
        (CONNECTOR,streams)).fetchall()}
    old = conn.execute("""select e.source_id,e.event_type,e.occurred_at,e.payload->>'sort_key' sk,
              i.external_id sender,i.is_self from core.events e left join core.source_identities i
              on i.identity_id=e.actor_identity_id where e.source='beeper' and e.thread_id=%s
              and e.event_type in ('message.sent','message.received') and e.payload->>'sort_key'=any(%s)
              order by e.ingested_at,e.event_id""",(chat['id'],[str(m['sortKey']) for m in msgs])).fetchall()
    out=[]
    for m,stream in zip(msgs,streams):
        kind='message.sent' if m.get('isSender') else 'message.received'
        candidates=[r for r in old if r['sk']==str(m['sortKey'])]
        # A sent-message WS snapshot can identify the owner by their bridge ID, while HTTP uses
        # their Matrix ID. Both explicitly identify the owner; incoming senders must still match.
        consistent=[r for r in candidates if r['occurred_at']==stamp(m) and r['event_type']==kind
                    and (not r['sender'] or r['sender']==m.get('senderID')
                         or (kind=='message.sent' and r['is_self']))]
        if candidates and not consistent:
            raise ValueError('Message order identity conflict; no merge performed')
        previous=known.get(stream)
        if previous and (previous['timestamp']!=m['timestamp'] or previous['sender']!=m.get('senderID') or previous['kind']!=kind):
            # Compare instants as well (one API can format UTC with a different suffix).
            if (datetime.fromisoformat(previous['timestamp'].replace('Z','+00:00'))!=stamp(m)
                or previous['kind']!=kind
                or (previous['sender']!=m.get('senderID') and kind!='message.sent')):
                raise ValueError('Message identity projection conflict')
        sid=(previous or {}).get('source_id') or (consistent[0]['source_id'] if consistent else chat['id']+'|sort:'+str(m['sortKey']))
        projection={'source_id':sid,'sort_key':str(m['sortKey']),'timestamp':m['timestamp'],
                    'sender':m.get('senderID'),'kind':kind}
        ingestion.set_checkpoint(CONNECTOR,stream,projection,conn=conn)
        ingestion.set_checkpoint(CONNECTOR,'@local:'+scope+':'+chat['id']+'|'+m['id'],projection,conn=conn)
        out.append({**m,'_canonical_source_id':sid})
    by_local={m['id']:m['_canonical_source_id'] for m in out}
    for m in out:
        linked=m.get('linkedMessageID')
        if linked:
            sid=by_local.get(linked)
            if not sid and m.get('_reply_message'):
                sid=canonical_messages(chat,[m['_reply_message']],scope,conn=conn)[0]['_canonical_source_id']
            if not sid:
                sid=ingestion.get_checkpoint(CONNECTOR,'@local:'+scope+':'+chat['id']+'|'+linked).get('source_id')
            m['_canonical_reply_to']=sid
    # Reactions also have installation-local IDs. Preserve legacy keys by canonical target, sender and emoji.
    # The owner reacts under several IDs (Matrix ID over HTTP, bridge ID in a WS snapshot): any owner ID is one sender.
    selves=owner_ids(chat,out)
    for m in out:
        existing=conn.execute("""select e.source_id,e.content,i.external_id sender,i.is_self from core.events e
            left join core.source_identities i on i.identity_id=e.actor_identity_id where e.source='beeper'
            and e.event_type='reaction.added' and e.thread_id=%s and e.payload->>'target_source_id'=%s
            order by e.ingested_at""",(chat['id'],m['_canonical_source_id'])).fetchall() if m.get('reactions') else []
        for r in m.get('reactions') or []:
            who=r.get('participantID') or 'unknown';emoji=r.get('reactionKey','')
            mine=who in selves
            match=next((x for x in existing if x['content']==emoji and (x['sender']==who or (mine and x['is_self']))),None)
            r['_canonical_source_id']=match['source_id'] if match else m['_canonical_source_id']+'|react:'+who+':'+emoji
    return out


def prepare_replies(bp, chat: dict, msgs: list[dict]) -> list[dict]:
    local={m['id'] for m in msgs}
    out=[]
    for message in msgs:
        m=dict(message)
        linked=m.get('linkedMessageID')
        if linked and linked not in local and hasattr(bp,'message'):
            m['_reply_message']=bp.message(chat['id'],linked)
        out.append(m)
    return out


def store_messages(chat: dict, msgs: list[dict], *, conn, scope: str = "") -> tuple[int, int]:
    msgs=canonical_messages(chat,msgs,scope,conn=conn)
    people = {p["id"]: p for p in ((chat.get("participants") or {}).get("items") or [])}
    evs, media = to_events(chat, msgs, people)
    inserted = queued = 0
    if evs:
        attach_known_objects(conn, evs)
        inserted = events.record_events(evs, conn=conn)["inserted"]
    for job in media:
        if ingestion.enqueue(MEDIA_QUEUE, job, dedupe_key=f"beeper_media:{job['source_id']}:{job['url']}",
                             priority=200, conn=conn):
            queued += 1
    return inserted, queued


def sync_chat(bp: Beeper, chat: dict, backfill_pages: int) -> tuple[int, int]:
    # Poll/reconciliation and the event worker may see the same chat together. Serialize its cursors only.
    with connection() as lock:
        key = "beeper.sync:" + chat["id"]
        if not lock.execute("select pg_try_advisory_lock(hashtextextended(%s, 0)) ok", (key,)).fetchone()["ok"]:
            raise SyncBusy("Beeper chat is being synchronized")
        try:
            return _sync_chat(bp, chat, backfill_pages)
        finally:
            lock.execute("select pg_advisory_unlock(hashtextextended(%s, 0))", (key,))


def _sync_chat(bp: Beeper, chat: dict, backfill_pages: int) -> tuple[int, int]:
    raw = ingestion.get_checkpoint(CONNECTOR, chat["id"])
    scope = getattr(bp, "checkpoint_scope", "")
    # Opaque API cursors belong to a client profile. Keep ALL old Mac checkpoint fields; canonical IDs stay beeper.
    cp = dict((raw.get("endpoints") or {}).get(scope) or {}) if scope else dict(raw)
    if scope and cp.get('mode')!='incremental_cutover':
        # Switch the source, not Memory's history. Server order keys are shared; opaque page cursors are not.
        cp={'mode':'incremental_cutover','newest_sort_key':int(raw.get('newest_sort_key') or 0),
            'backfill_done':True,'previous_profile_cursor':cp}
    people = {p["id"]: p for p in ((chat.get("participants") or {}).get("items") or [])}
    newest_known = int(cp.get("newest_sort_key") or 0)
    inserted = media_n = 0

    def write(msgs, cursor_update):
        nonlocal inserted, media_n
        msgs=prepare_replies(bp,chat,msgs)
        with connection() as conn:
            n, q = store_messages(chat, msgs, conn=conn, scope=scope)
            inserted += n; media_n += q
            next_cp = {**cp, **cursor_update}
            cursor = {**raw, "endpoints": {**raw.get("endpoints", {}), scope: next_cp}} if scope else next_cp
            ingestion.set_checkpoint(CONNECTOR, chat["id"], cursor,
                                     last_item_at=max((m["timestamp"] for m in msgs), default=None), conn=conn)
        cp.update(cursor_update)

    # 1) newest pages until the known sortKey. newest_sort_key moves only once known history is reached: a run that
    #    stops in the middle of a burst (Mac asleep, timeout) re-reads it next time instead of skipping the pages it
    #    did not get to (inserts are idempotent). Fixed 2026-11-02.
    page = bp.messages(chat["id"])
    first_oldest = page.get("oldestCursor")
    newest = max((int(m.get("sortKey") or 0) for m in page["items"]), default=newest_known)
    while page["items"]:
        fresh = [m for m in page["items"] if int(m.get("sortKey") or 0) > newest_known]
        cutoff=getattr(bp,'cutover_at',None)
        if cutoff and not newest_known:
            fresh=[m for m in fresh if datetime.fromisoformat(m['timestamp'].replace('Z','+00:00'))>=
                   datetime.fromisoformat(cutoff.replace('Z','+00:00'))]
        reached = len(fresh) < len(page["items"]) or not page.get("hasMore") or (newest_known == 0 and not cutoff)
        upd = {"newest_sort_key": max(newest, newest_known)} if reached else {}
        if "backfill_cursor" not in cp:
            upd["backfill_cursor"] = page.get("oldestCursor")
        write(fresh, upd)
        if reached:
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


def reconcile_chat(bp: Beeper, chat: dict, since: datetime) -> tuple[int, int]:
    """Re-read a chat back to `since` and write everything (idempotent): repairs messages a run missed and catches
    edits, deletions and reactions on recent messages, which the incremental pass (new sortKeys only) never sees.
    Returns (messages seen, events inserted)."""
    # Routine outage recovery starts at the source switch, never at the start of Memory's history.
    cutoff = getattr(bp, 'cutover_at', None)
    if cutoff:
        since = max(since, datetime.fromisoformat(cutoff.replace('Z', '+00:00')))
    people = {p["id"]: p for p in ((chat.get("participants") or {}).get("items") or [])}
    seen = inserted = 0
    page = bp.messages(chat["id"])
    while page["items"]:
        msgs = [m for m in page["items"] if datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")) >= since]
        seen += len(msgs)
        msgs=prepare_replies(bp,chat,msgs)
        with connection() as conn:
            n, _ = store_messages(chat, msgs, conn=conn, scope=getattr(bp,'checkpoint_scope',''))
            inserted += n
        if len(msgs) < len(page["items"]) or not page.get("hasMore"):
            break
        page = bp.messages(chat["id"], cursor=page["oldestCursor"], direction="before")
    return seen, inserted


def reconcile(bp: Beeper, chats: list[dict], days: int) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with connection() as conn:
        run_id = conn.execute("""insert into ingestion.reconciliation_runs (connector, stream) values (%s, %s)
                                 returning run_id""", (CONNECTOR, f"last {days} days")).fetchone()["run_id"]
    seen = inserted = errors = 0
    repaired_chats = []
    for chat in chats:
        try:
            s, i = reconcile_chat(bp, chat, since)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            errors += 1
            if errors >= 3:
                break                      # the Mac went away: the next daily run starts again
            continue
        seen += s; inserted += i
        if i:
            repaired_chats.append({"chat": chat["id"], "inserted": i})
    with connection() as conn:
        conn.execute("""update ingestion.reconciliation_runs set finished_at = now(), source_count = %s, walter_count = %s,
                          gaps = %s, repaired = %s, details = %s where run_id = %s""",
                     (seen, seen, inserted, inserted, json.dumps({"since": since.isoformat(), "chats": len(chats),
                                                                   "connection_errors": errors,
                                                                   "repaired_chats": repaired_chats[:50]}), run_id))
    return {"messages_seen": seen, "events_repaired": inserted, "connection_errors": errors}


def _reconcile_due(hours: int = 24) -> bool:
    with connection() as conn:
        r = conn.execute("""select max(finished_at) at from ingestion.reconciliation_runs where connector = %s
                            and (details->>'connection_errors')::int < 3""", (CONNECTOR,)).fetchone()
    return r["at"] is None or r["at"] < datetime.now(timezone.utc) - timedelta(hours=hours)


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
    ap.add_argument("--reconcile-days", type=int, default=7,
                    help="once a day, re-read the last N days of every chat (missed messages, edits, reactions)")
    a = ap.parse_args()
    ingestion.register_connector(CONNECTOR, "beeper", "push", "Native Beeper Server: events + polling reconciliation (read-only)",
                                 timedelta(minutes=10))
    try:
        bp = Beeper()
        chats = bp.chats()
        if a.chats:
            chats = chats[:a.chats]
        total_ins = total_media = 0
        unreachable = 0
        for n, chat in enumerate(chats, 1):
            try:
                ins, med = sync_chat(bp, chat, a.backfill_pages)
                total_ins += ins; total_media += med
                ingestion.resolve_failures(CONNECTOR, chat["id"])     # this chat is in sync again
                unreachable = 0
            except SyncBusy:
                continue  # event worker holds this chat; its durable job or next reconciliation continues it
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                unreachable += 1
                if unreachable >= 3:          # the Mac is gone: one failure for the run, not one per chat
                    ingestion.record_failure(CONNECTOR, f"source unreachable: {type(e).__name__}: {e}",
                                             details={"stopped_at_chat": n, "chats": len(chats)})
                    break
            except Exception as e:
                ingestion.record_failure(CONNECTOR, f"{type(e).__name__}: {e}", stream=chat["id"])
            if n % 25 == 0:
                ingestion.mark_success(CONNECTOR)   # long backfill runs still report liveness
        if unreachable >= 3:
            print(json.dumps({"chats": len(chats), "events_inserted": total_ins, "stopped": "source unreachable"}))
            return
        reconciled = reconcile(bp, chats, a.reconcile_days) if a.reconcile_days and _reconcile_due() else None
        media_done = run_media(bp, a.media) if a.media else 0
        ingestion.mark_success(CONNECTOR)
        ingestion.resolve_failures(CONNECTOR, "")
        with connection() as conn:
            pending = conn.execute("""select count(*) filter (where not coalesce(
                  (cursor->'endpoints'->%s->>'backfill_done')::boolean, false)) n
                  from ingestion.checkpoints where connector = %s and stream like '!%%'""",
                  (bp.checkpoint_scope, CONNECTOR)).fetchone()["n"]
        print(json.dumps({"chats": len(chats), "events_inserted": total_ins, "media_queued": total_media,
                          "media_stored": media_done, "chats_backfilling": pending, "reconciled": reconciled}))
    except Exception as e:
        ingestion.record_failure(CONNECTOR, f"{type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
