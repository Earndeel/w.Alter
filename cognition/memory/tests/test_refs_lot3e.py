"""Lot 3e (26/11): what one read produces, the next read takes — typed references and opaque cursors.

A reference is an identifier, never an authorisation: these tests check the decoding AND that a decoded reference
reads no more than the plain arguments would (privacy of derived knowledge and of a replied-to message)."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import refs


# ── pure ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_typed_and_legacy_forms_split():
    assert refs.split("event:abc") == ("event", "abc")
    assert refs.split("abc") == (None, "abc")
    assert refs.split("weird:abc") == (None, "weird:abc")          # unknown prefix: a legacy value, untouched
    assert refs.expect("object:1234", "object") == "1234" and refs.expect("1234", "object") == "1234"


def test_a_reference_of_another_kind_names_its_reader():
    with pytest.raises(refs.RefError, match="memory_view"):
        refs.expect("derived:x", "object")


@pytest.mark.parametrize("ref,want", [
    ("claude_code/vm/45d2#1160", ("claude_code/vm/45d2", 1160)),          # what logs_search prints (X1)
    ("log:walter/abc#7", ("walter/abc", 7)),
    ("walter/abc", ("walter/abc", None)),
    ("a#b#12", ("a#b", 12)),                                              # split on the last '#'
])
def test_log_refs(ref, want):
    assert refs.log_ref(ref) == want


def test_cursor_round_trip_and_refusals():
    token = refs.encode_cursor("events", {"until": "2026-11-20 10:00:00"})
    assert refs.decode_cursor("events", token, {"since", "until"}) == {"until": "2026-11-20 10:00:00"}
    with pytest.raises(refs.RefError, match="another read"):
        refs.decode_cursor("logs", token, {"since", "until"})
    forged = refs.encode_cursor("events", {"until": "x", "max_privacy": "local_only"})   # never a privacy override
    with pytest.raises(refs.RefError, match="does not page by"):
        refs.decode_cursor("events", forged, {"since", "until"})
    with pytest.raises(refs.RefError):
        refs.decode_cursor("events", "%%%not-a-cursor", {"since"})


def test_a_thread_read_returns_a_cursor_with_the_same_window_as_next():
    from walter_memory import events
    rows = [{"event_id": f"m{i}", "occurred_at": f"2026-11-{20 - i:02d} 09:00:00", "source": "beeper",
             "event_type": "message.received", "thread_id": "!t", "actor_name": "C", "content": "x" * 400,
             "payload": {}} for i in range(10)]
    out = events.compact(rows, None, width=300, budget=1200)
    assert out["truncated"] and out["next"] and out["cursor"]
    assert refs.decode_cursor("events", out["cursor"], {"since", "until"}) == out["next"]


# ── with the test database ────────────────────────────────────────────────────────────────────────────────────────
def _event(content, privacy="cloud_allowed", thread=None, source_id=None, reply_to=None):
    from walter_memory.events import record_event
    sid = source_id or uuid.uuid4().hex
    r = record_event(event_type="message.received", source="beeper", source_id=sid, thread_id=thread,
                     occurred_at=datetime.now(timezone.utc) - timedelta(minutes=5), content=content,
                     reply_to=reply_to, privacy_class=privacy,
                     actor={"account": "test", "external_id": "x", "display_name": "X"})
    return r["event_ids"][0], sid


def _derived(text, event_id, privacy="cloud_allowed"):
    from walter_memory.db import connection
    with connection() as conn:
        return str(conn.execute("""insert into core.derived_items (kind, content, status, derived_by, generation,
                                       privacy_class, stage, epistemic, scope, source_event_ids, valid_from)
                                   values ('decision', %s, 'derived', 'l3.extract', 'g1', %s, 'decided', 'stated_owner',
                                           'durable', %s::uuid[], now()) returning item_id""",
                                (text, privacy, [event_id])).fetchone()["item_id"])


def test_derived_reference_reads_with_the_same_check_as_search():
    from walter_memory import views
    ok_event, _ = _event("on garde Nginx")
    ok = _derived("Le site public utilise Nginx", ok_event)
    d = views.read_derived(ok)
    assert d["typed_ref"] == f"derived:{ok}" and d["text"] == "Le site public utilise Nginx"
    assert d["evidence"] == [f"event:{ok_event}"]
    secret_event, _ = _event("une confidence", privacy="local_only")
    hidden = _derived("Une connaissance tirée d'un message local", secret_event)   # cloud item, local provenance
    assert views.read_derived(hidden) == {"error": f"no knowledge item derived:{hidden}"}
    assert views.read_derived(hidden, privacy="local_only")["text"].startswith("Une connaissance")
    assert views.read_derived("not-a-uuid")["error"] == "invalid_request"


def test_reply_to_resolves_only_to_a_readable_event():
    from walter_memory import events
    thread = f"!t-{uuid.uuid4().hex[:6]}"
    first, sid = _event("question", thread=thread)
    answer, _ = _event("réponse", thread=thread, reply_to=sid)
    row = events.with_refs(events.get_events(event_id=answer, limit=1, max_privacy="cloud_allowed"),
                           max_privacy="cloud_allowed")[0]
    assert row["typed_ref"] == f"event:{answer}" and row["reply_to_event_id"] == first
    private, psid = _event("privé", privacy="local_only", thread=thread)
    answer2, _ = _event("suite", thread=thread, reply_to=psid)
    row2 = events.with_refs(events.get_events(event_id=answer2, limit=1, max_privacy="cloud_allowed"),
                            max_privacy="cloud_allowed")[0]
    assert "reply_to_event_id" not in row2                   # the hidden event is not even said to exist


def test_typed_links_resolve_to_the_message_link():
    from walter_memory import objects
    ev, sid = _event("un fichier joint")
    assert objects.resolve_links([f"event:{ev}"]) == [("beeper_message", sid)]
    assert objects.resolve_links(["entity:0f0e", "beeper_message:abc"]) == [("entity", "0f0e"), ("beeper_message", "abc")]
    with pytest.raises(ValueError):
        objects.resolve_links(["no-kind"])
    with pytest.raises(ValueError):
        objects.resolve_links([f"event:{uuid.uuid4()}"])
