"""The owner's reaction is one event whatever ID carries it (Matrix ID over HTTP, bridge ID in a WS snapshot), and
a WS snapshot keeps its identifiers when the secret masker scrubs it. Two different reactors stay two events.
Test DB only (5440), fake chats."""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from walter_memory import events, ingestion
from walter_memory.db import connection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "connectors"))
import beeper  # noqa: E402
import beeper_watch as watch  # noqa: E402


@pytest.fixture(autouse=True)
def connector():
    ingestion.register_connector("beeper", "beeper", "push", "native pytest", timedelta(minutes=10))


def chat():
    return {"id": f"!{uuid.uuid4().hex}:pytest", "accountID": "fixture", "type": "single",
            "participants": {"items": [{"id": "@owner:pytest", "isSelf": True}, {"id": "contact-1"}]}}


def msg(reactor, emoji="❤️", sender="contact-1", own=False):
    return {"id": uuid.uuid4().hex, "sortKey": "7", "timestamp": "2026-11-20T08:00:00+00:00", "senderID": sender,
            "text": "fixture", "isSender": own, "reactions": [{"participantID": reactor, "reactionKey": emoji}]}


def reactions(c):
    with connection() as conn:
        return conn.execute("""select e.source_id, i.is_self from core.events e left join core.source_identities i
                               on i.identity_id = e.actor_identity_id where e.thread_id = %s
                               and e.event_type = 'reaction.added'""", (c["id"],)).fetchall()


def test_owner_reaction_under_two_ids_is_one_event():
    c = chat()
    with connection() as conn:
        beeper.store_messages(c, [msg("@owner:pytest")], conn=conn, scope="s")
    with connection() as conn:   # same message seen again from the WS snapshot: the owner by their bridge ID
        c2 = {**c, "participants": {"items": c["participants"]["items"] + [{"id": "bridge-owner", "isSelf": True}]}}
        beeper.store_messages(c2, [msg("bridge-owner")], conn=conn, scope="s")
    rows = reactions(c)
    assert len(rows) == 1 and rows[0]["is_self"]


def test_two_people_with_the_same_emoji_stay_two_reactions():
    c = chat()
    with connection() as conn:
        beeper.store_messages(c, [msg("@owner:pytest")], conn=conn, scope="s")
    with connection() as conn:
        beeper.store_messages(c, [msg("contact-1")], conn=conn, scope="s")
    rows = reactions(c)
    assert len(rows) == 2 and sorted(r["is_self"] for r in rows) == [False, True]


def test_ws_snapshot_keeps_identifiers_but_masks_content(monkeypatch):
    monkeypatch.setattr(events, "vault_scrub", lambda t: t.replace("owner-login", "«secret:vault»") if t else t)
    frame = {"type": "message.upserted", "chatID": "!x:pytest", "entries": [
        {"id": "m1", "senderID": "owner-login", "text": "my login is owner-login",
         "reactions": [{"participantID": "owner-login", "reactionKey": "👍"}]}]}
    clean = watch.scrub(frame)
    e = clean["entries"][0]
    assert e["senderID"] == "owner-login" and e["reactions"][0]["participantID"] == "owner-login"
    assert "owner-login" not in e["text"]


def test_server_html_escaped_text_is_stored_as_written():
    c = chat()
    m = {**msg("contact-1"), "text": "Tom &amp; Léa&nbsp;: 3 &lt; 5", "reactions": []}
    evs, _ = beeper.to_events(c, [m], {})
    assert evs[0]["content"] == "Tom & Léa\xa0: 3 < 5"
