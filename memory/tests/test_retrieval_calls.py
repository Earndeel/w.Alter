import pytest
from walter_memory import llm

@pytest.fixture
def guard(monkeypatch):
 logs=[];calls=[]
 monkeypatch.setattr(llm,'_log',lambda **kw:logs.append(kw))
 monkeypatch.setattr(llm,'budget_status',lambda b:None)
 monkeypatch.setattr(llm,'account_balance',lambda:20)
 monkeypatch.setattr(llm,'_key',lambda:'test-key')
 class Response:
  def raise_for_status(self):pass
  def json(self):return {'data':[{'index':0,'embedding':[1,0]}],'usage':{'cost':0}}
 monkeypatch.setattr(llm.httpx,'post',lambda *a,**kw:(calls.append((a,kw)) or Response()))
 return logs,calls

def test_local_only_never_sends(guard):
 logs,calls=guard
 with pytest.raises(llm.PrivacyRefused):llm.retrieval('embeddings',model='x:free',processor='test',privacy_class='local_only',payload={'input':['private']})
 assert not calls and logs[-1]['status']=='refused_privacy'

def test_secret_never_sends(guard):
 logs,calls=guard
 with pytest.raises(llm.PrivacyRefused):llm.retrieval('rerank',model='x:free',processor='test',privacy_class='cloud_allowed',payload={'query':'q','documents':['password: abcdefgh']})
 assert not calls

def test_recursive_redaction(guard):
 logs,calls=guard
 llm.retrieval('embeddings',model='x:free',processor='test',privacy_class='redacted_cloud',names=['Alice'],payload={'input':['Alice mail alice@example.invalid']})
 body=calls[0][1]['json'];assert 'Alice' not in str(body) and 'alice@example.invalid' not in str(body)
 assert body['model']=='x:free' and logs[-1]['status']=='ok'

def test_free_still_obeys_monthly_budget(guard,monkeypatch):
 logs,calls=guard;monkeypatch.setattr(llm,'budget_status',lambda b:{'hard_stop':True,'spent_usd':10,'limit_usd':10})
 with pytest.raises(llm.BudgetExceeded):llm.retrieval('embeddings',model='x:free',processor='test',privacy_class='cloud_allowed',payload={'input':['text']})
 assert not calls

def test_paid_floor(guard,monkeypatch):
 logs,calls=guard;monkeypatch.setattr(llm,'account_balance',lambda:.1)
 with pytest.raises(llm.BudgetExceeded):llm.retrieval('rerank',model='x',processor='test',privacy_class='cloud_allowed',payload={'query':'q','documents':['d']})
 assert not calls

def test_invalid_operation(guard):
 with pytest.raises(ValueError):llm.retrieval('chat/completions',model='x',processor='test',privacy_class='cloud_allowed',payload={})
