"""Run model-call accounting is returned as recorded, including unknown costs, without real PG."""
from contextlib import contextmanager
import json
import sqlite3

from walter_memory import runs


def test_show_keeps_usage_and_cost_completeness_of_each_model_call(monkeypatch):
    conn = sqlite3.connect(':memory:')

    def row_factory(cursor, values):
        row = dict(zip([c[0] for c in cursor.description], values))
        if isinstance(row.get('usage'), str):
            row['usage'] = json.loads(row['usage'])
        return row

    conn.row_factory = row_factory
    for schema in ('runs', 'models', 'information_schema'):
        conn.execute(f"attach database ':memory:' as {schema}")
    conn.execute('create table runs.runs (run_id text, parent_run_id text, status text, goal text)')
    conn.execute('create table runs.tasks (run_id text, started_at text)')
    conn.execute('create table runs.links (run_id text, kind text, ref text, at text)')
    conn.execute('create table information_schema.columns (table_schema text, table_name text, column_name text)')
    conn.execute("insert into information_schema.columns values ('models', 'exec_log', 'run_id')")
    conn.execute('''create table models.exec_log (run_id text, at text, task text, model_id text,
        provider text, ok boolean, seconds real, cost_usd real, task_id text, usage text, cost_status text)''')
    conn.execute("insert into runs.runs values ('fixture-run', null, 'open', 'Fixture')")
    conn.execute('insert into models.exec_log values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        ('fixture-run', '2026-10-28T00:00:00', 'general', 'fixture-model', 'fixture-provider', True, 1.0,
         None, None, json.dumps({'input_tokens': 12, 'output_tokens': 4}), 'unknown'))
    conn.execute('insert into models.exec_log values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        ('fixture-run', '2026-10-28T00:00:01', 'coding', 'fixture-model', 'fixture-provider', True, 2.0,
         0.12, 'fixture-task', json.dumps({'input_tokens': 25, 'output_tokens': 8}), 'reported'))

    class Connection:
        def execute(self, sql, args=()):
            return conn.execute(sql.replace('%s', '?'), args)

    @contextmanager
    def connect():
        yield Connection()

    monkeypatch.setattr(runs, 'connect', connect)
    try:
        calls = runs.show('fixture-run')['model_calls']
        assert calls[0]['cost_usd'] is None and calls[0]['cost_status'] == 'unknown'
        assert calls[0]['usage'] == {'input_tokens': 12, 'output_tokens': 4}
        assert calls[1]['cost_usd'] == 0.12 and calls[1]['cost_status'] == 'reported'
        assert calls[1]['usage'] == {'input_tokens': 25, 'output_tokens': 8}
    finally:
        conn.close()
