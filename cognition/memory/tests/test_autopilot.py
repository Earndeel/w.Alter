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


# SOCLE A8 (2026-11-11): the outage — 409 failed model calls between 07:37 and 11:28 UTC — scored 100/100 twice.
OUTAGE = {'triage': (166, 162), 'episodic.attest': (165, 165), 'walter-context-preflight': (84, 81)}
CAUSE = 'Cloudflare Workers AI credentials missing (CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN)'


def _outage_health():
    from walter_memory import health
    rows = [{'processor': p, 'calls': n, 'failed': f, 'dominant': CAUSE} for p, (n, f) in OUTAGE.items()]
    problems = health.model_call_problems(rows) + health.triage_problems(145, 145)
    return problems


def test_outage_replay_is_an_error_not_a_perfect_score():
    m = _autopilot()
    problems = _outage_health()
    assert sum(f for _, f in OUTAGE.values()) == 408   # + 1 other call in the 409 of system.model_calls
    assert len([p for p in problems if p.startswith('model_calls:')]) == 3
    out = m.evaluate(_report(walter_memory={'report': {'status': 'problems', 'problems': problems}}))
    assert out['severity'] == 'error' and out['score'] < 92 and not out['ok']
    assert any('model_calls:episodic.attest:1.00' in e for e in out['errors'])
    assert any('triage:' in w for w in out['warnings'])


def test_one_failing_processor_alone_drops_below_the_warning_threshold():
    m = _autopilot()
    out = m.evaluate(_report(walter_memory={'report': {'status': 'problems',
                                                       'problems': ['model_calls:triage:0.98 — 162/166 failed']}}))
    assert out['severity'] == 'error' and out['score'] < 92


def test_healthy_memory_still_scores_full():
    m = _autopilot()
    out = m.evaluate(_report())
    assert (out['severity'], out['score'], out['errors']) == ('ok', 100, [])
