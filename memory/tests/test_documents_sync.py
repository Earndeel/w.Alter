"""Exercise the complete documents pipeline with real temp files and an in-memory SQL boundary.

No PostgreSQL, model, network or instance data is used. Parsing, classification, canonical recording,
retraction and canonical read checks remain the production code; only storage and instance discovery differ.
"""
from __future__ import annotations

from copy import deepcopy
import json
import shlex
import uuid

import pytest

from walter_memory import db, documents, events, ingestion, privacy, read_policy, types


class Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchall(self):
        return deepcopy(self.rows)

    def fetchone(self):
        return deepcopy(self.rows[0]) if self.rows else None


class Cursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, args=()):
        self.result = self.conn.execute(sql, args)
        return self

    def fetchone(self):
        return self.result.fetchone()


class MemorySQL:
    """Small transactional store implementing the SQL boundary, never documents' business decisions."""
    def __init__(self):
        self.items, self.events, self.keys, self.chunks, self.checkpoints = {}, {}, {}, {}, {}
        self.successes = 0
        self.source_default = 'cloud_allowed'
        self.policies = []
        self.seed = [x for x in json.loads(types.SEED.read_text())
                     if x['name'] in ('document.section', 'event.retracted')]

    def __enter__(self):
        self.before = deepcopy((self.items, self.events, self.keys, self.chunks, self.checkpoints, self.successes))
        return self

    def __exit__(self, error, *_):
        if error:
            self.items, self.events, self.keys, self.chunks, self.checkpoints, self.successes = self.before
        return False

    def cursor(self):
        return Cursor(self)

    def execute(self, sql, args=()):
        sql = ' '.join(sql.lower().split())
        if 'pg_advisory_xact_lock' in sql or 'ensure_event_partition' in sql:
            return Result()
        if 'from core.event_types' in sql:
            return Result([dict(name=x['name'], version=x.get('version', 1), json_schema=x.get('json_schema', {}))
                           for x in self.seed])
        if 'from privacy.policies' in sql:
            return Result(self.policies)
        if 'from core.sources' in sql:
            return Result([{'source': 'documents', 'privacy_default': self.source_default}])
        if sql.startswith('with k as'):
            key = args['source'], args['source_id'], args['event_type']
            if key in self.keys:
                return Result()
            eid = args['event_id']
            row = {**args, 'payload': json.loads(args['payload'])}
            self.keys[key], self.events[eid] = eid, row
            return Result([{'event_id': eid}])
        if 'from core.event_keys' in sql:
            if 'where source =' in sql:
                eid = self.keys.get((args[0], args[1], 'document.section'))
                return Result([{'event_id': eid}] if eid else [])
            return Result([dict(event_id=eid, occurred_at=self.events[eid]['occurred_at'])
                           for eid in args[0] if eid in self.events])
        if sql.startswith('select') and 'from core.derived_items' in sql:
            rows = list(self.items.values())
            if 'where item_id = any' in sql:
                rows = [r for r in rows if r['item_id'] in args[0]]
            elif "status = 'derived'" in sql:
                rows = [r for r in rows if r['status'] == 'derived']
            return Result(rows)
        if sql.startswith('insert into core.derived_items'):
            kind, body, meta, processor, version, ids, refs, date, pclass = args
            item_id = str(uuid.uuid4())
            attr = json.loads(meta)
            self.items[item_id] = dict(item_id=item_id, id=item_id, kind=kind, content=body, attributes=attr,
                k=attr['doc_key'], sha=attr['sha'], source=attr['source'], path=attr['path'],
                revision=attr.get('revision'), status='derived', source_event_ids=list(ids), source_object_ids=[],
                privacy_class=pclass, quarantined=False)
            self.chunks[item_id] = dict(hidden=False, privacy_class=pclass)
            return Result()
        if sql.startswith('update core.derived_items set status'):
            self.items[args[1]]['status'] = 'retracted'
            self.items[args[1]]['attributes']['retracted_reason'] = args[0]
            return Result()
        if sql.startswith('update search.chunks set hidden'):
            self.chunks[args[1]].update(hidden=True, hidden_reason=args[0])
            return Result()
        if sql.startswith('update core.events set privacy_class'):
            for eid in args[1]:
                if self.events[eid]['privacy_class'] in args[2]:
                    self.events[eid]['privacy_class'] = args[0]
            return Result()
        if sql.startswith('update core.derived_items set privacy_class'):
            if self.items[args[1]]['privacy_class'] in args[2]:
                self.items[args[1]]['privacy_class'] = args[0]
            return Result()
        if sql.startswith('update search.chunks set privacy_class'):
            if self.chunks[args[1]]['privacy_class'] in args[2]:
                self.chunks[args[1]]['privacy_class'] = args[0]
            return Result()
        if "select payload->>'target_event_id'" in sql:
            return Result([{'t': e['payload']['target_event_id']} for e in self.events.values()
                           if e['event_type'] == 'event.retracted'])
        if sql.startswith('select') and 'from core.events' in sql:
            return Result([dict(id=eid, **self.events[eid]) for eid in args[1] if eid in self.events])
        if 'select cursor from ingestion.checkpoints' in sql:
            key = args[0], args[1]
            return Result([{'cursor': self.checkpoints[key]}] if key in self.checkpoints else [])
        if sql.startswith('insert into ingestion.checkpoints'):
            self.checkpoints[(args[0], args[1])] = json.loads(args[2])
            return Result()
        if sql.startswith('update ingestion.connectors set last_success_at'):
            self.successes += 1
            return Result()
        raise AssertionError(f'Unexpected SQL in offline store: {sql}')

    def active(self):
        return [r for r in self.items.values() if r['status'] == 'derived']

    def cloud_rows(self, monkeypatch):
        # Each assertion is a fresh read, independent of the process-wide 60-second retraction cache.
        monkeypatch.setattr(read_policy, '_retracted', (0.0, frozenset()))
        rows = [dict(kind='derived', ref_id=r['item_id'], text=r['content'], privacy_class=r['privacy_class'])
                for r in self.active()]
        return read_policy.filter_cloud_rows(self, rows)


@pytest.fixture
def source(tmp_path, monkeypatch):
    conn = MemorySQL()
    config = tmp_path / 'documents.toml'
    doc = tmp_path / 'decisions.md'
    doc.write_text('## Decision\nVersion A.\n')
    config.write_text(f'[[source]]\nname = "decisions"\npath = {json.dumps(str(doc))}\n')
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    command = bindir / 'walter'
    command.write_text('#!/bin/sh\nprintf \'%s\\n\' ' + shlex.quote(str(config)) + '\n')
    command.chmod(0o700)
    monkeypatch.setenv('PATH', str(bindir))
    monkeypatch.setattr(documents, 'connect', lambda: conn)
    monkeypatch.setattr(types, 'connection', lambda: conn)
    monkeypatch.setattr(ingestion, 'connection', lambda: conn)
    monkeypatch.setattr(types, '_cache', {})
    monkeypatch.setattr(types, '_loaded_at', 0)
    monkeypatch.setattr(events, '_partitions', set())
    monkeypatch.setattr(privacy, '_policies', [])
    monkeypatch.setattr(privacy, '_source_defaults', {})
    monkeypatch.setattr(privacy, '_policies_at', 0)
    monkeypatch.setattr(db, 'connect', lambda: pytest.fail('Live PostgreSQL forbidden in document tests'))
    monkeypatch.setattr(db, 'pool', lambda: pytest.fail('Live PostgreSQL forbidden in document tests'))
    return conn, config, doc, command


def test_unreadable_config_preserves_existing_knowledge(source, monkeypatch):
    conn, config, _, _ = source
    assert documents.sync()['new'] == 1
    previous = deepcopy(conn.items)
    config.write_text('[[ invalid TOML')
    try:
        documents.sync()
    except (ValueError, RuntimeError, OSError):
        pass
    assert conn.items == previous
    assert len(conn.cloud_rows(monkeypatch)) == 1


def test_missing_file_preserves_existing_knowledge_until_explicit_removal(source):
    conn, config, doc, _ = source
    documents.sync()
    previous = deepcopy(conn.items)
    doc.unlink()
    try:
        documents.sync()
    except (ValueError, RuntimeError, OSError):
        pass
    assert conn.items == previous
    config.write_text('source = []\n')
    assert documents.sync()['removed'] == 1
    assert not conn.active()


def test_missing_glob_member_requires_explicit_exclusion(source):
    conn, config, doc, _ = source
    config.write_text(f'[[source]]\nname = "decisions"\npath = {json.dumps(str(doc.parent / "*.md"))}\n')
    documents.sync()
    previous = deepcopy(conn.items)
    doc.unlink()
    try:
        documents.sync()
    except (ValueError, RuntimeError, OSError):
        pass
    assert conn.items == previous
    with config.open('a') as stream:
        stream.write('exclude = ["decisions.md"]\n')
    assert documents.sync()['removed'] == 1
    assert not conn.active()


def test_reverting_text_creates_readable_new_occurrence_without_undoing_retractions(source, monkeypatch):
    conn, _, doc, _ = source
    documents.sync()
    first_id = conn.active()[0]['source_event_ids'][0]
    doc.write_text('## Decision\nVersion B.\n')
    assert documents.sync()['changed'] == 1
    second_id = conn.active()[0]['source_event_ids'][0]
    doc.write_text('## Decision\nVersion A.\n')
    assert documents.sync()['changed'] == 1
    assert [r['text'] for r in conn.cloud_rows(monkeypatch)] == ['## Decision\nVersion A.']
    third_id = conn.active()[0]['source_event_ids'][0]
    assert len({first_id, second_id, third_id}) == 3
    retired = {e['payload']['target_event_id'] for e in conn.events.values() if e['event_type'] == 'event.retracted'}
    assert retired == {first_id, second_id}
    before = deepcopy((conn.items, conn.events))
    assert documents.sync()['unchanged'] == 1
    assert (conn.items, conn.events) == before


def test_config_only_privacy_tightening_hides_identical_content_everywhere(source, monkeypatch):
    conn, config, _, _ = source
    assert documents.sync_if_changed()['new'] == 1
    before = conn.active()[0]
    with config.open('a') as stream:
        stream.write('privacy = "local_only"\n')
    documents.sync_if_changed()
    assert conn.active()[0]['privacy_class'] == 'local_only'
    assert conn.events[before['source_event_ids'][0]]['privacy_class'] == 'local_only'
    assert conn.items[before['item_id']]['privacy_class'] == 'local_only'
    assert conn.chunks[before['item_id']]['privacy_class'] == 'local_only'
    assert not conn.cloud_rows(monkeypatch)
    # Loosening config cannot declassify an already restricted version, even after reintroduction.
    config.write_text(config.read_text().replace('local_only', 'cloud_allowed'))
    documents.sync_if_changed()
    assert conn.active()[0]['privacy_class'] == 'local_only'


def test_sync_repairs_current_row_whose_existing_provenance_was_already_retracted(source, monkeypatch):
    conn, _, _, _ = source
    documents.sync()
    old_event = conn.active()[0]['source_event_ids'][0]
    events.record_events([dict(event_type='event.retracted', source='walter', source_id=f'retract:{old_event}',
        occurred_at=conn.events[old_event]['occurred_at'], privacy_class='cloud_allowed',
        payload={'target_event_id': old_event, 'reason': 'legacy version superseded'})], conn=conn)
    assert not conn.cloud_rows(monkeypatch)
    documents.sync()
    assert len(conn.cloud_rows(monkeypatch)) == 1
    assert conn.active()[0]['source_event_ids'] != [old_event]


@pytest.mark.parametrize('suffix', ['privacy = "unclassified"', 'split = "guess"', 'exclude = "decisions.md"',
    '\n[[source]]\nname = "decisions"\npath = "/another-record.md"'])
def test_invalid_source_contract_cannot_mutate_knowledge(source, suffix):
    conn, config, doc, _ = source
    documents.sync()
    previous = deepcopy((conn.items, conn.events))
    with config.open('a') as stream:
        stream.write(suffix.replace('/another-record.md', str(doc)) + '\n')
    with pytest.raises(documents.DocumentsUnavailable):
        documents.sync()
    assert (conn.items, conn.events) == previous


@pytest.mark.parametrize('location', ['metadata', 'after-truncation'])
def test_secret_section_is_rejected_before_truncation_and_metadata_storage(source, location):
    conn, config, doc, _ = source
    if location == 'metadata':
        doc.write_text('---\ndescription: "password: invented-test-placeholder"\n---\nPublic-looking body.\n')
        with config.open('a') as stream:
            stream.write('split = "file"\n')
    else:
        doc.write_text('## Decision\n' + 'a' * documents.MAX_CHARS + '\npassword: invented-test-placeholder\n')
    stats = documents.sync()
    assert stats['skipped_secret'] == 1 and stats['new'] == 0
    assert not conn.items and not conn.events


def test_restricted_projection_also_tightens_weaker_canonical_evidence(source):
    conn, _, _, _ = source
    documents.sync()
    old = conn.active()[0]
    conn.items[old['item_id']]['privacy_class'] = 'local_only'
    conn.chunks[old['item_id']]['privacy_class'] = 'local_only'
    documents.sync()
    assert conn.events[old['source_event_ids'][0]]['privacy_class'] == 'local_only'


@pytest.mark.parametrize('rule', ['source-default', 'event-policy'])
def test_document_configuration_cannot_loosen_memory_source_policy(source, monkeypatch, rule):
    conn, _, _, _ = source
    if rule == 'source-default':
        conn.source_default = 'local_only'
    else:
        conn.policies = [{'name': 'restricted-documents', 'match': {'event_type': 'document.section'},
                          'class': 'redacted_cloud'}]
    documents.sync()
    expected = 'local_only' if rule == 'source-default' else 'redacted_cloud'
    assert conn.active()[0]['privacy_class'] == expected
    assert not conn.cloud_rows(monkeypatch)


def test_source_reintroduction_preserves_retractions_and_retry_idempotence(source, monkeypatch):
    conn, config, _, _ = source
    original_config = config.read_text()
    documents.sync_if_changed()
    first = conn.active()[0]['source_event_ids'][0]
    config.write_text('source = []\n')
    assert documents.sync_if_changed()['removed'] == 1
    config.write_text(original_config)
    assert documents.sync_if_changed()['new'] == 1
    assert conn.active()[0]['source_event_ids'] != [first]
    assert len(conn.cloud_rows(monkeypatch)) == 1
    previous = deepcopy((conn.items, conn.events, conn.checkpoints))
    assert documents.sync_if_changed() == {}
    assert (conn.items, conn.events, conn.checkpoints) == previous


@pytest.mark.parametrize('failure', ['configuration', 'file'])
def test_failed_pass_preserves_checkpoint_and_retries_when_available(source, failure):
    conn, config, doc, _ = source
    documents.sync_if_changed()
    previous = deepcopy((conn.items, conn.events, conn.checkpoints, conn.successes))
    original = config.read_text()
    if failure == 'configuration':
        config.write_text('[[ broken TOML')
    else:
        doc.unlink()
    with pytest.raises(documents.DocumentsUnavailable):
        documents.sync_if_changed()
    assert (conn.items, conn.events, conn.checkpoints, conn.successes) == previous
    config.write_text(original)
    doc.write_text('## Decision\nVersion B.\n')
    assert documents.sync_if_changed()['changed'] == 1
    assert conn.active()[0]['content'].endswith('Version B.')


def test_dry_run_changes_no_canonical_projection_or_chunk(source):
    conn, config, doc, _ = source
    documents.sync()
    previous = deepcopy((conn.items, conn.events, conn.chunks))
    with config.open('a') as stream:
        stream.write('privacy = "local_only"\n')
    assert documents.sync(dry_run=True)['changed'] == 1
    assert (conn.items, conn.events, conn.chunks) == previous
    doc.write_text('## Decision\nVersion B.\n')
    assert documents.sync(dry_run=True)['changed'] == 1
    assert (conn.items, conn.events, conn.chunks) == previous


def test_storage_failure_rolls_back_canonical_event_and_current_projection(source, monkeypatch):
    conn, _, doc, _ = source
    documents.sync()
    previous = deepcopy((conn.items, conn.events, conn.keys, conn.chunks))
    doc.write_text('## Decision\nVersion B.\n')
    execute = conn.execute

    def failed_insert(sql, args=()):
        if 'insert into core.derived_items' in sql:
            raise OSError('injected offline storage failure')
        return execute(sql, args)

    monkeypatch.setattr(conn, 'execute', failed_insert)
    with pytest.raises(OSError):
        documents.sync()
    assert (conn.items, conn.events, conn.keys, conn.chunks) == previous
    monkeypatch.setattr(conn, 'execute', execute)
    assert documents.sync()['changed'] == 1
    assert len(conn.cloud_rows(monkeypatch)) == 1
