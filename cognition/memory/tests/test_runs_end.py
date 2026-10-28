"""Explicit run closure exercises the public CLI and real writer on transactional SQLite, never PG."""
from contextlib import contextmanager
from datetime import datetime
import io
import json
import sqlite3

import pytest

from walter_memory import cli, runs


@pytest.fixture
def run_store(monkeypatch):
    conn = sqlite3.connect(':memory:')

    def rows(cursor, values):
        row = dict(zip([c[0] for c in cursor.description], values))
        for field in ('started_at', 'ended_at'):
            if row.get(field):
                row[field] = datetime.fromisoformat(row[field])
        return row

    conn.row_factory = rows
    conn.create_function('now', 0, lambda: '2026-10-28T01:00:10+00:00')
    conn.execute("attach database ':memory:' as runs")
    conn.execute("attach database ':memory:' as bus")
    conn.execute('''create table runs.runs (run_id text primary key, status text, started_at text,
        ended_at text, costs text, updated_at text)''')
    conn.execute('''create table bus.events (type text, source text, subject text, payload text,
        dedupe_key text unique)''')
    conn.execute("insert into runs.runs values ('fixture-run', 'open', '2026-10-28T01:00:00+00:00', null, null, null)")
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
    conn.close()


def test_failed_closure_is_persisted_once_and_cannot_be_relabelled_success(run_store, monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, 'stdin', io.StringIO('{"status":"failed"}'))
    cli.main(['runs', 'end', 'fixture-run'])
    assert json.loads(capsys.readouterr().out) == {'ok': True}
    assert run_store.execute('select status from runs.runs').fetchone()['status'] == 'failed'
    first = run_store.execute('select * from runs.runs').fetchone()
    for status in ('failed', 'ended'):
        monkeypatch.setattr(cli.sys, 'stdin', io.StringIO(json.dumps({'status': status})))
        cli.main(['runs', 'end', 'fixture-run'])
        capsys.readouterr()
    assert run_store.execute('select * from runs.runs').fetchone() == first
    emitted = run_store.execute('select * from bus.events').fetchall()
    assert len(emitted) == 1
    assert emitted[0]['type'] == 'run.ended'
    assert json.loads(emitted[0]['payload'])['status'] == 'failed'


@pytest.mark.parametrize('status', ['ended', 'cancelled'])
def test_other_explicit_terminal_statuses_are_preserved(run_store, monkeypatch, capsys, status):
    monkeypatch.setattr(cli.sys, 'stdin', io.StringIO(json.dumps({'status': status})))
    cli.main(['runs', 'end', 'fixture-run'])
    assert json.loads(capsys.readouterr().out) == {'ok': True}
    assert run_store.execute('select status from runs.runs').fetchone()['status'] == status


@pytest.mark.parametrize('payload', [{}, [], {'status': 'open'}, {'status': 'abandoned'}, {'status': None}])
def test_missing_or_unapproved_status_cannot_close_the_run(run_store, monkeypatch, payload):
    monkeypatch.setattr(cli.sys, 'stdin', io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as error:
        cli.main(['runs', 'end', 'fixture-run'])
    assert error.value.code == 2
    assert run_store.execute('select status from runs.runs').fetchone()['status'] == 'open'
    assert not run_store.execute('select * from bus.events').fetchall()


def test_target_run_must_be_explicit_before_any_closure(run_store, monkeypatch):
    monkeypatch.setattr(cli.sys, 'stdin', io.StringIO('{"status":"failed"}'))
    with pytest.raises(SystemExit) as error:
        cli.main(['runs', 'end'])
    assert error.value.code == 2
    assert run_store.execute('select status from runs.runs').fetchone()['status'] == 'open'
