"""27/11/2026 (Monsieur, « derniers messages reçus »): common spellings of the order are read, a family is asked
explicitly, an unknown type answers the valid names (never an empty list), and « people » keeps the owner's
exchanges with others apart from his conversations with W.Alter's agents."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import context, events

NOW = datetime.now(timezone.utc)


def record(source, event_type, text, *, minutes=5, is_self=False, account="whatsapp"):
    ev = {"event_type": event_type, "source": source, "source_account": account, "source_id": uuid.uuid4().hex,
          "thread_id": f"!t-{uuid.uuid4().hex[:6]}", "content": text, "occurred_at": NOW - timedelta(minutes=minutes),
          "privacy_class": "cloud_allowed",
          "actor": {"external_id": "@me" if is_self else f"@x-{uuid.uuid4().hex[:6]}", "account": account,
                    "display_name": "Moi" if is_self else "Ami", "is_self": is_self}}
    return events.record_events([ev])["event_ids"][0]


def test_order_spellings():
    assert events.order_of("desc") == events.order_of("newest") == "desc"
    assert events.order_of("ASC") == events.order_of("oldest") == "asc"
    with pytest.raises(events.UnknownFilter) as e:
        events.order_of("latest")
    assert e.value.valid == ["newest", "oldest"]


def test_family_unknown_and_source_groups():
    tag = uuid.uuid4().hex[:8]
    got = record("beeper", "message.received", f"salut {tag}")
    mine = record("beeper", "message.sent", f"réponse {tag}", minutes=4, is_self=True)
    prompt = record("claude_code", "message.received", f"prompt {tag}", minutes=3, account="vm")
    ids = lambda **kw: [r["event_id"] for r in events.get_events(text=tag, max_privacy="cloud_allowed", **kw)]
    assert set(ids(event_types=["message.*"])) == {got, mine, prompt}          # a family, explicitly
    assert ids(event_types=["message.received"], source="people") == [got]      # exact type, with others only
    assert ids(event_types=["message.received"], source="agents") == [prompt]
    assert ids(event_types=["message.*"], order="oldest")[0] == got
    with pytest.raises(events.UnknownFilter) as e:                               # a bare family: said, not empty
        ids(event_types=["message"])
    assert "message.received" in e.value.valid and "message.*" in e.value.valid
    with pytest.raises(events.UnknownFilter) as e:
        ids(event_types=["messages.recieved"])
    assert "message.received" in e.value.valid


def test_chronological_context_reads_received_in_order_without_rerank(monkeypatch):
    tag = uuid.uuid4().hex[:8]
    older = record("beeper", "message.received", f"premier {tag}", minutes=30)
    newer = record("beeper", "message.received", f"second {tag}", minutes=2)
    record("beeper", "message.sent", f"envoyé {tag}", minutes=1, is_self=True)
    record("claude_code", "message.received", f"prompt {tag}", minutes=1, account="vm")
    monkeypatch.setattr("walter_memory.search.rerank_pools",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no rerank for a chronological read")))
    zero = dict.fromkeys(context.DEFAULT_BUDGET, 0)
    r = context.get_context("mes derniers messages reçus", budget={**zero, "evidence": 2000}, include_profile=False,
                            recent_hours=1)
    text = r["sections"]["evidence"]
    assert text.index(f"second {tag}") < text.index(f"premier {tag}")           # newest first
    assert f"envoyé {tag}" not in text and f"prompt {tag}" not in text           # only what others wrote to him
    assert r["trace"]["sections"]["evidence"]["mode"] == "chronological"
    assert f"event:{newer}" in text and f"event:{older}" in text                 # each line cites its event
