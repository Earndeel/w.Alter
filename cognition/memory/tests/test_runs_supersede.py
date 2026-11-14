"""A new run of a harness session closes the same session's older open run (lot E8: engine restarted mid-turn)."""
from contextlib import contextmanager
from datetime import datetime
import json
import sqlite3

import pytest

from walter_memory import runs


@pytest.fixture
def store(monkeypatch):
    conn = sqlite3.connect(':memory:')
    def rows(cursor, values):
        row = dict(zip([d[0] for d in cursor.description], values))
        for field in ('started_at', 'ended_at'):
            if row.get(field):
                row[field] = datetime.fromisoformat(row[field])
        return row

    conn.row_factory = rows
    conn.create_function('now', 0, lambda: '2026-11-10T10:31:14+00:00')
    conn.execute("attach database ':memory:' as runs")
    conn.execute("attach database ':memory:' as bus")
    conn.execute('''create table runs.runs (run_id text primary key, status text, origin text, started_at text,
        ended_at text, costs text, updated_at text)''')
    conn.execute('create table bus.events (type text, source text, subject text, payload text, dedupe_key text unique)')
    for rid, sess, at in (('old', 's1', '2026-11-10T10:31:01+00:00'), ('new', 's1', '2026-11-10T10:31:14+00:00'),
                          ('other', 's2', '2026-11-10T10:30:00+00:00')):
        conn.execute("insert into runs.runs values (?, 'open', ?, ?, null, null, null)",
                     (rid, json.dumps({'session_id': sess}), at))
    conn.commit()

    class Connection:
        def execute(self, sql, args=()):
            return conn.execute(sql.replace('%s', '?'), args)

    @contextmanager
    def connect():
        with conn:
            yield Connection()

    monkeypatch.setattr(runs, 'connect', connect)
    yield conn


def status(conn, rid):
    return conn.execute('select status from runs.runs where run_id = ?', (rid,)).fetchone()['status']


def test_only_the_same_sessions_older_open_run_is_cancelled(store):
    assert runs.supersede('s1', 'new') == ['old']
    assert status(store, 'old') == 'cancelled'
    assert status(store, 'new') == 'open'
    assert status(store, 'other') == 'open'
    assert runs.supersede('s1', 'new') == []


def test_a_replayed_start_never_closes_newer_runs(store):
    assert runs.supersede('s1', 'old') == []
    assert status(store, 'new') == 'open'
