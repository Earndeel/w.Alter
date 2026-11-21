"""20/11/2026: a person's card names their conversations (network, thread id, dates, who wrote last) so an agent reads
them with memory_events directly; retracted duplicates are not counted. No model; rows removed afterwards."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import events, social
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)
ACCOUNT = "pytest-conv"


@pytest.fixture
def world():
    tag = uuid.uuid4().hex[:8]
    made = {"events": []}
    with connection() as conn:
        made["entity"] = conn.execute("""insert into core.entities (entity_type, canonical_name) values ('person', %s)
                                         returning entity_id::text""", (f"Pytest Conv {tag}",)).fetchone()["entity_id"]
        made["ids"] = []
        for ext in (f"@them-{tag}:wa", f"@them-{tag}:sig"):
            iid = conn.execute("""insert into core.source_identities (source, account, external_id, display_name)
                                  values ('beeper', %s, %s, 'Contact') returning identity_id::text""",
                               (ACCOUNT, ext)).fetchone()["identity_id"]
            conn.execute("""insert into core.identity_links (identity_id, entity_id, status, method)
                            values (%s, %s, 'confirmed', 'pytest')""", (iid, made["entity"]))
            made["ids"].append(iid)

    def msg(thread, network, n, *, them, days, ident=0, kind="single"):
        evs = [{"event_type": "message.received" if them else "message.sent", "source": "beeper",
                "source_account": ACCOUNT, "source_id": f"{tag}-{thread}-{i}-{them}", "thread_id": f"!{tag}-{thread}",
                "occurred_at": NOW - timedelta(days=days, minutes=i), "content": f"m{i}",
                "payload": {"chat": {"network": network, "type": kind, "title": "x"}},
                **({"actor_identity_id": made["ids"][ident]} if them else {})} for i in range(n)]
        ids = events.record_events(evs)["event_ids"]
        made["events"] += ids
        return ids
    made["msg"] = msg
    yield made
    with connection() as conn:
        conn.execute("set local walter.purge = 'on'")
        retr = [r["event_id"] for r in conn.execute(
            "select event_id::text from core.events where event_type = 'event.retracted' and payload->>'target_event_id' = any(%s)",
            (made["events"],))]
        ids = made["events"] + retr
        conn.execute("delete from core.event_keys where event_id = any(%s::uuid[])", (ids,))
        conn.execute("delete from core.events where event_id = any(%s::uuid[])", (ids,))
        conn.execute("delete from core.identity_links where entity_id = %s", (made["entity"],))
        conn.execute("delete from core.source_identities where identity_id = any(%s::uuid[])", (made["ids"],))
        conn.execute("delete from core.entities where entity_id = %s", (made["entity"],))


def test_the_card_lists_every_conversation_of_the_person_across_networks(world):
    wa = world["msg"]("wa", "whatsapp", 3, them=True, days=2)
    world["msg"]("wa", "whatsapp", 2, them=False, days=1)
    world["msg"]("sig", "signal", 2, them=True, days=40, ident=1)
    events.record_events([{"event_type": "event.retracted", "source": "walter", "source_id": f"retract:{wa[0]}",
                           "occurred_at": NOW, "payload": {"target_event_id": wa[0], "reason": "pytest duplicate"}}])
    with connection() as conn:
        threads = social.conversations(conn, world["entity"], ["cloud_allowed", "redacted_cloud", "local_only"])
    assert [t["network"] for t in threads] == ["whatsapp", "signal"]           # direct chats, most recent first
    w = threads[0]
    assert w["messages"] == 4                                                  # the retracted copy is not counted
    assert w["last_from_owner"] > w["last_from_them"]
    assert w["read_with"] == {"tool": "memory_events", "thread_id": w["thread_id"], "source": "beeper"}
