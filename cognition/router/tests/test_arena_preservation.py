"""Partial public Arena collections preserve evidence and remain visibly degraded; no DB/network/model calls."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import json

import pytest

from walter_router import health
from walter_router.guardian import checks
from walter_router.research import sources
from walter_router.research.benchmarks import arena

NOW = datetime.now(timezone.utc)


def doc(keys, errors=None):
    return {'boards':{key:{'rows':[{'rating':1}], 'kind':'elo','leaderboard_id':key} for key in keys}, 'errors':errors or {}}


class Cursor(list):
    def fetchone(self): return self[0] if self else None
    def fetchall(self): return list(self)


class Connection:
    def __init__(self, raw): self.raw=raw
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def transaction(self): return nullcontext()
    def execute(self, sql, args=()):
        if 'select raw from models.snapshots' in sql:
            return Cursor([{'raw':self.raw}])
        if 'summary from models.runs' in sql:
            return Cursor([{'summary':{}}])
        if 'summary' in sql and 'status, finished_at' in sql:
            return Cursor([{'run_id':1,'status':'ok','finished_at':NOW,'age':timedelta(),'summary':{}}])
        if "where status = 'ok'" in sql:
            return Cursor([{'run_id':1,'finished_at':NOW}])
        if 'select now() -' in sql:
            return Cursor([{'a':timedelta()}])
        if 'models.latest_snapshots' in sql:
            return Cursor([{'kind':'arena','age_h':0}])
        if 'latest_dossiers' in sql:
            return Cursor([{'n':1}])
        if 'provider_status' in sql or 'latest_subscription_usage' in sql:
            return Cursor()
        raise AssertionError(sql)


def test_full_request_keeps_previous_boards_when_only_some_are_refreshed(monkeypatch):
    previous=doc(set(arena.ARENA_BOARDS.values()))
    partial=doc(set(arena.ARENA_BOARDS.values()) - {'vision'}, {'vision':'timeout'})
    monkeypatch.setattr(sources,'SOURCES',{'arena':lambda:(partial,NOW,'https://arena.ai/leaderboard/')})
    saved=[]
    result=sources.collect_all(Connection(previous),lambda c,k,d,t,u:saved.append(d) or (1,True),only=['arena'])
    assert set(saved[0]['boards']) == set(arena.ARENA_BOARDS.values())
    assert saved[0]['errors'] == {'vision':'timeout'}
    assert result['arena']['snapshot_id']==1


def test_silent_missing_board_is_not_turned_into_a_complete_refresh(monkeypatch):
    previous=doc(set(arena.ARENA_BOARDS.values()))
    monkeypatch.setattr(sources,'SOURCES',{'arena':lambda:(doc(['text']),NOW,'https://arena.ai/leaderboard/')})
    saved=[]
    sources.collect_all(Connection(previous),lambda c,k,d,t,u:saved.append(d) or (1,True),only=['arena'])
    assert set(saved[0]['boards']) == set(previous['boards'])
    assert 'vision' in saved[0]['errors']


def test_part_retry_clears_only_errors_of_boards_actually_refreshed(monkeypatch):
    previous=doc(['text','vision','document'],{'vision':'timeout','document':'budget'})
    monkeypatch.setattr(sources,'SOURCES',{'arena':lambda **kw:(doc(['vision']),NOW,'https://arena.ai/leaderboard/')})
    saved=[]
    sources.collect_all(Connection(previous),lambda c,k,d,t,u:saved.append(d) or (1,True),parts={'arena':{'vision'}})
    assert set(saved[0]['boards'])=={'text','vision','document'}
    assert saved[0]['errors']=={'document':'budget'}


def test_health_warns_even_when_all_boards_exist_but_some_are_retained(monkeypatch):
    previous=doc(set(arena.ARENA_BOARDS.values()),{'vision':'timeout'})
    monkeypatch.setattr(health.db,'connect',lambda:Connection(previous))
    result=health.health()
    assert any('arena' in message and 'incompl' in message for message in result['warnings'])
    assert result['source_coverage']['arena']['failed_boards']==['vision']


def test_guardian_reports_missing_arena_boards_without_waiting_for_age_limit():
    result=checks.sources(Connection(doc(['text'])))
    assert len(result)==1 and result[0]['kind']=='source_error' and result[0]['subject']=='arena'
    assert 'vision' in result[0]['detail']['coverage']['missing_boards']


def test_complete_arena_does_not_raise_a_coverage_warning(monkeypatch):
    previous=doc(set(arena.ARENA_BOARDS.values()))
    monkeypatch.setattr(health.db,'connect',lambda:Connection(previous))
    assert not health.health()['warnings']
    assert checks.sources(Connection(previous))==[]


@pytest.mark.parametrize('key,path,slug',[
    ('text_coding','chat/text/coding','text-coding-style_control'),
    ('text_creative','chat/text/creative-writing','text-creative_writing-style_control')])
def test_collection_uses_observed_official_category_route(monkeypatch,key,path,slug):
    read=[]
    envelope={'id':'leaderboard-sets/public/leaderboards/'+slug+'/leaderboard-snapshots/latest',
              'entries':[{'modelDisplayName':'Fixture','rating':1}]}
    def fetch(url):
        read.append(url)
        return json.dumps(envelope,separators=(',',':'))
    monkeypatch.setattr(arena,'fetch_text',fetch)
    monkeypatch.setattr(arena.time,'sleep',lambda *a:None)
    result,_,_=arena.source_arena(parts={key})
    assert read==['https://arena.ai/leaderboard/'+path]
    assert set(result['boards'])=={key}


def test_empty_board_does_not_replace_previous_evidence_or_clear_failure(monkeypatch):
    previous=doc(['vision'], {'vision':'timeout'})
    partial={'boards':{'vision':{'rows':[]}}, 'errors':{}}
    monkeypatch.setattr(sources,'SOURCES',{'arena':lambda **kw:(partial,NOW,'https://arena.ai/leaderboard/')})
    saved=[]
    sources.collect_all(Connection(previous),lambda c,k,d,t,u:saved.append(d) or (1,True),parts={'arena':{'vision'}})
    assert saved[0]['boards']['vision']==previous['boards']['vision']
    assert 'vision' in saved[0]['errors']
