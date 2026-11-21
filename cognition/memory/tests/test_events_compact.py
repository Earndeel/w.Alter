"""events.compact / order (07/11): an agent finds « the first event about X » in one call, with a bounded answer."""
from walter_memory import events


def _row(i, content):
    return {"event_id": f"e{i}", "occurred_at": f"2026-11-0{i}", "source": "codex", "event_type": "message.sent",
            "thread_id": "t", "actor_name": None, "content": content, "payload": {"big": "x" * 5000}}


def test_compact_windows_content_and_bounds_answer():
    rows = [_row(i, "a" * 3000 + " Sagora installée " + "b" * 3000) for i in range(1, 9)]
    out = events.compact(rows, "sagora", width=300, budget=1500)
    assert out["events"] and "payload" not in out["events"][0]
    assert "Sagora" in out["events"][0]["content"] and len(out["events"][0]["content"]) <= 302
    assert out["truncated"] == len(rows) - len(out["events"]) > 0 and "event_id" in out["hint"]


def test_order_is_validated():
    import pytest
    with pytest.raises(ValueError):
        events.get_events(order="sideways")


def _msg(i, *, mine=False, day=None):
    return {"event_id": f"m{i}", "occurred_at": day or f"2026-11-{10 + i:02d} 09:00:00.123456+00:00", "source": "beeper",
            "event_type": "message.sent" if mine else "message.received", "thread_id": "!chat:x", "source_id": f"s{i}",
            "actor_name": None if mine else "Contact", "actor_is_self": mine, "content": f"message {i}", "payload": {}}


def test_a_conversation_reads_as_a_transcript_with_the_owner_named_and_an_exact_next_window(monkeypatch):
    monkeypatch.setattr(events, "owner_label", lambda: "Monsieur")
    monkeypatch.setattr(events, "attachments", lambda rows, **kw: {})
    rows = [_msg(i, mine=i % 2 == 0) for i in range(1, 9)]                      # oldest first
    out = events.compact(rows, None, width=100, budget=400)
    assert out["thread_id"] == "!chat:x" and out["source"] == "beeper"
    first = out["events"][0]
    assert set(first) == {"event_id", "at", "who", "text"} and first["who"] == "Contact"
    assert out["events"][1]["who"] == "Monsieur"                               # never the network's account ID
    n = len(out["events"])
    assert 0 < n < 8 and out["truncated"] == 8 - n
    assert out["next"] == {"since": rows[n]["occurred_at"]}                    # the first one not shown (inclusive)
    newest = list(reversed(rows))
    out = events.compact(newest, None, width=100, budget=400)
    n = len(out["events"])
    assert out["next"] == {"until": newest[n - 1]["occurred_at"]}              # the last one shown (exclusive)


def test_a_search_keeps_the_former_shape_with_the_owner_named(monkeypatch):
    monkeypatch.setattr(events, "owner_label", lambda: "Monsieur")
    monkeypatch.setattr(events, "attachments", lambda rows, **kw: {})
    out = events.compact([_msg(1, mine=True), _msg(2)], "message", width=100)
    assert "next" not in out and out["events"][0]["actor"] == "Monsieur" and "content" in out["events"][0]
