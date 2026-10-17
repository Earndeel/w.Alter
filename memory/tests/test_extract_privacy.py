"""Exercise the real L3 -> LLM privacy boundary, without DB or network access."""
import contextlib,datetime,json,types,uuid
from walter_memory import extract,llm

def message(cls,text):
    return {'event_id':uuid.uuid4(),'event_type':'message.sent','occurred_at':datetime.datetime.now(datetime.timezone.utc),
            'content':text,'privacy_class':cls}

class Connection:
    def __init__(self,msgs,title=None):self.msgs=msgs;self.title=title;self.inserts=[];self.current=[]
    def execute(self,sql,args=()):
        if 'insert into core.derived_items' in sql:self.inserts.append(args);self.current=[]
        elif 'select event_id' in sql:self.current=self.msgs
        elif 'payload->>' in sql:self.current=[]
        elif 'conversation.started' in sql:self.current=[self.title] if self.title else []
        else:raise AssertionError(sql)
        return self
    def fetchall(self):return self.current
    def fetchone(self):return self.current[0] if self.current else None

def setup(monkeypatch,msgs,title=None):
    c=Connection(msgs,title)
    @contextlib.contextmanager
    def connect():yield c
    monkeypatch.setattr(extract,'connection',connect)
    monkeypatch.setattr(llm,'budget_status',lambda _: {'hard_stop':True,'spent_usd':0,'limit_usd':10})
    monkeypatch.setattr(llm,'_gateway_token',lambda:'test-credential',raising=False)
    monkeypatch.setattr(llm,'_key',lambda:'test-credential',raising=False)
    monkeypatch.setattr(llm,'account_balance',lambda:100.0)
    monkeypatch.setattr(llm,'_log',lambda **_:None)
    seen=[]
    def post(url,**kw):
        seen.append(kw['json'])
        result={'summary':'A summary','facts':[{'text':'A fact','msgs':[1]}]}
        return types.SimpleNamespace(status_code=200,headers={'x-walter-route':'codex/test-model'},
             json=lambda:{'choices':[{'message':{'content':json.dumps(result)}}],'usage':{'cost':0}})
    monkeypatch.setattr(llm.httpx,'post',post)
    return c,seen

def test_redacted_segment_is_pseudonymised_before_cloud_and_stays_restricted(monkeypatch):
    msgs=[message('cloud_allowed','Bonjour'),message('redacted_cloud','Contact au +33 6 12 34 56 78 ou alice@example.org'),
          message('local_only','PRIVATE_LOCAL_MESSAGE')]
    c,seen=setup(monkeypatch,msgs,{'content':'PRIVATE_TITLE','privacy_class':'local_only'})
    extract.summarize_session('s')
    wire=json.dumps(seen)
    assert 'alice@example.org' not in wire and '+33 6' not in wire and 'PRIVATE_LOCAL_MESSAGE' not in wire
    assert '[EMAIL_1]' in wire and '[PHONE_1]' in wire
    assert len(c.inserts)==2 and all(args[-1]=='redacted_cloud' for args in c.inserts)
    assert all(str(msgs[2]['event_id']) not in str(args[8]) for args in c.inserts)
    assert json.loads(c.inserts[0][2])['title'] is None

def test_cloud_allowed_only_keeps_its_class(monkeypatch):
    c,seen=setup(monkeypatch,[message('cloud_allowed','Projet public')])
    extract.summarize_session('s');assert seen and all(args[-1]=='cloud_allowed' for args in c.inserts)

def test_entirely_local_session_never_calls_model(monkeypatch):
    c,seen=setup(monkeypatch,[message('local_only','PRIVATE')])
    assert extract.summarize_session('s')['segments']==0
    assert not seen and not c.inserts
