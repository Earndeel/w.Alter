#!/usr/bin/env python3
"""Gmail connector (P2.5, D2: read-only). Human correspondence only (quality gate in gmail_filter.py, decision
2026-10-02): Gmail stays the archive for everything else and is searched live. Kept e-mails → core.events
(email.received / email.sent), their attachments → Raw Vault (encrypted zone).

Backfill, resumable, in two lanes: (1) every thread where Monsieur wrote (`in:sent`, whole thread), which also builds
the correspondents set; (2) the rest of the mailbox, read as metadata only and fetched in full only when the gate keeps
it. Then incremental via history.list. Bodies are plain text (HTML stripped), capped at 50 000 chars.
"""
from __future__ import annotations

import base64
import html
import json
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses, parseaddr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from google_api import Google, SyncTokenExpired  # noqa: E402
from gmail_filter import ME, keep  # noqa: E402
from walter_memory import events, ingestion, objects  # noqa: E402
from walter_memory.db import connection  # noqa: E402

API = "https://gmail.googleapis.com/gmail/v1/users/me"
CONNECTOR = "gmail"
MAX_ATTACH = 25 * 1024 * 1024
TAG = re.compile(r"<[^>]+>")


def _b64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def body_text(part: dict) -> str:
    """Prefer text/plain; fall back to stripped text/html."""
    plain, rich = [], []
    def walk(p):
        mt, data = p.get("mimeType", ""), (p.get("body") or {}).get("data")
        if data and mt == "text/plain":
            plain.append(_b64(data).decode("utf-8", "replace"))
        elif data and mt == "text/html":
            rich.append(html.unescape(TAG.sub(" ", re.sub(r"(?is)<(script|style).*?</\1>", " ", _b64(data).decode("utf-8", "replace")))))
        for c in p.get("parts") or []:
            walk(c)
    walk(part)
    text = "\n".join(plain) or re.sub(r"[ \t]+", " ", "\n".join(rich))
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:50000]


def attachments_of(part: dict) -> list[dict]:
    out = []
    def walk(p):
        if p.get("filename") and (p.get("body") or {}).get("attachmentId"):
            out.append({"name": p["filename"], "mime": p.get("mimeType"), "size": p["body"].get("size"),
                        "attachment_id": p["body"]["attachmentId"]})
        for c in p.get("parts") or []:
            walk(c)
    walk(part)
    return out


def to_event(m: dict, me: str) -> tuple[dict, list[dict]]:
    h = {x["name"].lower(): x["value"] for x in m["payload"].get("headers", [])}
    labels = m.get("labelIds") or []
    sent = "SENT" in labels
    name, addr = parseaddr(h.get("from", ""))
    atts = attachments_of(m["payload"])
    ev = {"event_type": "email.sent" if sent else "email.received", "source": "gmail", "source_account": me,
          "source_id": m["id"], "occurred_at": datetime.fromtimestamp(int(m["internalDate"]) / 1000, tz=timezone.utc),
          "thread_id": m["threadId"], "content": (h.get("subject", "") + "\n\n" + body_text(m["payload"])).strip(),
          "actor": {"account": me, "external_id": addr.lower() or "unknown", "display_name": name or addr,
                    "emails": [addr.lower()] if addr else [], "is_self": sent},
          "payload": {"from": h.get("from"), "to": [a for _, a in getaddresses([h.get("to", "")]) if a],
                      "cc": [a for _, a in getaddresses([h.get("cc", "")]) if a], "subject": h.get("subject"),
                      "labels": labels, "gmail_thread_id": m["threadId"], "message_id_header": h.get("message-id"),
                      "attachments": [{k: a[k] for k in ("name", "mime", "size")} for a in atts]}}
    return ev, atts


def store(g: Google, me: str, msgs: list[dict]) -> int:
    evs, jobs = [], []
    for m in msgs:
        ev, atts = to_event(m, me)
        evs.append(ev)
        jobs += [(m, a) for a in atts if (a.get("size") or 0) <= MAX_ATTACH]
    with connection() as conn:
        n = events.record_events(evs, conn=conn)["inserted"] if evs else 0
    for m, a in jobs:
        try:
            data = g.get(f"{API}/messages/{m['id']}/attachments/{a['attachment_id']}")
            with tempfile.TemporaryDirectory(dir="/var/tmp") as d:
                p = Path(d) / objects.safe_name(a["name"])
                p.write_bytes(_b64(data["data"]))
                objects.put_object(p, "gmail", original_name=a["name"], zone="secure",
                                   captured_at=datetime.fromtimestamp(int(m["internalDate"]) / 1000, tz=timezone.utc),
                                   links=[("email", f"gmail:{m['id']}")], source_ref={"gmail_id": m["id"]})
        except Exception as e:
            ingestion.record_failure(CONNECTOR, f"attachment: {type(e).__name__}: {e}", item_ref=m["id"])
    return n


def _headers(m: dict) -> dict:
    return {x["name"].lower(): x["value"] for x in (m.get("payload") or {}).get("headers", [])}


class Gate:
    """Decides per message from metadata; knows the threads where Monsieur wrote and the people he wrote to."""

    def __init__(self):
        with connection() as conn:
            rows = conn.execute("""select thread_id, payload->'to' t, payload->'cc' c from core.events
                                   where source = 'gmail' and payload->'labels' ? 'SENT'""").fetchall()
            self.stored_threads = {r["thread_id"] for r in conn.execute(
                "select distinct thread_id from core.events where source = 'gmail'").fetchall()}
        self.human_threads = {r["thread_id"] for r in rows}
        self.correspondents = {a.lower() for r in rows for a in (r["t"] or []) + (r["c"] or [])} - {ME}

    def learn(self, m: dict) -> None:
        if "SENT" in (m.get("labelIds") or []):
            h = _headers(m)
            self.human_threads.add(m["threadId"])
            self.correspondents |= {a.lower() for _, a in getaddresses([h.get("to", ""), h.get("cc", "")]) if a} - {ME}

    def ok(self, m: dict) -> bool:
        labels = m.get("labelIds") or []
        if {"SPAM", "TRASH", "CHAT"} & set(labels):
            return False
        h = _headers(m)
        return keep(labels=labels, from_header=h.get("from"), subject=h.get("subject"), snippet=m.get("snippet"),
                    human_thread=m["threadId"] in self.human_threads, correspondents=self.correspondents)


def store_threads(g: Google, me: str, gate: Gate, thread_ids) -> int:
    """Whole threads where Monsieur wrote (each message still passes the OTP part of the gate)."""
    n = 0
    for tid in dict.fromkeys(thread_ids):
        msgs = g.get(f"{API}/threads/{tid}", format="full").get("messages", [])
        for m in msgs:
            gate.learn(m)
        n += store(g, me, [m for m in msgs if gate.ok(m)])
        gate.stored_threads.add(tid)
    return n


def store_if_kept(g: Google, me: str, gate: Gate, ids, failed: list | None = None) -> int:
    """Metadata first; full fetch only for kept messages. A new message from Monsieur pulls its whole thread.
    A message that cannot be read goes to `failed` (retried next run) instead of being silently skipped."""
    keep_full, new_threads = [], []
    for mid in dict.fromkeys(ids):
        try:
            m = g.get(f"{API}/messages/{mid}", format="metadata", metadataHeaders=["From", "To", "Cc", "Subject"])
        except Exception as e:
            if "404" in str(e):          # deleted before we read it: nothing to keep
                continue
            if failed is not None:
                failed.append(mid)
            ingestion.record_failure(CONNECTOR, f"metadata: {type(e).__name__}: {e}", item_ref=mid)
            continue
        if "SENT" in (m.get("labelIds") or []) and m["threadId"] not in gate.stored_threads:
            gate.learn(m); new_threads.append(m["threadId"]); continue
        gate.learn(m)
        if gate.ok(m):
            keep_full.append(mid)
    n = store_threads(g, me, gate, new_threads)
    full = [g.get(f"{API}/messages/{mid}", format="full") for mid in keep_full]
    return n + (store(g, me, full) if full else 0)


def reconcile(g: Google, me: str, gate: Gate, days: int) -> dict:
    """Compare Gmail with core.events over the last `days`: every message the gate keeps must be stored; missing ones
    are stored now. Recorded in ingestion.reconciliation_runs (listed / kept by the gate / already stored / repaired)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with connection() as conn:
        run_id = conn.execute("""insert into ingestion.reconciliation_runs (connector, stream) values (%s, %s)
                                 returning run_id""", (CONNECTOR, f"last {days} days")).fetchone()["run_id"]
    ids, token = [], None
    while True:
        lst = g.get(f"{API}/messages", maxResults=500, pageToken=token, q=f"after:{since:%Y/%m/%d} -in:chats",
                    includeSpamTrash="false")
        ids += [x["id"] for x in lst.get("messages", [])]
        token = lst.get("nextPageToken")
        if not token:
            break
    with connection() as conn:
        have = {r["source_id"] for r in conn.execute(
            "select source_id from core.events where source = 'gmail' and source_id = any(%s)", (ids,))}
    kept, missing, failed = 0, [], []
    for mid in ids:
        try:
            m = g.get(f"{API}/messages/{mid}", format="metadata", metadataHeaders=["From", "To", "Cc", "Subject"])
        except Exception:
            failed.append(mid); continue
        gate.learn(m)
        if gate.ok(m):
            kept += 1
            if mid not in have:
                missing.append(mid)
    repaired = store(g, me, [g.get(f"{API}/messages/{mid}", format="full") for mid in missing]) if missing else 0
    with connection() as conn:
        conn.execute("""update ingestion.reconciliation_runs set finished_at = now(), source_count = %s, walter_count = %s,
                          gaps = %s, repaired = %s, details = %s where run_id = %s""",
                     (len(ids), len(have), len(missing), repaired,
                      json.dumps({"since": since.isoformat(), "kept_by_gate": kept, "dropped_by_gate": len(ids) - kept - len(failed),
                                  "unreadable": len(failed)}), run_id))
    return {"listed": len(ids), "kept_by_gate": kept, "stored_before": len(have), "repaired": repaired,
            "unreadable": len(failed)}


def _reconcile_due(hours: int = 24) -> bool:
    with connection() as conn:
        r = conn.execute("select max(finished_at) at from ingestion.reconciliation_runs where connector = %s",
                         (CONNECTOR,)).fetchone()
    return r["at"] is None or r["at"] < datetime.now(timezone.utc) - timedelta(hours=hours)


def main() -> None:
    ingestion.register_connector(CONNECTOR, "gmail", "pull", "Gmail lucas.jouvencon@gmail.com (read-only, human only)",
                                 timedelta(minutes=15))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pages = int(args[0]) if args else 5
    rec_days = next((int(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--reconcile-days=")), 3)
    force_reconcile = "--reconcile-now" in sys.argv
    try:
        g = Google()
        prof = g.get(f"{API}/profile")
        me = prof["emailAddress"]
        key = f"v2:{me}"
        cp = ingestion.get_checkpoint(CONNECTOR, key)
        cp.setdefault("history_id", prof["historyId"])     # incremental starts from the moment backfill began
        gate, total = Gate(), 0
        for lane, q in (("sent", "in:sent"), ("rest", "-in:sent -in:chats")):
            if cp.get(f"{lane}_done"):
                continue
            for _ in range(pages):
                lst = g.get(f"{API}/messages", maxResults=100, pageToken=cp.get(f"{lane}_page"), q=q,
                            includeSpamTrash="false")
                ids = [x["id"] for x in lst.get("messages", [])]
                if lane == "sent":
                    total += store_threads(g, me, gate, [x["threadId"] for x in lst.get("messages", [])
                                                         if x["threadId"] not in gate.stored_threads])
                else:
                    total += store_if_kept(g, me, gate, ids)
                cp[f"{lane}_page"] = lst.get("nextPageToken")
                cp[f"{lane}_done"] = not cp[f"{lane}_page"]
                ingestion.set_checkpoint(CONNECTOR, key, cp)
                ingestion.mark_success(CONNECTOR)
                if cp[f"{lane}_done"]:
                    break
            break                                           # one lane per run: lane 2 needs lane 1's correspondents
        if cp.get("sent_done") and cp.get("rest_done"):
            try:
                hist, token, h = [], None, {}
                while True:
                    h = g.get(f"{API}/history", startHistoryId=cp["history_id"], historyTypes="messageAdded", pageToken=token)
                    hist += [x["message"]["id"] for rec in h.get("history", []) for x in rec.get("messagesAdded", [])]
                    token = h.get("nextPageToken")
                    if not token:
                        break
                failed: list = []
                total += store_if_kept(g, me, gate, list(cp.get("retry_ids") or []) + hist, failed)
                cp["history_id"] = h.get("historyId", cp["history_id"])
                cp["retry_ids"] = failed[-500:]           # unreadable now: read again next run, never skipped
                ingestion.set_checkpoint(CONNECTOR, key, cp)
            except SyncTokenExpired:
                ingestion.set_checkpoint(CONNECTOR, key, {})   # full re-scan, idempotent
        reconciled = None
        if cp.get("sent_done") and cp.get("rest_done") and rec_days and (force_reconcile or _reconcile_due()):
            reconciled = reconcile(g, me, gate, rec_days)
        ingestion.mark_success(CONNECTOR)
        print(json.dumps({"account": me, "events_inserted": total, "reconciled": reconciled,
                          "lanes": {k: cp.get(k) for k in ("sent_done", "rest_done")}}))
    except Exception as e:
        ingestion.record_failure(CONNECTOR, f"{type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
