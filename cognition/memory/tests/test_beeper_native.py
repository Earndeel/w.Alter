"""Native migration: stable IDs, preserved cursors, atomic media, queue crash recovery and missed WS repair.
The test harness refuses production 5433; only testdb 5440 and fake Beeper are used.
"""
import importlib.util
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from walter_beeper import BeeperAPIError
from walter_memory import ingestion
from walter_memory.db import connection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "connectors"))
import beeper
import beeper_watch as watch


@pytest.fixture(autouse=True)
def connector():
    ingestion.register_connector("beeper", "beeper", "push", "native pytest", timedelta(minutes=10))


def chat():
    return {"id": f"!{uuid.uuid4().hex}:pytest", "accountID": "fixture", "type": "single", "participants": {"items": []}}


def msg(i=1):
    return {"id": "m"+str(i), "sortKey": str(i), "timestamp": datetime.now(timezone.utc).isoformat(),
            "senderID": "fixture", "text": "fixture", "isSender": False}


class Fake:
    checkpoint_scope = "oracle-server"
    def __init__(self, c, messages): self.c, self.rows = c, messages
    def chats(self): return [self.c]
    def chat(self, _): return self.c
    def messages(self, _, **kwargs):
        return {"items": self.rows, "hasMore": False, "oldestCursor": None}


def count(c, kind="message.received"):
    with connection() as conn:
        return conn.execute("select count(*) n from core.events where source='beeper' and thread_id=%s and event_type=%s",
                            (c['id'], kind)).fetchone()["n"]


def test_new_profile_preserves_mac_cursor_and_canonical_ids():
    c = chat(); m = msg()
    old = {"newest_sort_key": 99999999, "backfill_cursor": "mac-only", "backfill_done": True}
    ingestion.set_checkpoint("beeper", c["id"], old)
    with connection() as conn:
        beeper.store_messages(c, [m], conn=conn)  # already imported through the Mac
    assert beeper.sync_chat(Fake(c, [{**m,'id':'different-server-local-id'}]), c, 0)[0] == 0
    cp = ingestion.get_checkpoint("beeper", c["id"])
    assert all(cp[k] == v for k, v in old.items())
    assert cp["endpoints"]["oracle-server"]["newest_sort_key"] == old['newest_sort_key']
    assert cp['endpoints']['oracle-server']['backfill_done'] is True
    assert count(c) == 1


def test_events_media_and_cursor_roll_back_together(monkeypatch):
    c = chat(); m = msg()
    m["attachments"] = [{"srcURL": "mxc://pytest/"+uuid.uuid4().hex,"fileName":"fixture.png"}]
    original = ingestion.set_checkpoint
    def crash(*args, **kwargs): raise RuntimeError("crash before commit")
    monkeypatch.setattr(ingestion, "set_checkpoint", crash)
    with pytest.raises(RuntimeError): beeper.sync_chat(Fake(c, [m]), c, 0)
    assert count(c) == 0
    with connection() as conn:
        assert conn.execute("select count(*) n from ingestion.jobs where payload->>'chat_id'=%s", (c["id"],)).fetchone()["n"] == 0
    monkeypatch.setattr(ingestion, "set_checkpoint", original)
    assert beeper.sync_chat(Fake(c, [m]), c, 0)[0] == 1
    with connection() as conn:
        assert conn.execute("select count(*) n from ingestion.jobs where payload->>'chat_id'=%s", (c["id"],)).fetchone()["n"] == 1


def test_duplicate_notification_and_redelivery_after_crash_are_idempotent():
    c = chat(); m = msg()
    frame = {"type":"message.upserted", "chatID":c["id"],"ids":[m["id"]],"entries":[m],"ts":m["timestamp"],"seq":1}
    first = watch.enqueue_notice(frame, "oracle-server")
    assert first and watch.enqueue_notice({**frame,"seq":42}, "oracle-server") is None
    with connection() as conn:
        payload = conn.execute("select payload from ingestion.jobs where job_id=%s", (first,)).fetchone()["payload"]
        conn.execute("update ingestion.jobs set status='running', locked_at=now() where job_id=%s", (first,))
    api = Fake(c, [m])
    assert watch.apply_job(api, payload)["events_inserted"] == 1
    # A crash after the canonical commit, before job completion: restart reclaims only this connector's queue.
    other = ingestion.enqueue("another_connector",{},dedupe_key=uuid.uuid4().hex)
    with connection() as conn:
        conn.execute("update ingestion.jobs set status='running', locked_at=now() where job_id=%s",(other,))
    ingestion.requeue_stale(minutes=0, queue=watch.QUEUE)
    assert watch.apply_job(api, payload)["events_inserted"] == 0
    with connection() as conn:
        assert conn.execute("select status from ingestion.jobs where job_id=%s",(other,)).fetchone()["status"] == 'running'
    assert count(c) == 1


def test_reconnect_catchup_repairs_notifications_missed_during_outage(monkeypatch):
    c = chat(); original=msg(10); api = Fake(c, [original])
    beeper.sync_chat(api, c, 0)
    api.rows = [msg(11), original, {**msg(5),"id":"late-old-sort"}]
    monkeypatch.setattr(watch, "settings", lambda: {"reconcile_days":7})
    payload = {"scope":"oracle-server", "catchup_chat":c,"reconcile":True}
    watch.apply_job(api, payload)
    assert count(c) == 3
    watch.apply_job(api, payload)
    assert count(c) == 3


def test_explicit_delete_survives_removed_upstream_chat():
    c = chat()
    with connection() as conn:
        beeper.store_messages(c,[msg(1)],conn=conn,scope='oracle-server')
    class Removed(Fake):
        def chat(self,_): raise BeeperAPIError(404)
    payload = {"scope":"oracle-server","notification":{"type":"message.deleted","chatID":c["id"],
        "ids":["m1"],"ts":datetime.now(timezone.utc).isoformat()}}
    watch.apply_job(Removed(c,[]),payload)
    watch.apply_job(Removed(c,[]),payload)
    assert count(c,"message.deleted") == 1


def test_chat_removal_does_not_delete_messages_or_history():
    c = chat(); api = Fake(c,[msg()])
    beeper.sync_chat(api,c,0)
    watch.apply_job(api,{"scope":"oracle-server","notification":{"type":"chat.deleted","chatID":c["id"],"ids":[c["id"]]}})
    assert count(c) == 1 and count(c,"message.deleted") == 0


def test_different_messages_cannot_merge_on_reused_order_key():
    c=chat();m=msg(1)
    with connection() as conn:
        beeper.store_messages(c,[m],conn=conn,scope='server-one')
    with connection() as conn, pytest.raises(ValueError,match='identity conflict'):
        beeper.store_messages(c,[{**m,'id':'other','senderID':'someone-else'}],conn=conn,scope='server-two')
    assert count(c)==1


def test_owner_bridge_and_matrix_ids_share_the_same_sent_message():
    c=chat();m={**msg(1),'isSender':True,'senderID':'bridge-owner'}
    with connection() as conn:
        beeper.store_messages(c,[m],conn=conn,scope='server-one')
    with connection() as conn:
        assert beeper.store_messages(c,[{**m,'id':'other-local-id','senderID':'@owner:matrix'}],
            conn=conn,scope='server-two')[0]==0
    assert count(c,'message.sent')==1


def test_cutover_skips_old_history_but_recovers_new_messages_on_multiple_pages():
    c=chat();now=datetime.now(timezone.utc)
    old={**msg(1),'timestamp':(now-timedelta(days=2)).isoformat()}
    fresh=[{**msg(i),'timestamp':now.isoformat()} for i in range(2,5)]
    class Paged(Fake):
        cutover_at=(now-timedelta(hours=1)).isoformat()
        def messages(self,_,cursor=None,**kwargs):
            index=int(cursor or 0)
            return {'items':[[fresh[2]],[fresh[1]],[fresh[0],old]][index],
                'hasMore':index<2,'oldestCursor':str(index+1) if index<2 else None}
    api=Paged(c,[])
    assert beeper.sync_chat(api,c,20)[0]==3
    assert count(c)==3
    # Even an explicitly broad recovery window never reimports history predating the source switch.
    beeper.reconcile_chat(api,c,now-timedelta(days=7))
    assert count(c)==3
