#!/usr/bin/env python3
"""Google Calendar connector (P2.5, D2: read-only). Every version of every event → calendar.event
(source_id = calendar|event|updated, so changes are new observations; history stays append-only).
Incremental with syncToken per calendar; a 410 (expired token) triggers an idempotent full re-scan.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from google_api import Google, SyncTokenExpired  # noqa: E402
from walter_memory import events, ingestion  # noqa: E402

API = "https://www.googleapis.com/calendar/v3"
CONNECTOR = "calendar"


def when(t: dict | None) -> str | None:
    return (t or {}).get("dateTime") or ((t or {}).get("date") and t["date"] + "T00:00:00+00:00")


def to_event(cal: dict, e: dict) -> dict:
    start = when(e.get("start")) or e.get("updated")
    organizer = e.get("organizer") or {}
    return {"event_type": "calendar.event", "source": "calendar", "source_account": cal["id"],
            "source_id": f"{cal['id']}|{e['id']}|{e.get('updated')}", "occurred_at": start,
            "thread_id": e.get("recurringEventId") or e["id"],
            "content": "\n".join(x for x in (e.get("summary"), e.get("location"), e.get("description")) if x) or None,
            "actor": {"account": cal["id"], "external_id": (organizer.get("email") or cal["id"]).lower(),
                      "display_name": organizer.get("displayName") or organizer.get("email"),
                      "emails": [organizer["email"].lower()] if organizer.get("email") else [],
                      "is_self": bool(organizer.get("self"))},
            "payload": {"start": e.get("start"), "end": e.get("end"), "location": e.get("location"),
                        "status": e.get("status"), "calendar_id": cal["id"], "event_id": e["id"],
                        "updated": e.get("updated"), "html_link": e.get("htmlLink"),
                        "attendees": [{k: a.get(k) for k in ("email", "displayName", "responseStatus", "self")}
                                      for a in e.get("attendees") or []]}}


def main() -> None:
    ingestion.register_connector(CONNECTOR, "calendar", "pull", "Google Calendar lucas.jouvencon@gmail.com (read-only)",
                                 timedelta(minutes=30))
    try:
        g = Google()
        total = 0
        for cal in g.get(f"{API}/users/me/calendarList").get("items", []):
          try:
            cid = urllib.parse.quote(cal["id"], safe="")
            cp = ingestion.get_checkpoint(CONNECTOR, cal["id"])
            page, sync = None, cp.get("sync_token")
            while True:
                try:
                    params = {"syncToken": sync} if sync else {"singleEvents": "false", "showDeleted": "true",
                                                               "maxResults": 2500}
                    d = g.get(f"{API}/calendars/{cid}/events", pageToken=page, **params)
                except SyncTokenExpired:
                    sync, page = None, None
                    continue
                evs = [to_event(cal, e) for e in d.get("items", []) if e.get("updated")]
                if evs:
                    total += events.record_events(evs)["inserted"]
                page = d.get("nextPageToken")
                if not page:
                    ingestion.set_checkpoint(CONNECTOR, cal["id"], {"sync_token": d.get("nextSyncToken")})
                    break
          except Exception as e:
            ingestion.record_failure(CONNECTOR, f"{type(e).__name__}: {e}"[:500], stream=cal["id"])
        ingestion.mark_success(CONNECTOR)
        print(json.dumps({"events_inserted": total}))
    except Exception as e:
        ingestion.record_failure(CONNECTOR, f"{type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
