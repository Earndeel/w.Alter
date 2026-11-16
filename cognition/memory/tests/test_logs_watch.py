"""walter-logs-watch: a reader of a Hermes state.db must not look like a write (the 2026-11-16 self-trigger loop)."""
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from connectors.walter_logs import hermes_fingerprint  # noqa: E402


def _wal_db(tmp_path):
    db = tmp_path / "state.db"
    w = sqlite3.connect(db)
    w.execute("pragma journal_mode=wal")
    w.execute("pragma wal_autocheckpoint=0")
    w.execute("create table m(id integer primary key, t text)")
    w.execute("insert into m(t) values ('a')")
    w.commit()
    return db, w


def test_read_only_reader_leaves_fingerprint_unchanged(tmp_path):
    db, w = _wal_db(tmp_path)
    before = hermes_fingerprint(db)
    for _ in range(3):                                   # what sync_hermes and walter-memory-hermes do
        r = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        r.execute("select max(id) from m").fetchone()
        r.close()
    assert hermes_fingerprint(db) == before
    w.close()


def test_a_write_changes_fingerprint(tmp_path):
    db, w = _wal_db(tmp_path)
    before = hermes_fingerprint(db)
    time.sleep(0.01)
    w.execute("insert into m(t) values ('b')")
    w.commit()
    assert hermes_fingerprint(db) != before
    w.close()


def test_missing_wal_is_part_of_the_fingerprint(tmp_path):
    db = tmp_path / "state.db"
    sqlite3.connect(db).close()
    assert hermes_fingerprint(db)[1] is None
