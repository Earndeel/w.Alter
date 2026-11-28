"""walter_memory.health — model-call error rate per processor and decisions by fallback (SOCLE A8). Pure functions:
no database needed."""
from walter_memory import health

CFG = {'window_min': 30, 'min_calls': 5, 'error_ratio': 0.5}


def test_failing_processor_is_an_error_with_masked_dominant_cause():
    rows = [{'processor': 'triage', 'calls': 166, 'failed': 162,
             'dominant': 'RuntimeError: key sk-abcdefghijklmnopqrstuvwxyz012345 rejected at https://api.x.io/v1?key=zz '
                         'reading /user/Lucas/bootstrap/secret.env token=hunter22'},
            {'processor': 'views', 'calls': 25, 'failed': 0, 'dominant': None}]
    out = health.model_call_problems(rows, CFG)
    assert len(out) == 1 and out[0].startswith('model_calls:triage:0.98 — 162/166')
    assert 'sk-abc' not in out[0] and 'https://' not in out[0] and '/user/Lucas' not in out[0]
    assert health.severity(out[0]) == 'error'


def test_thresholds_min_calls_and_ratio():
    assert health.model_call_problems([{'processor': 'p', 'calls': 4, 'failed': 4}], CFG) == []     # too few calls
    assert health.model_call_problems([{'processor': 'p', 'calls': 10, 'failed': 5}], CFG) == []    # 50 % is not above
    assert health.model_call_problems([{'processor': 'p', 'calls': 10, 'failed': 6}], CFG)
    assert health.model_call_problems([{'processor': 'p', 'calls': 0, 'failed': 0}], CFG) == []


def test_mask_error_secrets_and_length():
    t = health.mask_error('Authorization: Bearer abcdefghijklmnop1234567890 at /root/.hermes/.env ' + 'x' * 200)
    assert 'abcdefghijklmnop' not in t and '/root/.hermes' not in t and len(t) <= 80
    assert health.mask_error(None) == ''


def test_triage_fallback_decisions_are_counted():
    assert health.triage_problems(4, 100) == []
    p = health.triage_problems(145, 145)
    assert p and p[0].startswith('triage: 145/145') and health.severity(p[0]) == 'warning'


def test_settings_defaults():
    s = health.settings()
    assert s['model_calls']['min_calls'] >= 1 and 0 < s['model_calls']['error_ratio'] < 1
