"""The bench cleans up failed children without inventing a successful Stop."""
import json
import subprocess
import tempfile
from types import SimpleNamespace

import pytest
from test_scenario_regressions import S

SID = 'session-11111111-1111-4111-8111-111111111111'
RUN = '22222222-2222-4222-8222-222222222222'


@pytest.mark.parametrize('timeout', [False, True])
def test_failure_closes_only_its_exact_run_failed(monkeypatch, tmp_path, timeout):
    calls = []
    partial = json.dumps({'type': 'session', 'sessionId': SID}) + '\n'
    def execute(argv, **kwargs):
        calls.append((argv, kwargs.get('input')))
        if '--profile' in argv:
            if timeout:
                raise subprocess.TimeoutExpired(argv, 1, output=partial.encode())
            return SimpleNamespace(returncode=1, stdout=partial, stderr='private diagnostics withheld')
        return SimpleNamespace(returncode=0, stdout=json.dumps({'run_id': RUN}), stderr='')
    monkeypatch.setattr(S.subprocess, 'run', execute)
    monkeypatch.setattr(S.time, 'sleep', lambda n: None)
    monkeypatch.setattr(tempfile, 'mkdtemp', lambda **kw: str(tmp_path))
    result = S.step_harness({'prompt': 'fixture', 'timeout': 1}, {})
    assert result['ok'] is False and result['run_id'] == RUN
    ends = [call for call in calls if call[0][:3] == ['walter-memory', 'runs', 'end']]
    assert len(ends) == 1 and ends[0][0][-1] == RUN
    assert json.loads(ends[0][1]) == {'status': 'failed'}
    assert 'private diagnostics' not in json.dumps(result)


def test_success_is_not_closed_artificially(monkeypatch, tmp_path):
    calls = []
    def execute(argv, **kwargs):
        calls.append(argv)
        rows = [{'type': 'session', 'sessionId': SID}, {'type': 'final', 'text': 'OK'}]
        return SimpleNamespace(returncode=0, stdout='\n'.join(map(json.dumps, rows)) if '--profile' in argv
                               else json.dumps({'run_id': RUN}), stderr='')
    monkeypatch.setattr(S.subprocess, 'run', execute)
    monkeypatch.setattr(S.time, 'sleep', lambda n: None)
    monkeypatch.setattr(tempfile, 'mkdtemp', lambda **kw: str(tmp_path))
    assert S.step_harness({'prompt': 'fixture'}, {})['ok'] is True
    assert not any(argv[:3] == ['walter-memory', 'runs', 'end'] for argv in calls)
