"""Public run lookup against real in-memory SQL, without PostgreSQL or production data."""
from contextlib import contextmanager
import io
import json
import sqlite3

import pytest

from walter_memory import cli, db, runs


@pytest.fixture
def run_store(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute("attach database ':memory:' as runs")
    conn.execute('''create table runs.runs
        (run_id text, origin text, status text, privacy_class text, started_at text, goal text)''')

    class Connection:
        def execute(self, sql, args=()):
            # Translate only the driver's parameter marker; JSON access/filter/order run in SQLite itself.
            return conn.execute(sql.replace('%s', '?'), args)

    @contextmanager
    def connect():
        yield Connection()

    monkeypatch.setattr(db, 'connect', connect)

    def add(run_id, status, started_at, session='dsh/vm/fixture', pclass='cloud_allowed'):
        conn.execute('insert into runs.runs values (?, ?, ?, ?, ?, ?)',
            (run_id, json.dumps({'session_id': session}), status, pclass, started_at, 'Never expose this goal'))

    yield add
    conn.close()


def test_open_lookup_selects_latest_open_run_of_exact_session_with_metadata_only(run_store, capsys):
    run_store('open-older', 'ended', '2026-10-28T00:00:00')
    run_store('open-current', 'open', '2026-10-28T01:00:00', pclass='local_only')
    run_store('ended-newer', 'ended', '2026-10-28T02:00:00')
    run_store('other-session', 'open', '2026-10-28T03:00:00', session='dsh/vm/another')
    cli.main(['runs', 'find', '--session', 'dsh/vm/fixture', '--open-only'])
    assert json.loads(capsys.readouterr().out) == {
        'run_id': 'open-current', 'status': 'open', 'privacy_class': 'local_only'}


def test_open_lookup_never_falls_back_to_a_closed_or_another_session_run(run_store, capsys):
    run_store('ended', 'ended', '2026-10-28T02:00:00')
    run_store('other', 'open', '2026-10-28T03:00:00', session='dsh/vm/another')
    cli.main(['runs', 'find', '--session', 'dsh/vm/fixture', '--open-only'])
    assert json.loads(capsys.readouterr().out) == {'run_id': None, 'status': None, 'privacy_class': None}


def test_open_session_lookup_refuses_multiple_open_runs(run_store, capsys):
    run_store('open-one', 'open', '2026-10-28T01:00:00')
    run_store('open-two', 'open', '2026-10-28T02:00:00')
    cli.main(['runs', 'find', '--session', 'dsh/vm/fixture', '--open-only'])
    assert json.loads(capsys.readouterr().out) == {
        'run_id': None, 'status': None, 'privacy_class': None, 'error': 'ambiguous_open_runs'}


def test_default_lookup_keeps_existing_closed_run_behavior_and_response_shape(run_store, capsys):
    run_store('open', 'open', '2026-10-28T01:00:00')
    run_store('ended-newer', 'ended', '2026-10-28T02:00:00')
    cli.main(['runs', 'find', '--session', 'dsh/vm/fixture'])
    assert json.loads(capsys.readouterr().out) == {'run_id': 'ended-newer'}


def test_default_missing_lookup_keeps_existing_null_response(run_store, capsys):
    cli.main(['runs', 'find', '--session', 'dsh/vm/absent'])
    assert json.loads(capsys.readouterr().out) == {'run_id': None}


def test_open_lookup_by_explicit_id_does_not_substitute_latest_session_run(run_store, capsys):
    run_store('explicit', 'open', '2026-10-28T01:00:00', pclass='redacted_cloud')
    run_store('newer', 'open', '2026-10-28T02:00:00')
    cli.main(['runs', 'find', 'explicit', '--open-only'])
    assert json.loads(capsys.readouterr().out) == {
        'run_id': 'explicit', 'status': 'open', 'privacy_class': 'redacted_cloud'}


def test_open_lookup_by_closed_explicit_id_never_uses_another_open_run(run_store, capsys):
    run_store('explicit', 'ended', '2026-10-28T01:00:00')
    run_store('another', 'open', '2026-10-28T02:00:00')
    cli.main(['runs', 'find', 'explicit', '--open-only'])
    assert json.loads(capsys.readouterr().out) == {'run_id': None, 'status': None, 'privacy_class': None}


def test_routing_command_reads_stdin_and_publishes_only_route_attestation_fields(monkeypatch, capsys):
    calls = []
    spec = {'applied': True, 'via': 'llm', 'model_id': 'model-row', 'model': 'fixture-model',
            'provider': 'fixture-provider', 'observed_model': 'fixture-observed',
            'goal': 'Must not enter the route', 'run_id': 'must-not-override-target'}
    monkeypatch.setattr(cli.sys, 'stdin', io.StringIO(json.dumps(spec)))
    monkeypatch.setattr(runs, 'routing', lambda run_id, decision: calls.append((run_id, decision)))
    cli.main(['runs', 'routing', 'explicit-run'])
    expected = {key: spec[key] for key in ('applied', 'via', 'model_id', 'model', 'provider', 'observed_model')}
    assert calls == [('explicit-run', expected)]
    assert json.loads(capsys.readouterr().out) == {'ok': True}


@pytest.mark.parametrize('arguments,payload', [(['runs', 'routing'], {}),
    (['runs', 'routing', 'explicit-run'], [])])
def test_routing_requires_explicit_target_and_json_object_before_writer(monkeypatch, arguments, payload):
    monkeypatch.setattr(cli.sys, 'stdin', io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(runs, 'routing', lambda *args: pytest.fail('Writer reached on invalid routing input'))
    with pytest.raises(SystemExit) as error:
        cli.main(arguments)
    assert error.value.code == 2
