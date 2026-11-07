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

def _autopilot():
    spec=importlib.util.spec_from_file_location('autopilot',pathlib.Path(__file__).resolve().parents[1]/'ops/memory_autopilot.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def _report(**checks):
    base={'postgres':{'running':True},'systemd':[{'unit':'walter-memory-gateway','active':True}],
          'walter_memory':{'report':{'status':'ok'}},
          'recall_probes':{'ok':True,'ok_count':3,'total':3,'avg_ms':500,'probes':[]}}
    base.update(checks);return {'checks':base}


def test_autopilot_scores_walter_memory_health():
    m=_autopilot()
    assert m.evaluate(_report())['severity']=='ok'
    out=m.evaluate(_report(walter_memory={'report':{'status':'problems','problems':['queue dead']}}))
    assert out['severity']=='warning' and any('queue dead' in x for x in out['warnings'])
    out=m.evaluate(_report(systemd=[{'unit':'walter-memory-gateway','active':False}],
                           recall_probes={'ok':False,'ok_count':0,'total':3,'avg_ms':None,'probes':[]}))
    assert out['severity']=='error' and out['score']<50
    assert any('walter-memory-gateway' in x for x in out['errors']) and any('recall' in x for x in out['errors'])
    leak={'query':'q','secret_leak_detected':True}
    out=m.evaluate(_report(recall_probes={'ok':True,'ok_count':3,'total':3,'avg_ms':1,'probes':[leak]}))
    assert out['severity']=='error' and any('secret' in x for x in out['errors'])
