"""HTTP gateway request-local correlation and real usage, entirely offline."""
import ast
import asyncio
import hashlib
import json
import re
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import uuid
from datetime import datetime, timezone
import time

import httpx
import pytest
from fastapi import Request

RUN='11111111-1111-4111-8111-111111111111'
SESSION='22222222-2222-4222-8222-222222222222'

def gateway(tmp_path, monkeypatch):
    source=Path(__file__).resolve().parents[1]/'llm'/'gateway.py'
    tree=ast.parse(source.read_text())
    names={'_usage','_number','_telemetry','_uuid','_dsh_session','_correlation','_session_run','_run_metadata','_record_attempt','exact_call','log','build_app',
           'start_completion','_rate_limited','_charge','_price_usd','_priced','test_budget','test_gate','_ledger','_ledger_add','approve_tests',
           'planned_task','exact_task','owner_tasks','rule_answer','_text_parts','_rule_completion','_rule_stream','_rule_routing',
           'route_state','selection_plan','selection_check','log_selection','cost_headers'}
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    agents=tmp_path/'agents.json'
    agents.write_text(json.dumps({hashlib.sha256(b'fixture-token').hexdigest():{'agent':'dsh'}}))
    class Thread:
        def __init__(self,target,**kw):self.target,self.kw=target,kw
        def start(self):
            if self.target.__name__=='<lambda>':self.target()
    ns={'re':re,'EXACT':'exact:','_MODEL_ID':re.compile(r'^[A-Za-z0-9._:/-]{1,120}$'),'json':json,'hashlib':hashlib,'uuid':uuid,'math':math,'datetime':datetime,'timezone':timezone,
        'time':time,'Request':Request,'subprocess':subprocess,'AGENTS':agents,'LOG':tmp_path/'log.jsonl',
        'ROUTER':'walter-router','DEFAULT_TASK':'coding','threading':SimpleNamespace(Thread=Thread),
        'warm':lambda:None,'_install_codex_auth':lambda:None,'chat_tasks':lambda:['coding'],
        'decision':lambda task:{'model_id':'fixture-model','execution':[{'provider':'fixture','model':'fixture-model'}]},
        '_run_metadata':lambda run:{'run_id':run,'status':'open','privacy_class':'cloud_allowed'},
        'litellm_target':lambda route:{'model':'fixture-model'},'as_json':lambda x:x,'json_instruction':lambda x:'JSON',
        'PAID':{'kie','openrouter','arnict'},'QUOTA_SWITCH':90.0,'RATE_LIMIT_WAITS':(0,0),'Path':Path,'os':os,'_telegram':lambda *a:None,
        'TEST_BUDGET':{'paid_limit_eur':2.0,'usd_per_eur':1.10,'window_hours':24,'ledger':str(tmp_path/'test-spend.jsonl')},
        '_instance_path':lambda value:Path(value)}
    monkeypatch.setitem(sys.modules,'litellm',SimpleNamespace())
    # Only local fixture lookups run here. Avoid the sandbox's executor-shutdown stall;
    # concurrent ASGI requests still interleave at the provider's awaited barrier.
    async def inline(fn,*args,**kwargs):return fn(*args,**kwargs)
    monkeypatch.setattr(asyncio,'to_thread',inline)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),ns)
    ns['_lookup_run_metadata']=ns['_run_metadata']
    ns['_run_metadata']=lambda run:{'run_id':run,'status':'open','privacy_class':'cloud_allowed'}
    return ns

def post(app,body,headers=None):
    async def call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
            return await client.post('/v1/chat/completions',json=body,
                                     headers={'Authorization':'Bearer fixture-token',**(headers or {})})
    return asyncio.run(call())

def response(usage=None):
    return SimpleNamespace(usage=usage,_hidden_params={},choices=[],model_dump=lambda:{'choices':[]})

def test_explicit_correlation_is_request_local_and_not_sent_to_provider(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);logs=[];calls=[]
    async def complete(route,**kw):calls.append(kw);return response()
    ns.update(log=logs.append,provider_completion=complete)
    app=ns['build_app']()
    assert post(app,{'model':'coding','messages':[]}, {'X-Walter-Run-Id':RUN}).status_code==200
    assert logs[-1].get('run_id')==RUN
    assert post(app,{'model':'coding','messages':[]}).status_code==200
    assert not logs[-1].get('run_id')
    assert all('run_id' not in c and 'task_id' not in c for c in calls)

def test_dsh_session_resolves_open_run_and_internal_cache_metadata_stays_local(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);logs=[];calls=[];lookups=[]
    async def complete(route,**kw):calls.append(kw);return response()
    ns.update(log=logs.append,provider_completion=complete,
              _session_run=lambda s:lookups.append(s) or {'run_id':RUN,'status':'open','privacy_class':'cloud_allowed'})
    r=post(ns['build_app'](),{'model':'coding','messages':[], 'prompt_cache_key':SESSION,'prompt_cache_retention':'24h'})
    assert r.status_code==200
    assert lookups==['dsh/vm/'+SESSION]
    assert logs[-1].get('run_id')==RUN
    assert 'prompt_cache_key' not in calls[0] and 'prompt_cache_retention' not in calls[0]

def test_invalid_correlation_fails_before_provider(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch)
    async def fail(*a,**kw):pytest.fail('provider must not be called')
    ns.update(provider_completion=fail)
    r=post(ns['build_app'](),{'messages':[]},{'X-Walter-Run-Id':'private-invalid-value'})
    assert r.status_code==400 and 'private-invalid-value' not in r.text

def test_private_dsh_run_never_reaches_cloud(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch)
    async def fail(*a,**kw):pytest.fail('private run must not reach provider')
    ns.update(provider_completion=fail,_session_run=lambda s:{'run_id':RUN,'status':'open','privacy_class':'local_only'})
    r=post(ns['build_app'](),{'messages':[],'prompt_cache_key':SESSION})
    assert r.status_code==403

def test_stream_records_final_usage_and_explicit_provider_cost(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);logs=[]
    usage=SimpleNamespace(prompt_tokens=30,completion_tokens=4,prompt_tokens_details=SimpleNamespace(cached_tokens=20),cost=0.002)
    async def chunks():
        yield SimpleNamespace(usage=None,_hidden_params={},model_dump_json=lambda:'{"choices":[{}]}')
        yield SimpleNamespace(usage=usage,_hidden_params={},model_dump_json=lambda:'{"usage":{"prompt_tokens":30,"completion_tokens":4,"cost":0.002}}')
    async def complete(*a,**kw):return chunks()
    ns.update(log=logs.append,provider_completion=complete)
    r=post(ns['build_app'](),{'messages':[],'stream':True})
    assert r.status_code==200 and '[DONE]' in r.text
    assert logs[-1].get('usage')=={'in':30,'out':4,'cached':20}
    assert logs[-1].get('cost_usd')==0.002 and logs[-1].get('cost_status')=='reported'

def test_absent_cost_is_unknown_and_estimate_is_labelled(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);logs=[]
    async def complete(*a,**kw):
        r=response(SimpleNamespace(prompt_tokens=3,completion_tokens=1,prompt_tokens_details=None))
        r._hidden_params={'response_cost':0.0004}
        return r
    ns.update(log=logs.append,provider_completion=complete)
    assert post(ns['build_app'](),{'messages':[]}).status_code==200
    assert logs[-1].get('cost_usd')==0.0004 and logs[-1].get('cost_status')=='estimated'

def test_paid_call_without_reported_cost_gets_the_router_price_never_zero(tmp_path,monkeypatch):
    """C10 (2026-11-07): Venice/Kie report no cost; the call is priced at the route's router price, labelled."""
    for host,expected in (({'price_in_1m':1.0,'price_out_1m':4.0},(3*1.0+1*4.0)/1e6),({},None)):
        ns=gateway(tmp_path,monkeypatch);logs=[]
        ns['decision']=lambda task,host=host:{'model_id':'m','execution':[{'provider':'kie','model':'m','host':host}]}
        async def complete(*a,**kw):
            r=response(SimpleNamespace(prompt_tokens=3,completion_tokens=1,prompt_tokens_details=None));r._hidden_params={}
            return r
        ns.update(log=logs.append,provider_completion=complete)
        assert post(ns['build_app'](),{'messages':[]}).status_code==200
        assert logs[-1].get('cost_usd')==expected
        assert logs[-1].get('cost_status')==('estimated_price' if expected else 'unknown')
        r=post(ns['build_app'](),{'messages':[]})      # the caller's own ledger gets the same, labelled
        assert (r.headers.get('x-walter-cost-usd') is not None)==(expected is not None)
        if expected:
            assert abs(float(r.headers['x-walter-cost-usd'])-expected)<1e-9 and r.headers['x-walter-cost-status']=='estimated_price'

def test_usage_dict_and_zero_are_preserved(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch)
    u={'prompt_tokens':3,'completion_tokens':0,'prompt_tokens_details':{'cached_tokens':1},'cost':0}
    assert ns['_usage'](response(u))=={'in':3,'out':0,'cached':1}


def test_metadata_writer_preserves_correlation_usage_and_cost_source():
    from walter_router.serve import execution
    class Conn:
        def execute(self,sql,args):self.sql,self.args=sql,args;return self
        def fetchone(self):return {'exec_id':1}
    c=Conn()
    execution.log(c,{'task':'coding','provider':'fixture','ok':True,'run_id':RUN,
                     'usage':{'in':30,'out':4,'cached':20},'cost_usd':0.002,'cost_status':'reported'})
    fields=c.sql.split('(',1)[1].split(')',1)[0].replace(' ','').split(',')
    row=dict(zip(fields,c.args))
    assert row['run_id']==RUN
    assert json.loads(row.get('usage') or '{}')=={'in':30,'out':4,'cached':20}
    assert row.get('cost_status')=='reported'


@pytest.mark.parametrize('bad',[None,-1,float('nan'),float('inf'),True,'unknown'])
def test_invalid_or_missing_cost_is_unknown(tmp_path,monkeypatch,bad):
    ns=gateway(tmp_path,monkeypatch)
    assert ns['_telemetry'](response({'cost':bad}))['cost_usd'] is None


@pytest.mark.parametrize('via_session',[False,True])
@pytest.mark.parametrize('privacy',['local_only','redacted_cloud'])
def test_identified_private_context_is_refused_for_headers_and_sessions(tmp_path,monkeypatch,privacy,via_session):
    ns=gateway(tmp_path,monkeypatch)
    async def fail(*args,**kwargs):pytest.fail('private or unredacted context reached cloud')
    row={'run_id':RUN,'status':'open','privacy_class':privacy}
    ns.update(provider_completion=fail,_run_metadata=lambda run:row,_session_run=lambda session:row)
    body={'messages':[],'prompt_cache_key':SESSION} if via_session else {'messages':[]}
    headers=None if via_session else {'X-Walter-Run-Id':RUN}
    assert post(ns['build_app'](),body,headers).status_code==403


@pytest.mark.parametrize('row',[{}, {'run_id':RUN,'status':'ended','privacy_class':'cloud_allowed'},
                               {'run_id':RUN,'status':'open'}, {'run_id':None,'status':'open','privacy_class':'cloud_allowed'}])
@pytest.mark.parametrize('via_session',[False,True])
def test_identifiable_unresolved_or_unclassified_context_fails_closed(tmp_path,monkeypatch,row,via_session):
    ns=gateway(tmp_path,monkeypatch)
    async def fail(*args,**kwargs):pytest.fail('unresolved identified context reached cloud')
    ns.update(provider_completion=fail,_run_metadata=lambda run:row,_session_run=lambda session:row)
    body={'messages':[],'prompt_cache_key':SESSION} if via_session else {'messages':[]}
    headers=None if via_session else {'X-Walter-Run-Id':RUN}
    assert post(ns['build_app'](),body,headers).status_code in (403,409,503)


def test_explicit_run_metadata_uses_public_open_only_lookup(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);calls=[]
    def command(argv,**kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0,stdout=json.dumps({'run_id':RUN,'status':'open','privacy_class':'cloud_allowed'}))
    monkeypatch.setattr(subprocess,'run',command)
    row=ns['_lookup_run_metadata'](RUN)
    assert row['run_id']==RUN
    assert calls==[['walter-memory','runs','find',RUN,'--open-only']]


def test_hidden_zero_without_cost_provenance_is_unknown(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch)
    for usage in (None,{'prompt_tokens':4,'completion_tokens':1}):
        r=response(usage);r._hidden_params={'response_cost':0}
        assert ns['_telemetry'](r)['cost_usd'] is None
        assert ns['_telemetry'](r)['cost_status']=='unknown'
    assert ns['_telemetry'](response({'cost':0}))['cost_status']=='reported'


def test_writer_distinguishes_explicit_null_from_missing_environment_fallback(monkeypatch):
    from walter_router.serve import execution
    class Conn:
        def execute(self,sql,args):self.row=dict(zip(sql.split('(',1)[1].split(')',1)[0].replace(' ','').split(','),args));return self
        def fetchone(self):return {'exec_id':1}
    monkeypatch.setenv('WALTER_RUN_ID',RUN);monkeypatch.setenv('WALTER_TASK_ID',SESSION)
    c=Conn();execution.log(c,{'provider':'fixture','ok':True,'run_id':None,'task_id':None})
    assert c.row['run_id'] is None and c.row['task_id'] is None
    execution.log(c,{'provider':'fixture','ok':True})
    assert c.row['run_id']==RUN and c.row['task_id']==SESSION


async def streaming_response(ns):
    app=ns['build_app']()
    payload=json.dumps({'messages':[],'stream':True}).encode()
    async def receive():return {'type':'http.request','body':payload,'more_body':False}
    request=Request({'type':'http','method':'POST','path':'/v1/chat/completions','headers':[]},receive)
    endpoint=next(route.endpoint for route in app.routes if getattr(route,'path',None)=='/v1/chat/completions')
    return await endpoint(request,authorization='Bearer fixture-token')


def chunk():
    return SimpleNamespace(usage=None,_hidden_params={},model_dump_json=lambda:'{"choices":[{}]}')


def test_premature_stream_close_is_not_success(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);logs=[]
    async def chunks():
        yield chunk()
        yield chunk()
    async def complete(*a,**kw):return chunks()
    ns.update(log=logs.append,provider_completion=complete)
    async def scenario():
        reply=await streaming_response(ns)
        await reply.body_iterator.__anext__()
        await reply.body_iterator.aclose()
    asyncio.run(scenario())
    assert len(logs)==1 and logs[-1]['ok'] is False


def test_failing_stream_cleanup_still_records_attempt(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);logs=[]
    class Iterator:
        def __aiter__(self):return self
        async def __anext__(self):return chunk()
        async def aclose(self):raise RuntimeError('fixture close failure')
    async def complete(*a,**kw):return Iterator()
    ns.update(log=logs.append,provider_completion=complete)
    async def scenario():
        reply=await streaming_response(ns)
        await reply.body_iterator.__anext__()
        with pytest.raises(RuntimeError):await reply.body_iterator.aclose()
    asyncio.run(scenario())
    assert len(logs)==1 and logs[0]['ok'] is False
    assert 'fixture close failure' not in json.dumps(logs)


def test_stream_cancellation_before_first_chunk_is_recorded(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);logs=[]
    async def complete(*a,**kw):raise asyncio.CancelledError()
    ns.update(log=logs.append,provider_completion=complete)
    async def scenario():
        with pytest.raises(asyncio.CancelledError):await streaming_response(ns)
    asyncio.run(scenario())
    assert len(logs)==1 and logs[0]['ok'] is False


def test_concurrent_requests_keep_distinct_and_untracked_run_identity(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);logs=[];calls=[]
    run2='33333333-3333-4333-8333-333333333333'
    ns['log']=logs.append
    async def scenario():
        all_entered=asyncio.Event()
        async def complete(route,**kw):
            calls.append(kw)
            if len(calls)==3:all_entered.set()
            await asyncio.wait_for(all_entered.wait(),timeout=2)
            if kw['messages'][0]['content']=='first':await asyncio.sleep(0.01)
            return response({'prompt_tokens':2,'completion_tokens':1})
        ns['provider_completion']=complete
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ns['build_app']()),base_url='http://fixture') as client:
            async def send(label,run):
                headers={'Authorization':'Bearer fixture-token',**({'X-Walter-Run-Id':run} if run else {})}
                return await client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':label}]},headers=headers)
            results=await asyncio.gather(send('first',RUN),send('second',run2),send('untracked',None))
            assert all(result.status_code==200 for result in results)
    asyncio.run(scenario())
    assert {row.get('run_id') for row in logs}=={RUN,run2,None}
    assert logs[-1]['run_id']==RUN
    assert all(not any(k in call for k in ('run_id','task_id','prompt_cache_key')) for call in calls)


def test_observed_dsh_routing_uses_public_cli_after_actual_response(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);calls=[]
    def command(argv,**kw):
        calls.append((argv,kw.get('input')))
        return SimpleNamespace(returncode=0,stdout='{}')
    monkeypatch.setattr(subprocess,'run',command)
    entry={'agent':'dsh','run_id':RUN,'correlation_status':'resolved','provider':'fixture','model':'expected',
           'model_id':'canonical','ok':True,'observed_model':'actual'}
    ns['_record_attempt']({'provider':'fixture'},entry)
    assert calls[0][0][:2]==['walter-router','log-exec']
    assert calls[1][0]==['walter-memory','runs','routing',RUN]
    routing=json.loads(calls[1][1]);assert routing['applied'] is True and routing['observed_model']=='actual'
    calls.clear();ns['_record_attempt']({}, {**entry,'observed_model':None})
    assert len(calls)==1
    calls.clear();ns['_record_attempt']({}, {**entry,'agent':'other'})
    assert len(calls)==1


def test_real_dsh_session_prefix_is_resolved_without_rewriting_its_identity(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);seen=[]
    native='session-'+SESSION
    async def complete(*a,**kw):return response()
    ns.update(provider_completion=complete,log=lambda entry:None,
              _session_run=lambda sid:seen.append(sid) or {'run_id':RUN,'status':'open','privacy_class':'cloud_allowed'})
    result=post(ns['build_app'](),{'messages':[],'prompt_cache_key':native})
    assert result.status_code==200
    assert seen==['dsh/vm/'+native]


def test_exact_transport_returns_common_usage_and_cost_provenance(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch)
    msg=SimpleNamespace(model_dump=lambda **kw:{'content':'OK'})
    result=SimpleNamespace(usage={'prompt_tokens':5,'completion_tokens':1,'cost':0.003},_hidden_params={},
                           choices=[SimpleNamespace(message=msg,finish_reason='stop')],model='fixture-model',id='fixture-response')
    async def complete(*a,**kw):return result
    ns['provider_completion']=complete
    out=asyncio.run(ns['exact_call']({'route':{'provider':'openrouter','model':'fixture-model'},'messages':[]}))
    assert out['ok'] is True and out['usage']['in']==5
    assert out.get('cost_usd')==0.003 and out.get('cost_status')=='reported'



class RateLimitError(Exception):
    status_code = 429


def test_subscription_rate_limit_is_waited_out_before_any_fallback(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);logs=[];calls=[]
    ns['decision']=lambda task:{'model_id':'m','execution':[{'provider':'claude-pro','model':'m','access':'subscription'},
                                                               {'provider':'openrouter','model':'m','access':'paid'}]}
    async def complete(route,**kw):
        calls.append(route['provider'])
        if len(calls)<3:raise RateLimitError()
        return response()
    ns.update(log=logs.append,provider_completion=complete)
    assert post(ns['build_app'](),{'model':'coding','messages':[]}).status_code==200
    assert calls==['claude-pro']*3 and [e['provider'] for e in logs]==['claude-pro'] and logs[0]['ok'] is True


def test_exhausted_rate_limit_is_logged_skipped_not_failed(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);logs=[]
    ns['decision']=lambda task:{'model_id':'m','execution':[{'provider':'claude-pro','model':'m','access':'subscription'},
                                                               {'provider':'openrouter','model':'m','access':'paid'}]}
    async def complete(route,**kw):
        if route['provider']=='claude-pro':raise RateLimitError()
        return response()
    ns.update(log=logs.append,provider_completion=complete)
    assert post(ns['build_app'](),{'model':'coding','messages':[]}).status_code==200
    assert logs[0]['provider']=='claude-pro' and logs[0]['skipped']=='rate_limit'
    assert logs[1]['provider']=='openrouter' and logs[1]['ok'] is True and 'skipped' not in logs[1]


def test_test_runs_paid_spend_is_charged_then_refused_above_the_cap(tmp_path,monkeypatch):
    ns=gateway(tmp_path,monkeypatch);logs=[];calls=[]
    ns['_run_metadata']=lambda run:{'run_id':run,'status':'open','privacy_class':'cloud_allowed','channel':'test'}
    ns['decision']=lambda task:{'model_id':'m','execution':[{'provider':'openrouter','model':'m','access':'paid',
                                                                'host':{'price_in_1m':4.0,'price_out_1m':20.0}}]}
    async def complete(route,**kw):
        calls.append(1)
        return SimpleNamespace(usage={'prompt_tokens':100,'completion_tokens':10,'cost':1.5},_hidden_params={},
                               choices=[],model_dump=lambda:{'choices':[]})
    ns.update(log=logs.append,provider_completion=complete)
    app=ns['build_app']()
    assert post(app,{'model':'coding','messages':[]},{'X-Walter-Run-Id':RUN}).status_code==200
    assert ns['test_budget']()['spent_usd']==1.5
    assert post(app,{'model':'coding','messages':[]},{'X-Walter-Run-Id':RUN}).status_code==200   # 1.5 $ < cap 2.2 $
    assert ns['test_budget']()['spent_usd']==3.0
    refused=post(app,{'model':'coding','messages':[]},{'X-Walter-Run-Id':RUN})
    assert refused.status_code==502 and 'test_budget' in refused.text and len(calls)==2
    assert logs[-2]['skipped']=='test_budget' and logs[-1]['error']=='all routes failed'
    assert post(app,{'model':'coding','messages':[]}).status_code==200   # owner's untracked calls are never capped
    ns['approve_tests'](2.0,'fixture')
    assert post(app,{'model':'coding','messages':[]},{'X-Walter-Run-Id':RUN}).status_code==200


def test_second_claude_account_is_tried_without_waiting_and_each_attempt_names_its_account(tmp_path,monkeypatch):
    """2026-11-07: two Claude accounts = two routes; a refusal on the first goes straight to the second (no burst wait,
    no paid route), and every attempt is traceable to its account."""
    ns=gateway(tmp_path,monkeypatch);logs=[];calls=[]
    ns['RATE_LIMIT_WAITS']=(30,30)   # would stall the test if waited
    ns['decision']=lambda task:{'model_id':'m','execution':[
        {'provider':'claude-pro','model':'m','access':'subscription','account':'anthropic-pro'},
        {'provider':'claude-pro','model':'m','access':'subscription','account':'anthropic-pro-2'},
        {'provider':'openrouter','model':'m','access':'paid'}]}
    async def complete(route,**kw):
        calls.append(route.get('account') or route['provider'])
        if route.get('account')=='anthropic-pro':raise RateLimitError()
        return response()
    ns.update(log=logs.append,provider_completion=complete)
    t0=time.monotonic()
    assert post(ns['build_app'](),{'model':'coding','messages':[]}).status_code==200
    assert time.monotonic()-t0<10 and calls==['anthropic-pro','anthropic-pro-2']
    assert [(e['account'],e.get('skipped'),e['ok']) for e in logs]==[('anthropic-pro','rate_limit',False),('anthropic-pro-2',None,True)]


def test_claude_account_secret_comes_from_the_gateway_setting_never_from_the_route(monkeypatch):
    source=Path(__file__).resolve().parents[1]/'llm'/'gateway.py'
    tree=ast.parse(source.read_text())
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in {'provider_completion','claude_accounts'}]
    asked=[]
    grants=SimpleNamespace(access=lambda grant:asked.append(grant) or 'token')
    monkeypatch.setitem(sys.modules,'walter_secrets',SimpleNamespace(grants=grants))
    async def completion(config,token,**kw):return config['account']
    monkeypatch.setitem(sys.modules,'claude_subscription',SimpleNamespace(completion=completion))
    async def inline(fn,*args,**kwargs):return fn(*args,**kwargs)
    monkeypatch.setattr(asyncio,'to_thread',inline)
    ns={'_CONF':{'claude_subscription':{'grant':'claude-subscription','accounts':{'anthropic-pro':'claude-subscription',
                                                                                 'anthropic-pro-2':'claude-subscription-2'}}},
        '_instance_path':lambda v:Path(v)}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),ns)
    run=lambda route:asyncio.run(ns['provider_completion']({'provider':'claude-pro',**route}))
    assert run({'account':'anthropic-pro-2','grant':'telegram-bot'})=='anthropic-pro-2' and asked==['claude-subscription-2']
    assert run({})=='anthropic-pro' and asked[-1]=='claude-subscription'
    with pytest.raises(ValueError):run({'account':'someone-else'})
    assert len(asked)==2


def plan_gateway(tmp_path, monkeypatch, requested):
    ns=gateway(tmp_path,monkeypatch);logs=[];asked=[]
    extra=['planned_task','exact_task','owner_tasks','rule_answer','_text_parts','_rule_completion','_rule_stream','_rule_routing']
    source=Path(__file__).resolve().parents[1]/'llm'/'gateway.py'
    tree=ast.parse(source.read_text())
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in extra]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),ns)
    ns['chat_tasks']=lambda:['coding','general','document']
    ns['owner_tasks']=lambda:['coding','general','document']
    ns['_session_run']=lambda session:{'run_id':RUN,'status':'open','privacy_class':'cloud_allowed','requested':requested}
    def decision(task):
        asked.append(task);return {'model_id':'m','execution':[{'provider':'fixture','model':'m'}]}
    async def complete(route,**kw):return response()
    ns.update(log=logs.append,decision=decision,provider_completion=complete)
    return ns,logs,asked


def test_auto_follows_the_plan_and_an_explicit_task_only_takes_its_tier(tmp_path,monkeypatch):
    ns,logs,asked=plan_gateway(tmp_path,monkeypatch,{'task':'general','level':'L2'})
    app=ns['build_app']()
    for model in ('auto','coding'):
        assert post(app,{'model':model,'messages':[{'role':'user','content':'x'}],'prompt_cache_key':SESSION}).status_code==200
    assert asked==['general/L2','coding/L2'] and logs[0]['plan']=='task+level' and logs[1]['plan']=='level'
    ns,logs,asked=plan_gateway(tmp_path,monkeypatch,{'task':'unknown-task','level':'L9'})
    assert post(ns['build_app'](),{'model':'auto','messages':[]},).status_code==200 and asked==['coding']
    ns,logs,asked=plan_gateway(tmp_path,monkeypatch,{'task':'memory_extraction','level':'L1'})   # internal poste
    ns['owner_tasks']=lambda:['coding','general']
    assert post(ns['build_app'](),{'model':'auto','messages':[],'prompt_cache_key':SESSION}).status_code==200 and asked==['coding/L1']


def test_rule_answer_needs_the_exact_owner_message_and_calls_no_model(tmp_path,monkeypatch):
    sha=hashlib.sha256(b'12*7').hexdigest()
    ns,logs,asked=plan_gateway(tmp_path,monkeypatch,{'task':'general','level':'L1','fast_path':'trivial','answer':'12*7 = 84','message_sha':sha})
    ns['_rule_routing']=lambda run=None:None
    app=ns['build_app']()
    r=post(app,{'model':'auto','messages':[{'role':'user','content':[{'type':'text','text':' 12*7 '}]}],'prompt_cache_key':SESSION})
    assert r.status_code==200 and r.json()['choices'][0]['message']['content']=='12*7 = 84' and asked==[]
    assert r.headers['X-Walter-Route']=='walter-context/rule' and logs[-1]['rule']=='trivial'
    s=post(app,{'model':'auto','stream':True,'messages':[{'role':'user','content':'12*7'}],'prompt_cache_key':SESSION})
    assert '12*7 = 84' in s.text and s.text.rstrip().endswith('[DONE]') and asked==[]
    dsh=[{'role':'system','content':'runtime'},{'role':'user','content':'<walter-context>x</walter-context>'},
         {'role':'user','content':[{'type':'text','text':'12*7'}]},{'role':'user','content':'<system-reminder>AGENTS</system-reminder>'},
         {'role':'user','content':'Current runtime context. ...'}]                           # DSH appends 2 user rows
    assert post(app,{'model':'auto','messages':dsh,'prompt_cache_key':SESSION}).json()['choices'][0]['message']['content']=='12*7 = 84'
    assert asked==[]
    for messages in ([{'role':'user','content':'12*7'},{'role':'tool','content':'84'}],     # a tool step
                     [{'role':'user','content':'12*7'},{'role':'assistant','content':'84'},{'role':'user','content':'Current runtime context.'}],
                     [{'role':'user','content':'Write a title for: 12*7'}]):              # another request
        assert post(app,{'model':'auto','messages':messages,'prompt_cache_key':SESSION}).status_code==200
    assert asked==['general/L1','general/L1','general/L1']


def test_every_request_leaves_one_selection_line_with_its_plan_reasons_and_passed_routes(tmp_path,monkeypatch):
    """2026-11-07 (owner: « une télémétrie claire sur chaque sélection »): the plan in order with each route's state,
    the route that answered, the routes passed over and why, and whether subscriptions came first."""
    ns=gateway(tmp_path,monkeypatch);logs=[]
    plan=[{'provider':'claude-pro','account':'anthropic-pro-2','model':'m','access':'subscription',
           'subscription':{'quota_used_percent':29.0,'session_used_percent':5.0}},
          {'provider':'openrouter','model':'x/m','access':'paid','probe_ok':True},
          {'provider':'claude-pro','account':'anthropic-pro','model':'m','access':'subscription',
           'subscription':{'quota_used_percent':100.0,'session_used_percent':0.0}}]
    ns['decision']=lambda task:{'model_id':'m','source':'default_objective','execution':plan}
    async def complete(route,**kw):
        if route['provider']=='claude-pro':raise RateLimitError()
        return response(SimpleNamespace(prompt_tokens=3,completion_tokens=1,prompt_tokens_details=None))
    ns.update(log=logs.append,provider_completion=complete,RATE_LIMIT_WAITS=())
    assert post(ns['build_app'](),{'messages':[]}).status_code==200
    line=json.loads((tmp_path/'log.jsonl').read_text().splitlines()[-1])
    assert line['event']=='selection' and line['subscription_first'] is True and line['chosen']==1
    assert [r['state'] for r in line['plan']]==['subscription_available','paid','subscription_spent']
    assert line['passed']==[{'position':0,'reason':'rate_limit'}] and line['chosen_route']['provider']=='openrouter'
    assert line['plan'][0]['account']=='anthropic-pro-2' and line['plan'][0]['quota']==29.0
    assert ns['selection_check']([{'position':0,'provider':'openrouter','state':'paid'},
                                  {'position':1,'provider':'codex','state':'subscription_available'}]) is False


def test_a_model_named_for_the_run_is_executed_exactly_and_an_unknown_one_is_refused(tmp_path, monkeypatch):
    """Lot E5 (2026-11-10): an Engine API delegation names a model the Router validated; walter-llm runs exactly that
    one (Router `route --model`), whatever the poste asked, and says so when it cannot — never another model."""
    ns,logs,asked=plan_gateway(tmp_path,monkeypatch,{'model':'claude-opus-5-5','provider':'venice','task':'general'})
    assert ns['planned_task']('auto',{'model':'claude-opus-5-5','provider':'venice'})==('exact:claude-opus-5-5@venice','model')
    assert ns['planned_task']('coding',{'model':'claude-opus-5-5'})==('exact:claude-opus-5-5','model')
    assert ns['planned_task']('auto',{'model':'bad model; rm'})[0]!='exact:bad model; rm'
    assert ns['exact_task']({'model':'m','provider':'a b'}) is None
