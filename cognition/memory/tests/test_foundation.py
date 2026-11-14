"""P1/P1.5 acceptance tests. Uses source 'test' events and purges them at the end (break-glass, no backup rewrite).
Run: cd /opt/walter-memory && venv/bin/python -m pytest -q tests/"""
import os
import tempfile
import uuid
from datetime import datetime, timezone

import pytest

from walter_memory import events, ingestion, llm, objects, privacy, purge, types
from walter_memory.db import connection

RUN = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module", autouse=True)
def test_source():
    with connection() as conn:
        conn.execute("""insert into core.sources (source, kind, description, privacy_default)
                        values ('test', 'agent', 'automated tests', 'cloud_allowed') on conflict do nothing""")
    yield
    with connection() as conn:
        ids = [r["event_id"] for r in conn.execute("select event_id from core.events where source = 'test'").fetchall()]
        conn.execute("set local walter.purge = 'on'")
        conn.execute("delete from core.event_keys where source = 'test'")
        conn.execute("delete from core.events where source = 'test'")
        conn.execute("delete from privacy.detections where target_ref like 'test:%'")
        conn.execute("delete from core.source_identities where source = 'test'")
        conn.execute("delete from system.model_calls where processor = 'pytest'")
        conn.execute("delete from ingestion.jobs where queue = 'pytest'")
        conn.execute("""delete from system.purge_ledger where purge_id in
                        (select purge_id from system.purges where requested_by = 'pytest')""")
        conn.execute("delete from system.purges where requested_by = 'pytest'")


def ev(i, **kw):
    return {"event_type": "message.received", "source": "test", "source_account": "pytest", "source_id": f"{RUN}-{i}",
            "occurred_at": datetime(2026, 10, 1, 12, i, tzinfo=timezone.utc), "content": f"bonjour {i}",
            "thread_id": f"chat-{RUN}", "actor": {"account": "pytest", "external_id": f"user-{RUN}", "display_name": "Testeur"},
            "payload": {"chat": {"id": f"chat-{RUN}", "type": "single"}}, **kw}


def test_idempotent_batch():
    first = events.record_events([ev(1), ev(2)])
    again = events.record_events([ev(1), ev(2), ev(3)])
    assert first["inserted"] == 2 and again == {**again, "inserted": 1, "duplicates": 2}


def test_append_only():
    with pytest.raises(Exception, match="append-only"):
        with connection() as conn:
            conn.execute("update core.events set content = 'x' where source = 'test'")


def test_unknown_type_and_invalid_payload():
    with pytest.raises(types.UnknownEventType):
        events.record_events([ev(4, event_type="message.teleported")])
    with pytest.raises(types.InvalidPayload):
        events.record_events([ev(5, event_type="message.edited", payload={})])  # 'target_source_id' required


def test_retired_observability_types_are_refused():
    """Cleanup phase 2 (2026-11-09): agent execution lives in walter_logs, never again in core.events."""
    for t in ("tool.called", "skill.used"):
        with pytest.raises(types.RetiredEventType, match="retired"):
            events.record_events([ev(7, event_type=t, payload={"tool": "x", "skill": "x"})])
    types.sync_seed()      # re-seeding never re-activates a retired type
    with pytest.raises(types.RetiredEventType):
        events.record_events([ev(8, event_type="tool.called", payload={"tool": "x"})])


def test_extensible_taxonomy_without_migration():
    types.register("test.pinged", "pytest-only type", {"type": "object"})
    assert events.record_events([ev(6, event_type="test.pinged", payload={})])["inserted"] == 1
    with connection() as conn:
        conn.execute("delete from core.event_types where name = 'test.pinged'")


def test_identity_recorded_without_entity():
    with connection() as conn:
        row = conn.execute("""select i.display_name, (select count(*) from core.identity_links l where l.identity_id = i.identity_id) links
                              from core.source_identities i where source = 'test' and external_id = %s""", (f"user-{RUN}",)).fetchone()
    assert row["display_name"] == "Testeur" and row["links"] == 0


def test_secret_detection_makes_local_only():
    events.record_events([ev(7, content="mon mot de passe est Tr0ub4dor&3 ne le dis à personne")])
    with connection() as conn:
        row = conn.execute("select privacy_class from core.events where source='test' and source_id=%s", (f"{RUN}-7",)).fetchone()
        det = conn.execute("select category, action from privacy.detections where target_ref = %s", (f"test:{RUN}-7",)).fetchall()
    assert row["privacy_class"] == "local_only" and {"category": "secret", "action": "flagged_for_purge"} in det


def test_cloud_reader_cannot_see_local_only():
    visible = events.get_events(source="test", max_privacy="cloud_allowed", limit=100)
    assert all(e["privacy_class"] == "cloud_allowed" for e in visible)
    assert f"{RUN}-7" not in {e["source_id"] for e in visible}


def test_llm_guard_refuses_local_only():
    with pytest.raises(llm.PrivacyRefused):
        llm.chat([{"role": "user", "content": "x"}], model="openai/gpt-5-mini", processor="pytest", privacy_class="local_only")


def test_redaction_roundtrip():
    text = "Appelle Marika au +33 6 31 01 97 26 ou marika@example.com"
    red, mp = privacy.redact(text, ["Marika"])
    assert "Marika" not in red and "+33" not in red and "@" not in red
    assert privacy.restore(red, mp) == text


def test_local_only_object_goes_to_encrypted_zone():
    with tempfile.NamedTemporaryFile("wb", suffix=".txt", delete=False) as f:
        f.write(f"pytest secure object {RUN}".encode())
    row = objects.put_object(f.name, "test", privacy_class="local_only")
    assert row["storage_zone"] == "secure"
    back = objects.get_object(str(row["id"]), tempfile.gettempdir())
    assert back.read_bytes() == open(f.name, "rb").read()
    res = purge.purge(reason="pytest cleanup", requested_by="pytest", object_refs=[str(row["id"])], execute=True)
    assert res["counts"]["objects"] == 1 and objects.find(str(row["id"])) is None
    with connection() as conn:
        conn.execute("delete from core.objects where id = %s", (row["id"],))
    os.unlink(f.name); back.unlink(missing_ok=True)


def test_break_glass_purge_events():
    dry = purge.purge(reason="pytest", requested_by="pytest", pattern="Tr0ub4dor", execute=False)
    assert dry["counts"]["events"] == 1
    done = purge.purge(reason="pytest", requested_by="pytest", pattern="Tr0ub4dor", execute=True)
    assert done["status"] == "executed"
    assert not events.get_events(source="test", text="Tr0ub4dor")


def test_queue_skip_locked_and_retry():
    jid = ingestion.enqueue("pytest", {"n": 1}, dedupe_key=f"pytest-{RUN}")
    assert ingestion.enqueue("pytest", {"n": 1}, dedupe_key=f"pytest-{RUN}") is None
    calls = []
    def boom(payload):
        calls.append(payload); raise RuntimeError("transient")
    assert ingestion.work("pytest", boom) == 1
    with connection() as conn:
        job = conn.execute("select status, attempts from ingestion.jobs where job_id = %s", (jid,)).fetchone()
    assert job == {"status": "queued", "attempts": 1}


def test_detector_false_positives():
    assert privacy.detect("Lance un diagnostic du serveur et regarde stdout / STD error") == []
    assert privacy.detect("session id 1790882198123456 et timestamp 4111111111111111") == []
    assert ("secret", "card_number") in privacy.detect("ma carte visa 4111 1111 1111 1111 exp 12/28")
    assert ("health", "health") in privacy.detect("J'ai rendez-vous médical demain, prise de sang")


def test_card_detector_ignores_port_lists():
    assert privacy.detect("for p in 8642 8644 8787 8888 8896 12110; do curl :$p; done") == []
    assert privacy.detect("IG @x (ID 1784453396146767) rien à voir avec une card plus loin dans le texte") == []


def test_intimate_detector_and_tightening():
    assert ("intimate", "intimate") in privacy.detect("Yok | seins 5/5, visage 2.5/5")
    assert not any(c == "intimate" for c, _ in privacy.detect("Déploie le string de config sur le serveur"))  # known FP risk documented
