import importlib.util,pathlib


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
