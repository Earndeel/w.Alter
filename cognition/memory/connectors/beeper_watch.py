"""Native Beeper notifications -> existing Memory jobs -> canonical events/media/bus.

Upstream WS is at-most-once, without replay; seq belongs to one connection. Every reconnect
therefore schedules an HTTP catch-up. The existing polling/reconciliation service stays as
the repair path. No message sends, new database, webhook server or alternate memory.
"""
from __future__ import annotations

import hashlib
import json
import signal
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import beeper
from walter_beeper import BeeperAPIError, settings
from walter_memory import events, ingestion
from walter_memory.db import connection

QUEUE = "beeper_events"
KINDS = {"chat.upserted", "chat.deleted", "message.upserted", "message.deleted"}


IDENTIFIERS = {"id", "chatID", "accountID", "senderID", "participantID", "linkedMessageID", "sortKey", "ids",
               "messageID", "userID", "type"}


def scrub(value, key: str | None = None):
    if key in IDENTIFIERS:
        return value
    if isinstance(value, dict):
        return {k: scrub(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return events.vault_scrub(value) if isinstance(value, str) else value


def enqueue_notice(frame: dict, scope: str) -> int | None:
    if frame.get("type") not in KINDS or not str(frame.get("chatID", "")).startswith("!"):
        return None
    # Retain the hydrated snapshot (edits/deletes may race a later HTTP read). Existing secret masker applies to the
    # content, never to identifiers: a sender ID that is also a vault value (the owner's own login) stays an ID.
    clean = scrub(frame)
    fingerprint = hashlib.sha256(json.dumps({k: v for k, v in clean.items() if k != "seq"},
                                           sort_keys=True).encode()).hexdigest()
    return ingestion.enqueue(QUEUE, {"scope": scope, "notification": clean},
        dedupe_key=f"beeper.ws:{scope}:{fingerprint}", priority=20 if frame["type"].startswith("message.") else 80,
        max_attempts=12)


def schedule_catchup(scope: str, reason: str) -> int | None:
    return ingestion.enqueue(QUEUE, {"scope": scope, "rescan": uuid.uuid4().hex, "reason": reason}, priority=50,
                             max_attempts=12)


def apply_job(api: beeper.Beeper, payload: dict) -> dict:
    if payload.get("scope") != api.checkpoint_scope:
        raise ValueError("Job belongs to another Beeper profile")
    if payload.get("rescan"):
        chats = api.chats()
        for chat in chats:
            ingestion.enqueue(QUEUE, {"scope": api.checkpoint_scope, "catchup_chat": chat,
                                     "reconcile": True},
                dedupe_key=f"beeper.catchup:{payload['rescan']}:{chat['id']}", priority=100, max_attempts=12)
        return {"chats_scheduled": len(chats)}
    if payload.get("catchup_chat"):
        chat = payload["catchup_chat"]
        inserted, _ = beeper.sync_chat(api, chat, backfill_pages=0)
        # Drift includes out-of-order deliveries and recent edits/reactions, not just increasing sort keys.
        if payload.get("reconcile") and settings()['reconcile_days']:
            since = datetime.now(timezone.utc) - timedelta(days=settings()["reconcile_days"])
            _, n = beeper.reconcile_chat(api, chat, since)
            inserted += n
        return {"events_inserted": inserted}
    frame = payload["notification"]
    kind, chat_id = frame["type"], frame["chatID"]
    if kind == "chat.deleted":
        # Do not infer deletion of its messages or purge canonical history from a removed chat.
        return {"chat_removal_observed": True}
    try:
        chat = api.chat(chat_id)
    except BeeperAPIError as exc:
        if exc.status != 404 or kind != "message.deleted":
            raise
        chat = {"id": chat_id, "accountID": ""}
    if beeper.excluded(chat):
        return {"skipped": beeper.excluded(chat)}
    if kind == "message.deleted":
        stamp = frame.get("ts") or datetime.now(timezone.utc).isoformat()
        deleted=[]
        for mid in frame.get('ids',[]):
            cp=ingestion.get_checkpoint(beeper.CONNECTOR,'@local:'+api.checkpoint_scope+':'+chat_id+'|'+mid)
            sid=cp.get('source_id')
            if not sid:
                m=api.message(chat_id,mid)
                with connection() as conn:
                    sid=beeper.canonical_messages(chat,[m],api.checkpoint_scope,conn=conn)[0]['_canonical_source_id']
            deleted.append({"source":"beeper","event_type":"message.deleted","thread_id":chat_id,
                "source_account":chat.get('accountID',''),"source_id":sid+'|deleted',
                "occurred_at":stamp,"payload":{"target_source_id":sid}})
        return events.record_events(deleted)
    messages = [m for m in frame.get("entries", []) if isinstance(m, dict) and m.get("id") and m.get("timestamp")]
    if kind == "message.upserted" and not messages:
        messages = [api.message(chat_id, mid) for mid in frame.get("ids", [])]
    if messages:
        messages=beeper.prepare_replies(api,chat,messages)
        with connection() as conn:
            n, q = beeper.store_messages(chat, messages, conn=conn, scope=api.checkpoint_scope)
        return {"events_inserted": n, "media_queued": q}
    n, q = beeper.sync_chat(api, chat, backfill_pages=0)
    return {"events_inserted": n, "media_queued": q}


def worker(stop: threading.Event):
    api = beeper.Beeper()
    try:
        while not stop.is_set():
            jobs = ingestion.claim(QUEUE, 1)
            if not jobs:
                stop.wait(.5)
                continue
            job = jobs[0]
            try:
                result = apply_job(api, job["payload"])
                ingestion.complete(job["job_id"])
                ingestion.mark_success(beeper.CONNECTOR)
                print(json.dumps({"processed": 1, **result}), flush=True)
            except Exception as exc:
                ingestion.fail(job, type(exc).__name__)  # never log frame contents or secret-bearing errors
    finally:
        api.close()


def run(stop: threading.Event):
    ingestion.register_connector(beeper.CONNECTOR, "beeper", "push",
        "Native Beeper Server: WS events + durable jobs + HTTP reconciliation", timedelta(minutes=10))
    # This queue has one systemd-supervised worker. After its whole cgroup exits, its running jobs are orphaned.
    ingestion.requeue_stale(minutes=0, queue=QUEUE)
    thread = threading.Thread(target=worker, args=(stop,), name="beeper-events-worker", daemon=True)
    thread.start()
    api = beeper.Beeper()
    delay = 1
    try:
        while not stop.is_set():
            try:
                with api.websocket() as ws:
                    ws.send(json.dumps({"type": "subscriptions.set", "chatIDs": ["*"]}))
                    schedule_catchup(api.checkpoint_scope, "connected")
                    cp = ingestion.get_checkpoint(beeper.CONNECTOR, "@websocket")
                    cp.update(connected=True, connected_at=datetime.now(timezone.utc).isoformat(),
                              connections=int(cp.get("connections", 0)) + 1, last_seq=0)
                    ingestion.set_checkpoint(beeper.CONNECTOR, "@websocket", cp)
                    print(json.dumps({"websocket": "connected"}), flush=True)
                    delay = 1
                    last_seq = 0
                    while not stop.is_set():
                        if not thread.is_alive():
                            raise RuntimeError("Beeper queue worker stopped")
                        try:
                            frame = json.loads(ws.recv(timeout=2))
                        except TimeoutError:
                            continue
                        if frame.get("type") == "error":
                            raise RuntimeError("Beeper WS subscription error")
                        seq = frame.get("seq")
                        if isinstance(seq, int):
                            if last_seq and seq != last_seq + 1:
                                schedule_catchup(api.checkpoint_scope, "sequence_gap")
                            last_seq = seq
                        if frame.get("type") in KINDS:
                            enqueue_notice(frame, api.checkpoint_scope)
                            cp.update(last_seq=last_seq, last_event_at=datetime.now(timezone.utc).isoformat(),
                                      notifications=int(cp.get("notifications", 0)) + 1)
                            ingestion.set_checkpoint(beeper.CONNECTOR, "@websocket", cp)
            except Exception as exc:
                cp = ingestion.get_checkpoint(beeper.CONNECTOR, "@websocket")
                cp.update(connected=False, disconnected_at=datetime.now(timezone.utc).isoformat(),
                          last_error=type(exc).__name__)
                ingestion.set_checkpoint(beeper.CONNECTOR, "@websocket", cp)
                print(json.dumps({"websocket": "reconnecting", "error": type(exc).__name__}), flush=True)
                if not thread.is_alive():
                    raise RuntimeError("Beeper queue worker stopped") from None
                stop.wait(delay)
                delay = min(delay * 2, 60)
    finally:
        stop.set()
        api.close()
        thread.join(timeout=30)


if __name__ == "__main__":
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    run(stopping)
