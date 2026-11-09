"""Purge policy (cleanup phase 2, 2026-11-09): a purge covers the active database (events, knowledge, views, index,
walter_logs), leaves tombstones so ingestion cannot bring the data back, writes a ledger outside the database, and a
restore of older data is detected (verify) and undone (reapply). Synthetic data only, in the throwaway test database;
the ledger goes to a temporary file (conftest)."""
import json
import uuid
from datetime import datetime, timezone

from walter_memory import events, logs, purge
from walter_memory.db import connect

RUN = uuid.uuid4().hex[:10]
SECRET = f"Zq9-synthetic-{RUN}"
AT = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


def _ev(n, text):
    return {"event_type": "note.recorded", "source": "test", "source_id": f"purge-{RUN}-{n}", "occurred_at": AT,
            "content": text, "payload": {}, "privacy_class": "cloud_allowed"}


def test_purge_reingest_restore_reapply():
    ids = events.record_events([_ev(1, f"le code est {SECRET}"), _ev(2, "rien de secret ici")])["event_ids"]
    secret_id, other_id = ids
    with connect() as conn:
        item = conn.execute("""insert into core.derived_items (kind, content, status, derived_by, source_event_ids)
                               values ('fact', 'synthetic fact', 'derived', 'pytest', %s::uuid[]) returning item_id""",
                            ([secret_id],)).fetchone()["item_id"]
        view = f"pytest:{RUN}"
        conn.execute("insert into views.view (view_key, domain, horizon, title, status) values (%s, 'projects', 'long', 't', 'active')", (view,))
        conn.execute("""insert into views.version (view_key, depth, version, content, builder)
                        values (%s, 'overview', 1, %s, 'pytest')""", (view, f"résumé citant {SECRET}"))
        conn.execute("""insert into views.evidence (view_key, ref_kind, ref_id, role, privacy_class, added_by)
                        values (%s, 'derived', %s, 'support', 'cloud_allowed', 'pytest')""", (view, str(item)))
        conn.execute("""insert into search.chunks (kind, ref_id, chunk_no, occurred_at, source, label, text, tsv, privacy_class, indexer_version)
                        values ('event', %s, 0, %s, 'test', 'note', %s, to_tsvector('simple', %s), 'cloud_allowed', 'pytest')""",
                     (secret_id, AT, SECRET, SECRET))
        w = logs.Writer(conn)
        w.session(f"claude_code/pytest/{RUN}", runtime="claude_code", native_id=RUN)
        w.add(f"claude_code/pytest/{RUN}", "user/message", AT, "l1", text=f"voici {SECRET}", human=True)
        w.flush()
        backup = conn.execute("select * from core.events where event_id = %s", (secret_id,)).fetchone()

    dry = purge.purge(reason="pytest", requested_by="pytest", pattern=SECRET)
    assert dry["counts"] == {"events": 1, "derived": 1, "objects": 0, "walter_logs": 1}
    done = purge.purge(reason="pytest", requested_by="pytest", pattern=SECRET, execute=True)
    assert done["status"] == "executed" and all(not b["automatic_change"] for b in done["backups"])
    with connect() as conn:
        assert conn.execute("select count(*) n from core.events where event_id = %s", (secret_id,)).fetchone()["n"] == 0
        assert conn.execute("select count(*) n from core.events where event_id = %s", (other_id,)).fetchone()["n"] == 1
        assert conn.execute("select count(*) n from core.derived_items where item_id = %s", (item,)).fetchone()["n"] == 0
        assert conn.execute("select count(*) n from search.chunks where ref_id = %s", (secret_id,)).fetchone()["n"] == 0
        v = conn.execute("select content, stale_since from views.version where view_key = %s", (view,)).fetchone()
        assert SECRET not in v["content"] and v["stale_since"] is not None
        wl = conn.execute("select text, event_key from walter_logs.events where session_id = %s",
                          (f"claude_code/pytest/{RUN}",)).fetchone()
        assert wl["text"] == purge.MARK and wl["event_key"]
        # tombstones: the idempotence key stays
        assert conn.execute("select count(*) n from core.event_keys where event_id = %s", (secret_id,)).fetchone()["n"] == 1
    ledger_lines = [json.loads(x) for x in purge.ledger_path().read_text().splitlines()]
    assert {e["kind"] for e in ledger_lines if e["purge_id"] == done["purge_id"]} == {"event", "derived", "walter_logs"}
    assert SECRET not in purge.ledger_path().read_text()                     # identifiers only, never the pattern

    # ingestion cannot bring it back: the connector re-reads its source
    assert events.record_events([_ev(1, f"le code est {SECRET}")])["inserted"] == 0
    with connect() as conn:                                                     # nor the journal's writer
        w = logs.Writer(conn)
        w.session(f"claude_code/pytest/{RUN}", runtime="claude_code", native_id=RUN)
        w.add(f"claude_code/pytest/{RUN}", "user/message", AT, "l1", text=f"voici {SECRET}", human=True)
        w.flush()
        assert conn.execute("select count(*) n from walter_logs.events where session_id = %s and text like %s",
                            (f"claude_code/pytest/{RUN}", f"%{SECRET}%")).fetchone()["n"] == 0
    assert purge.verify()["ok"]

    # a restore of older data brings the row back: detected, then removed again
    with connect() as conn:
        conn.execute("set local walter.purge = 'on'")
        cols = [c for c in backup if c != "tsv"]
        conn.execute(f"insert into core.events ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
                     [json.dumps(backup[c]) if isinstance(backup[c], dict) else backup[c] for c in cols])
    v = purge.verify()
    assert not v["ok"] and v["present_again"]["event"] == 1
    assert purge.reapply(requested_by="pytest")["status"] == "dry_run"
    r = purge.reapply(requested_by="pytest", execute=True)
    assert r["status"] == "executed" and r["removed"]["events"] == 1
    assert purge.verify()["ok"]
    again = purge.reapply(requested_by="pytest", execute=True)           # idempotent
    assert not again["removed"].get("events")


def test_exposure_never_changes_backups():
    rep = purge.exposure()
    assert rep and all(b["automatic_change"] is False for b in rep)
