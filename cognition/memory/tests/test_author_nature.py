"""27/11/2026 (Monsieur): Memory tells apart the technical source, the channel, the author and the author's nature
(human, walter, agent, bot, service). « people » = exchanges with humans whatever the channel; W.Alter's and other
agents' messages stay whole in Memory but are never read as messages from people; a newest-first read says when a
source is no longer synchronised."""
import tomllib
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import authors, context, events, ingestion, social
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)
CFG = authors._merge(tomllib.loads(authors.MODULE_CONFIG.read_text()), {"walter": {"handles": ["TestWalterbot"]}})


@pytest.fixture(autouse=True)
def walter_handle(monkeypatch):
    monkeypatch.setattr(authors, "settings", lambda: CFG)


def test_rules():
    tg = "telegram.123"
    c = lambda source, **a: authors.classify(source, a, CFG)[0]
    assert c("beeper", external_id="@telegram_1:beeper.local", account=tg, handles={tg: "TestWalterbot"}) == "walter"
    assert c("beeper", external_id="@telegram_2:beeper.local", account=tg, handles={tg: "scena_01_bot"}) == "bot"
    assert c("beeper", external_id="@telegram_3:beeper.local", account=tg, handles={tg: "jeanbot"}) == "bot"
    assert c("beeper", external_id="@whatsappbot:beeper.local", account="whatsapp") == "service"
    assert c("beeper", external_id="@telegram_777000:beeper.local", account=tg, display_name="Telegram") == "service"
    assert c("beeper", external_id="@x:beeper.local", account="facebookgo", display_name="Meta AI") == "agent"
    assert c("gmail", external_id="no-reply@shop.example", account="me") == "service"
    assert c("gmail", external_id="jean@example.org", account="me") == "human"
    assert c("beeper", external_id="@me:beeper.com", account="whatsapp", is_self=True) == "human"
    assert c("claude_code", external_id="claude-code", account="vm") == "agent"
    assert c("hermes", external_id="walter", account="tui") == "walter"
    assert c("hermes", external_id="monsieur", account="tui") == "human"
    # a handle that is not a bot username stays a person (Telegram's rule applies to Telegram only)
    assert c("beeper", external_id="@whatsapp_33:beeper.local", account="whatsapp", handles={"whatsapp": "robot"}) == "human"


def msg(thread, event_type, text, actor, *, chat="single", minutes=5, network="telegram"):
    ev = {"event_type": event_type, "source": "beeper", "source_account": actor["account"],
          "source_id": uuid.uuid4().hex, "thread_id": thread, "content": text, "privacy_class": "cloud_allowed",
          "occurred_at": NOW - timedelta(minutes=minutes), "actor": actor,
          "payload": {"chat": {"id": thread, "type": chat, "network": network, "title": "t"}}}
    return events.record_events([ev])["event_ids"][0]


def test_people_are_humans_on_any_channel_and_agents_stay_whole():
    tag, tg = uuid.uuid4().hex[:8], "telegram.123"
    me = {"external_id": f"@me-{tag}", "account": tg, "display_name": "Moi", "is_self": True}
    bot_thread, bot2_thread, dm, group = (f"!{k}-{tag}:test" for k in ("walter", "bot", "dm", "group"))
    walter = {"external_id": f"@telegram_w{tag}:beeper.local", "account": tg, "display_name": "W.Alter",
              "handles": {tg: "TestWalterbot"}}
    bot = {"external_id": f"@telegram_b{tag}:beeper.local", "account": tg, "display_name": "Scena",
           "handles": {tg: f"scena_{tag}_bot"}}
    friend = {"external_id": f"@telegram_f{tag}:beeper.local", "account": tg, "display_name": "Ami"}
    bridge = {"external_id": "@telegrambot:beeper.local", "account": tg}
    from_walter = msg(bot_thread, "message.received", f"rapport {tag}", walter, minutes=9)
    to_walter = msg(bot_thread, "message.sent", f"question {tag}", me, minutes=10)
    from_bot = msg(bot2_thread, "message.received", f"lien {tag}", bot, minutes=8)
    from_friend = msg(dm, "message.received", f"salut {tag}", friend, minutes=7)
    notice = msg(dm, "message.received", f"notice {tag}", bridge, minutes=6)       # a bridge notice in a real DM
    to_friend = msg(dm, "message.sent", f"ça va {tag}", me, minutes=5)
    in_group = msg(group, "message.received", f"bot {tag}", bot, chat="group", minutes=4)
    ids = lambda **kw: {r["event_id"] for r in events.get_events(text=tag, max_privacy="cloud_allowed", **kw)}
    assert ids(source="people") == {from_friend, to_friend}          # the DM stays a human exchange
    assert ids(source="people", event_types=["message.received"]) == {from_friend}
    assert ids(source="agents") == {from_walter, to_walter}          # W.Alter on Telegram is an agent conversation
    everything = ids(source="beeper")
    assert {from_walter, to_walter, from_bot, notice, in_group} <= everything   # nothing hidden from Memory
    kinds = {r["event_id"]: r["actor_kind"] for r in events.get_events(text=tag, max_privacy="cloud_allowed")}
    assert (kinds[from_walter], kinds[from_bot], kinds[notice], kinds[from_friend]) == ("walter", "bot", "service", "human")


def test_identity_nature_follows_what_is_known_not_one_message():
    tag, tg = uuid.uuid4().hex[:8], "telegram.123"
    ext = f"@telegram_n{tag}:beeper.local"
    msg(f"!n-{tag}:test", "message.received", "a", {"external_id": ext, "account": tg, "handles": {tg: f"n{tag}bot"}})
    msg(f"!n-{tag}:test", "message.received", "b", {"external_id": ext, "account": tg, "display_name": "N"})  # no handle
    with connection() as conn:
        a = conn.execute("select attributes from core.source_identities where external_id = %s", (ext,)).fetchone()
    assert a["attributes"]["author"] == "bot" and a["attributes"]["author_rule"] == "telegram_bot_username"


def test_person_entries_of_non_humans_take_their_nature():
    tag, tg = uuid.uuid4().hex[:8], "telegram.123"
    ext = f"@telegram_e{tag}:beeper.local"
    msg(f"!e-{tag}:test", "message.received", "x", {"external_id": ext, "account": tg, "handles": {tg: f"e{tag}bot"}})
    with connection() as conn:
        ident = conn.execute("select identity_id from core.source_identities where external_id=%s", (ext,)).fetchone()
        ent = conn.execute("""insert into core.entities (entity_type, canonical_name) values ('person', %s)
                              returning entity_id""", (f"bot {tag}",)).fetchone()["entity_id"]
        conn.execute("""insert into core.identity_links (identity_id, entity_id, status, confidence, method)
                        values (%s, %s, 'confirmed', 1, 'test')""", (ident["identity_id"], ent))
    assert social.resolve_identities()["retyped"] >= 1
    with connection() as conn:
        assert conn.execute("select entity_type from core.entities where entity_id=%s", (ent,)).fetchone()["entity_type"] == "bot"


def test_a_source_no_longer_synchronised_is_said():
    tag = uuid.uuid4().hex[:8]
    name = f"beeper:test-{tag}"
    ingestion.register_connector(name, "beeper", "push", "test", timedelta(minutes=10))
    with connection() as conn:
        conn.execute("update ingestion.connectors set last_success_at = now() - interval '2 hours' where connector=%s",
                     (name,))
    try:
        assert ingestion.freshness(["beeper"])["beeper"]["state"] == "stale"
        assert events.staleness([], "people")["freshness"]["beeper"]["state"] == "stale"
        text, _, _ = context._recent_exchanges(24, 400, "cloud_allowed")
        assert text.startswith("- ⚠ beeper n'est plus synchronisé")
    finally:
        with connection() as conn:
            conn.execute("delete from ingestion.connectors where connector = %s", (name,))
