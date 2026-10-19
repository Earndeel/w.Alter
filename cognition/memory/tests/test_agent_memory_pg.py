"""Optional PostgreSQL regression: temporary fixtures only, rolled back on exit."""
import os
import pytest
from walter_memory import agent_memory as m, read_policy
from walter_memory.db import connect

@pytest.mark.skipif(os.environ.get('WALTER_TEST_PG') != '1', reason='set WALTER_TEST_PG=1 for temporary PostgreSQL fixtures')
def test_canonical_privacy_provenance_and_freshness():
    ids=[f'00000000-0000-4000-8000-{i:012d}' for i in range(1,5)];event,obj,derived,retract=ids
    conn=connect()
    class TempOnly:
     def execute(self,query,args=()):
      assert 'core.' in query
      return conn.execute(query.replace('core.','pg_temp.'),args)
    def allowed(kind,ref,text='public fixture'):
     read_policy._retracted=(0.0,frozenset())   # no 60 s cache inside the test
     return read_policy.canonical_allowed(TempOnly(),dict(kind=kind,ref_id=ref,text=text,privacy_class='cloud_allowed'))
    checks=0
    try:
     conn.execute('create temp table events(event_id uuid, occurred_at timestamptz default now(), privacy_class text, content text, event_type text, payload jsonb) on commit drop')
     conn.execute('create temp table event_keys(event_id uuid, occurred_at timestamptz) on commit drop')
     conn.execute('create temp table objects(id uuid, privacy_class text, original_name text, derived_text text, status text, purged_at timestamptz) on commit drop')
     conn.execute('create temp table derived_items(item_id uuid,privacy_class text,content text,status text,attributes jsonb,source_event_ids uuid[],source_object_ids uuid[]) on commit drop')
     conn.execute("insert into pg_temp.events(event_id,privacy_class,content,event_type,payload) values(%s,'cloud_allowed','public fixture','note.recorded','{}')",(event,))
     conn.execute("insert into pg_temp.event_keys select event_id, occurred_at from pg_temp.events")
     conn.execute("insert into pg_temp.objects values(%s,'local_only','fixture','public fixture','stored',null)",(obj,))
     conn.execute("insert into pg_temp.derived_items values(%s,'cloud_allowed','public fixture','derived','{}',ARRAY[%s::uuid],ARRAY[%s::uuid])",(derived,event,obj))
     assert allowed('event',event);checks+=1
     assert not allowed('derived',derived);checks+=1
     conn.execute("update pg_temp.objects set privacy_class='cloud_allowed'")
     assert allowed('derived',derived);checks+=1
     conn.execute("update pg_temp.objects set purged_at=now()")
     assert not allowed('derived',derived);checks+=1
     assert not allowed('object',obj);checks+=1
     conn.execute("update pg_temp.objects set purged_at=null")
     assert allowed('object',obj);checks+=1
     conn.execute("insert into pg_temp.events(event_id,privacy_class,content,event_type,payload) values(%s,'cloud_allowed','','event.retracted',jsonb_build_object('target_event_id',%s::text))",(retract,event))
     assert not allowed('event',event);checks+=1
     assert not allowed('derived',derived);checks+=1
     conn.execute('delete from pg_temp.events where event_id=%s',(retract,))
     conn.execute("update pg_temp.derived_items set status='verified'")
     assert allowed('derived',derived);checks+=1
     conn.execute("update pg_temp.derived_items set attributes='{"+'"quarantined":true'+"}'")
     assert not allowed('derived',derived);checks+=1
     conn.execute("update pg_temp.derived_items set attributes='{}',content='corrected fixture'")
     assert not allowed('derived',derived);checks+=1
     assert allowed('derived',derived,'corrected fixture');checks+=1
     conn.execute("update pg_temp.derived_items set status='legacy_derived'")
     assert allowed('derived',derived,'corrected fixture');checks+=1   # A2: readable, never promoted
     conn.execute("update pg_temp.derived_items set source_event_ids='{}',source_object_ids='{}'")
     assert not allowed('derived',derived,'corrected fixture');checks+=1
     assert checks == 14
    finally:
     conn.rollback();conn.close()
