import contextlib,importlib.util,json,pathlib
import pytest
from walter_memory import hygiene as H

class FakeConnection:
    def __init__(self):self.calls=[];self.rows=[]
    def execute(self,sql,args=()):
        self.calls.append((sql,args))
        if 'count(*)' in sql:self.rows=[{'n':2}]
        elif 'select id,tags' in sql:self.rows=[{'id':'id1','tags':['existing']},{'id':'id2','tags':[]}]
        elif 'returning id' in sql:self.rows=[{'id':'id1'},{'id':'id2'}]
        else:self.rows=[]
        return self
    def fetchone(self):return self.rows[0]
    def fetchall(self):return self.rows

def test_hygiene_is_dry_by_default_and_limits_scope(monkeypatch):
    c=FakeConnection()
    @contextlib.contextmanager
    def connection():yield c
    monkeypatch.setattr(H,'connection',connection)
    result=H.quarantine();assert result['quarantined']==0
    assert len(c.calls)==1 and "bank_id='walter'" in c.calls[0][0] and 'quarantine:noise' in c.calls[0][0]
    with pytest.raises(ValueError):H.quarantine(limit=1001)

def test_apply_saves_old_tags_and_quarantines_without_delete(monkeypatch,tmp_path):
    c=FakeConnection()
    @contextlib.contextmanager
    def connection():yield c
    monkeypatch.setattr(H,'connection',connection)
    out=H.quarantine(apply=True,backup_dir=tmp_path)
    assert out['quarantined']==2
    backup=pathlib.Path(out['snapshot']);assert backup.stat().st_mode & 0o777==0o600
    assert json.loads(backup.read_text())['before'][0]['tags']==['existing']
    assert not any('delete ' in sql.lower() for sql,_ in c.calls)
    assert any('update public.memory_units' in sql and args[0]=='hygiene:ephemeral' for sql,args in c.calls)

def test_autopilot_reports_failed_cleanup_and_business_health():
    spec=importlib.util.spec_from_file_location('autopilot',pathlib.Path('/root/.hermes/scripts/memory_autopilot.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    r={'checks':{'postgres':{'metrics':{'schemas_with_pending_work_exists':1}},'walter_memory':{'report':{'status':'problems','problems':['queue dead']}}},
       'autofix':{'safe':{'cleanup':{'command':{'ok':False},'report':{'summary':{'ok':False}}}}}}
    out=m.evaluate(r)
    assert out['severity']=='error' and out['score']<100
    assert any('cleanup' in x for x in out['errors']) and any('queue dead' in x for x in out['warnings'])
