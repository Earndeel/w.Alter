"""Bounded, reversible Hindsight hygiene on PostgreSQL/pgvector only."""
from __future__ import annotations
import argparse,datetime,json,os,pathlib
from .db import connection

SELECTORS={
 'ephemeral':r"text ~* '(proc_[0-9a-f]{6,}|[0-9]+ */ *[0-9]+ *tests|en [0-9]+([,.][0-9]+)? secondes|(exit code|code de sortie|code=0)|commit (local )?[0-9a-f]{7,})'",
 'markers':"""(text LIKE 'TEST_SUITE:%%' OR text LIKE 'BENCH_TEST_%%' OR text ILIKE '%%AUDIT_MEMORY_CHECK%%'
                 OR text ILIKE '%%MEMCHECK%%' OR context IN ('automated testing','automated test','test automatisé','technical verification','benchmarking')
                 OR text='Le système de test automatique vérifie la fonctionnalité retain en français.'
                 OR text LIKE 'pgvector ANN search uses HNSW index with ef_search=40%%'
                 OR text LIKE 'Hindsight test suite ran%%')"""
}

def quarantine(kind='ephemeral', *, apply=False, limit=200, backup_dir='/root/.hermes/backups/memory-hygiene'):
    if kind not in SELECTORS:raise ValueError('unknown hygiene selector')
    if not 1<=limit<=1000:raise ValueError('limit must be between 1 and 1000')
    where="bank_id='walter' and not ('quarantine:noise'=any(coalesce(tags,array[]::text[]))) and ("+SELECTORS[kind]+')'
    with connection() as conn:
        total=conn.execute('select count(*) n from public.memory_units where '+where,()).fetchone()['n']
        result={'ok':True,'mode':'quarantine' if apply else 'dry_run','matched':total,'quarantined':0,'remaining':total}
        if not apply or not total:return result
        rows=conn.execute('select id,tags from public.memory_units where '+where+' order by created_at,id limit %s for update',(limit,)).fetchall()
        ids=[r['id'] for r in rows]
        folder=pathlib.Path(backup_dir);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path=folder/(kind+'-'+stamp+'.json');fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'kind':kind,'before':rows},f,default=str)
        changed=conn.execute("""update public.memory_units set tags=array(select distinct unnest(coalesce(tags,array[]::text[]) ||
                    array['quarantine:noise',%s]::text[])) where id=any(%s) returning id""",('hygiene:'+kind,ids)).fetchall()
        result.update(quarantined=len(changed),remaining=total-len(changed),snapshot=str(path))
        conn.execute("insert into system.audit_log(actor,action,target,details) values ('walter-memory','memory.quarantine',%s,%s::jsonb)",
                     (kind,json.dumps(result)))
        return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--kind',choices=SELECTORS,default='ephemeral');p.add_argument('--apply',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--limit',type=int,default=200);a=p.parse_args()
    print(json.dumps(quarantine(a.kind,apply=a.apply and not a.dry_run,limit=a.limit)))

if __name__=='__main__':main()
