"""Beeper connector (2026-11-02): an interrupted burst is re-read, never skipped; the daily reconciliation repairs
messages a run missed. Fake Beeper API, test database."""
import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from walter_memory.db import connection

spec = importlib.util.spec_from_file_location("beeper_conn", Path(__file__).resolve().parent.parent / "connectors/beeper.py")
beeper = importlib.util.module_from_spec(spec); spec.loader.exec_module(beeper)
NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True, scope="module")
def connector():
    from walter_memory import ingestion
    ingestion.register_connector("beeper", "beeper", "pull", "pytest", timedelta(minutes=10))


class Fake:
    """Messages newest first, pages of 3; `fail_after` page requests → ConnectTimeout (Mac asleep)."""
    def __init__(self, chat_id, n):
        self.chat_id = chat_id
        self.msgs = [{"id": f"m{i}", "sortKey": str(i), "timestamp": (NOW - timedelta(minutes=100 - i)).isoformat(),
                      "senderID": "u1", "senderName": "Alix", "text": f"message {i}", "isSender": False} for i in range(1, n + 1)]
        self.fail_after, self.calls = None, 0

    def messages(self, chat_id, cursor=None, direction=None):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise httpx.ConnectTimeout("timed out")
        ordered = sorted(self.msgs, key=lambda m: -int(m["sortKey"]))
        start = int(cursor) if cursor else 0
        items = ordered[start:start + 3]
        return {"items": items, "hasMore": start + 3 < len(ordered), "oldestCursor": str(start + 3)}


def stored(chat_id):
    with connection() as conn:
        return {r["source_id"].split("|")[1] for r in conn.execute(
            "select source_id from core.events where source = 'beeper' and thread_id = %s and event_type like 'message.%%'",
            (chat_id,))}


def test_an_interrupted_burst_is_reread_not_skipped():
    chat = {"id": f"!{uuid.uuid4().hex[:8]}:pytest", "accountID": "whatsapp", "type": "single", "participants": {"items": []}}
    api = Fake(chat["id"], 4)
    beeper.sync_chat(api, chat, backfill_pages=10)                      # first run: everything known
    assert stored(chat["id"]) == {f"m{i}" for i in range(1, 5)}
    api.msgs += [{**api.msgs[0], "id": f"m{i}", "sortKey": str(i), "text": f"burst {i}",
                  "timestamp": (NOW - timedelta(minutes=50 - i)).isoformat()} for i in range(5, 15)]   # 10 new messages
    api.calls, api.fail_after = 0, 2                                     # the Mac drops after 2 pages
    with pytest.raises(httpx.ConnectTimeout):
        beeper.sync_chat(api, chat, backfill_pages=0)
    api.fail_after = None
    beeper.sync_chat(api, chat, backfill_pages=0)                        # next run
    assert stored(chat["id"]) == {f"m{i}" for i in range(1, 15)}         # the old code lost m5..m8


def test_reconciliation_repairs_a_missed_message_and_records_the_run():
    chat = {"id": f"!{uuid.uuid4().hex[:8]}:pytest", "accountID": "whatsapp", "type": "single", "participants": {"items": []}}
    api = Fake(chat["id"], 6)
    beeper.sync_chat(api, chat, backfill_pages=10)
    api.msgs.append({**api.msgs[0], "id": "m-late", "sortKey": "3", "text": "arrived out of order",
                     "timestamp": (NOW - timedelta(minutes=97)).isoformat()})      # old sortKey: invisible to sync
    beeper.sync_chat(api, chat, backfill_pages=0)
    assert "m-late" not in stored(chat["id"])
    r = beeper.reconcile(api, [chat], days=1)
    assert r["events_repaired"] == 1 and "m-late" in stored(chat["id"])
    with connection() as conn:
        run = conn.execute("""select gaps, repaired from ingestion.reconciliation_runs where connector = 'beeper'
                              order by run_id desc limit 1""").fetchone()
    assert run["gaps"] == 1 and run["repaired"] == 1
