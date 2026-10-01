#!/usr/bin/env python3
"""Gmail connector (P2.5, D2: read-only). E-mails → core.events (email.received / email.sent), attachments → Raw Vault
(encrypted zone). Backfill pages through messages.list (newest first, resumable); then incremental via history.list.
Spam and trash are skipped. Bodies are stored as plain text (HTML stripped), capped at 50 000 chars.
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
        promo = any(l in (m.get("labelIds") or []) for l in ("CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS"))
        jobs += [] if promo else [(m, a) for a in atts if (a.get("size") or 0) <= MAX_ATTACH]
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


def main() -> None:
    ingestion.register_connector(CONNECTOR, "gmail", "pull", "Gmail lucas.jouvencon@gmail.com (read-only)", timedelta(minutes=15))
    try:
        g = Google()
        prof = g.get(f"{API}/profile")
        me = prof["emailAddress"]
        cp = ingestion.get_checkpoint(CONNECTOR, me)
        total = 0
        if not cp.get("backfill_done"):
            if "history_id" not in cp:
                cp["history_id"] = prof["historyId"]       # incremental starts from the moment backfill began
            page = cp.get("page_token")
            for _ in range(int(sys.argv[1]) if len(sys.argv) > 1 else 10):   # pages of 100 per run
                lst = g.get(f"{API}/messages", maxResults=100, pageToken=page, includeSpamTrash="false")
                msgs = [g.get(f"{API}/messages/{x['id']}", format="full") for x in lst.get("messages", [])]
                total += store(g, me, msgs)
                page = lst.get("nextPageToken")
                ingestion.set_checkpoint(CONNECTOR, me, {**cp, "page_token": page, "backfill_done": not page})
                if not page:
                    cp["backfill_done"] = True
                    break
        if cp.get("backfill_done") or ingestion.get_checkpoint(CONNECTOR, me).get("backfill_done"):
            cp = ingestion.get_checkpoint(CONNECTOR, me)
            try:
                hist, token = [], None
                while True:
                    h = g.get(f"{API}/history", startHistoryId=cp["history_id"], historyTypes="messageAdded", pageToken=token)
                    hist += [x["message"]["id"] for rec in h.get("history", []) for x in rec.get("messagesAdded", [])]
                    token = h.get("nextPageToken")
                    if not token:
                        break
                msgs = []
                for mid in dict.fromkeys(hist):
                    try:
                        m = g.get(f"{API}/messages/{mid}", format="full")
                        if not {"SPAM", "TRASH"} & set(m.get("labelIds") or []):
                            msgs.append(m)
                    except Exception:
                        pass
                total += store(g, me, msgs)
                ingestion.set_checkpoint(CONNECTOR, me, {**cp, "history_id": h.get("historyId", cp["history_id"])})
            except SyncTokenExpired:
                ingestion.set_checkpoint(CONNECTOR, me, {"backfill_done": False})   # full re-scan, idempotent
        ingestion.mark_success(CONNECTOR)
        print(json.dumps({"account": me, "events_inserted": total}))
    except Exception as e:
        ingestion.record_failure(CONNECTOR, f"{type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
