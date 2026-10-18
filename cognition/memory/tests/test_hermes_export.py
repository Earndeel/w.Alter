import io
import json
import sqlite3
from datetime import date, datetime, timezone

import pytest
import zstandard

from walter_memory import hermes_export as E


def fixture_db():
    db = sqlite3.connect(":memory:"); db.row_factory = sqlite3.Row
    db.execute("create table sessions(id text,started_at real,model text)")
    db.execute("create table messages(id integer primary key,session_id text,timestamp real,content text,extra text)")
    stamp = lambda d: datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp()
    db.execute("insert into sessions values('s',?,'test-model')", (stamp('2026-10-01'),))
    for i, day in enumerate(('2026-10-01', '2026-10-02', '2026-10-04'), 1):
        db.execute("insert into messages values(?,'s',?,?,?)", (i, stamp(day), 'synthetic only', 'all columns'))
    db.commit(); return db


class Store:
    def __init__(self):
        self.cursor = None; self.files = {}; self.fail = None; self.modes = []
    def last_day(self): return self.cursor
    def advance(self, day): self.cursor = day
    def reuse(self, profile, day):
        if (profile, day) not in self.files: return False
        self.advance(day.isoformat()); return True
    def save(self, path, profile, day, counts):
        if self.fail == day: raise OSError('simulated interruption')
        self.modes.append(path.stat().st_mode & 0o777)
        with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(path.read_bytes())) as reader:
            self.files[profile, day] = [json.loads(line) for line in reader.read().splitlines()]
        self.advance(day.isoformat())


def test_bound_resume_and_idempotence_all_columns_and_prior_session(tmp_path):
    db = fixture_db(); store = Store()
    first = E.export_profile(db, 'wild', store, today=date(2026,10,4), max_days=1, temp_root=str(tmp_path))
    assert first['remaining_days'] == 1 and first['through'] == '2026-10-01'
    second = E.export_profile(db, 'wild', store, today=date(2026,10,4), temp_root=str(tmp_path))
    assert second['through'] == '2026-10-03' and second['messages'] == 1
    rows = store.files['wild', date(2026,10,2)]
    assert rows[0]['profile'] == 'wild' and rows[1]['kind'] == 'session'
    assert rows[2]['extra'] == 'all columns'
    assert E.export_profile(db, 'wild', store, today=date(2026,10,4))['exported_days'] == 0
    assert store.modes == [0o600, 0o600] and not list(tmp_path.iterdir())


def test_failed_day_does_not_advance_and_retry_reuses_archive(tmp_path):
    db=fixture_db(); store=Store(); store.fail=date(2026,10,2)
    with pytest.raises(OSError):
        E.export_profile(db,'main',store,today=date(2026,10,4),temp_root=str(tmp_path))
    assert store.cursor=='2026-10-01' and len(store.files)==1
    assert not list(tmp_path.iterdir())
    store.fail=None
    # Simulate an old catalogue object whose checkpoint did not advance.
    store.cursor=None
    result=E.export_profile(db,'main',store,today=date(2026,10,4))
    assert result['reused_days']==1 and len(store.files)==2


def test_empty_profile_and_today_are_not_exported():
    db=fixture_db(); db.execute('delete from messages'); db.execute('delete from sessions'); db.commit()
    store=Store()
    assert E.export_profile(db,'empty',store,today=date(2026,10,4))['through']=='2026-10-03'
    assert not store.files


def test_deadline_leaves_no_partial_file_or_cursor(tmp_path,monkeypatch):
    db=fixture_db(); store=Store(); ticks=iter([0,0,2])
    monkeypatch.setattr(E.time,'monotonic',lambda: next(ticks))
    with pytest.raises(E.ExportDeadline):
        E.export_profile(db,'wild',store,today=date(2026,10,4),max_seconds=1,temp_root=str(tmp_path))
    assert store.cursor is None and not list(tmp_path.iterdir())


def test_live_storage_enforces_private_zone_before_head(monkeypatch):
    from walter_memory import objects
    monkeypatch.setattr(objects,'s3',lambda: pytest.fail('storage accessed before privacy check'))
    store=E.VaultExports('wild')
    for cls,zone,purged in [('cloud_allowed','secure',None),('local_only','clear',None),('local_only','secure','date')]:
        with pytest.raises(RuntimeError,match='storage policy'):
            store._verify({'privacy_class':cls,'storage_zone':zone,'purged_at':purged})


def test_store_commit_has_explicit_profile_and_privacy(monkeypatch,tmp_path):
    from contextlib import nullcontext
    from walter_memory import objects, ingestion
    calls=[]; store=E.VaultExports('wild')
    class Connection:
        def transaction(self): return nullcontext()
    store.conn=Connection(); store._verify=lambda row: calls.append(('verified',row))
    monkeypatch.setattr(objects,'put_object',lambda *a,**kw: calls.append(('put',kw)) or {'object':'fake'})
    monkeypatch.setattr(ingestion,'set_checkpoint',lambda *a,**kw: calls.append(('cursor',a)))
    store.save(tmp_path/'fake','wild',date(2026,10,2),{'messages':2,'sessions':1})
    assert [c[0] for c in calls]==['put','verified','cursor']
    assert calls[0][1]['privacy_class']=='local_only' and calls[0][1]['zone']=='secure'
    assert calls[0][1]['source_ref']['profile']=='wild'
    assert calls[-1][1][0]=='hermes:wild'


def test_default_and_profile_named_main_have_distinct_identity(tmp_path):
    assert E.VaultExports('main',True).connector=='hermes'
    assert E.VaultExports('main',False).connector=='hermes:main'
    db=fixture_db(); a=tmp_path/'a.zst'; b=tmp_path/'b.zst'
    E.write_day(db,a,'main',date(2026,10,1),float('inf'),True)
    E.write_day(db,b,'main',date(2026,10,1),float('inf'),False)
    assert a.read_bytes()!=b.read_bytes()


def test_readonly_forced_even_for_bare_path_or_rw_uri(tmp_path,monkeypatch):
    source=tmp_path/'state.db'; db=sqlite3.connect(source); db.execute('create table example(x)'); db.close()
    class ContextStore:
        def __init__(self,*a): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
    monkeypatch.setattr(E,'VaultExports',ContextStore)
    def probe(db,*a,**kw):
        with pytest.raises(sqlite3.OperationalError,match='readonly'):
            db.execute('insert into example values(1)')
        return {'readonly':True}
    monkeypatch.setattr(E,'export_profile',probe)
    assert E.run(str(source),'wild')['readonly']
    assert E.run(source.as_uri()+'?mode=rw','wild')['readonly']


def test_invalid_null_dates_and_future_cursor():
    db=fixture_db()
    db.execute("insert into messages values(10,'s',NULL,'test','test')")
    db.execute("insert into messages values(11,'s','nonsense','test','test')")
    db.commit(); store=Store()
    with pytest.raises(ValueError,match='invalid timestamps'):
        E.export_profile(db,'wild',store,today=date(2026,10,4))
    assert store.cursor is None
    db.execute('delete from messages where id>=10');db.commit()
    store.cursor='2026-10-20'
    assert E.export_profile(db,'wild',store,today=date(2026,10,4))['through']=='2026-10-20'


def test_export_only_dispatches_every_profile_without_canonical_ingestion(tmp_path,monkeypatch):
    import importlib.util
    from pathlib import Path
    from walter_memory import ingestion
    spec=importlib.util.spec_from_file_location('export_connector',Path(__file__).parents[1]/'connectors/hermes.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    for name in ('wild','main'):
        directory=tmp_path/name; directory.mkdir();(directory/'state.db').touch()
    monkeypatch.setattr(mod,'PROFILES_DIR',str(tmp_path))
    monkeypatch.setattr(mod,'run_one',lambda *a: pytest.fail('canonical ingestion during raw export'))
    monkeypatch.setattr(ingestion,'register_connector',lambda *a: None)
    monkeypatch.setattr(ingestion,'mark_success',lambda *a: None)
    called=[]
    monkeypatch.setattr(E,'run',lambda db,profile,**kw: called.append((profile,kw['default_profile'])) or {'remaining_days':0})
    monkeypatch.setattr(mod.sys,'argv',['hermes.py','--export-only','--all-profiles'])
    mod.main()
    assert called==[('main',True),('main',False),('wild',False)]
