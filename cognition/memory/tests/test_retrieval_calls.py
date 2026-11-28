"""llm.retrieval: privacy and budget refusals before any request; rerank through the gateway; embeddings refused
explicitly (walter-llm has no embeddings endpoint, SOCLE A6)."""
import pytest
from walter_memory import llm


@pytest.fixture
def guard(monkeypatch):
    logs, calls = [], []
    monkeypatch.setattr(llm, '_log', lambda **kw: logs.append(kw))
    monkeypatch.setattr(llm, 'budget_status', lambda b: None)
    monkeypatch.setattr(llm, '_gateway_token', lambda: 'memory-token')

    class Response:
        status_code, headers = 200, {}

        def json(self):
            return {'results': [{'index': 0, 'relevance_score': 1.0}], 'model': 'vendor/reranker',
                    'provider': 'openrouter', 'usage': {'total_tokens': 3}, 'cost_usd': 0}
    monkeypatch.setattr(llm.httpx, 'post', lambda *a, **kw: (calls.append((a, kw)) or Response()))
    return logs, calls


def test_local_only_never_sends(guard):
    logs, calls = guard
    with pytest.raises(llm.PrivacyRefused):
        llm.retrieval('rerank', processor='test', privacy_class='local_only', payload={'query': 'q', 'documents': ['private']})
    assert not calls and logs[-1]['status'] == 'refused_privacy'


def test_secret_never_sends(guard):
    logs, calls = guard
    with pytest.raises(llm.PrivacyRefused):
        llm.retrieval('rerank', processor='test', privacy_class='cloud_allowed',
                      payload={'query': 'q', 'documents': ['password: abcdefgh']})
    assert not calls


def test_recursive_redaction_and_gateway_rerank(guard):
    logs, calls = guard
    llm.retrieval('rerank', processor='test', privacy_class='redacted_cloud', names=['Alice'], model='vendor/reranker',
                  payload={'query': 'q', 'documents': ['Alice mail alice@example.invalid']})
    (args, kw), = calls
    body = kw['json']
    assert args[0].endswith('/v1/rerank') and kw['headers'] == {'Authorization': 'Bearer memory-token'}
    assert 'Alice' not in str(body) and 'alice@example.invalid' not in str(body)
    assert body['model'] == 'vendor/reranker' and logs[-1]['status'] == 'ok'


def test_monthly_budget_is_obeyed(guard, monkeypatch):
    logs, calls = guard
    monkeypatch.setattr(llm, 'budget_status', lambda b: {'hard_stop': True, 'spent_usd': 10, 'limit_usd': 10})
    with pytest.raises(llm.BudgetExceeded):
        llm.retrieval('rerank', processor='test', privacy_class='cloud_allowed', payload={'query': 'q', 'documents': ['d']})
    assert not calls


def test_paid_floor_travels_to_the_gateway(guard):
    logs, calls = guard
    llm.retrieval('rerank', processor='test', privacy_class='cloud_allowed', payload={'query': 'q', 'documents': ['d']})
    assert calls[0][1]['json']['paid_floor_usd'] == llm.ACCOUNT_FLOOR_USD['backfill']


def test_embeddings_are_refused_explicitly(guard):
    logs, calls = guard
    with pytest.raises(llm.GatewayError, match='no embeddings endpoint'):
        llm.retrieval('embeddings', processor='test', privacy_class='cloud_allowed', payload={'input': ['text']})
    assert not calls


def test_invalid_operation(guard):
    with pytest.raises(ValueError):
        llm.retrieval('chat/completions', processor='test', privacy_class='cloud_allowed', payload={})
