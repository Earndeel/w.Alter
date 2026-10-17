#!/usr/bin/env python3
"""PostgreSQL/pgvector marker hygiene. Quarantine only; Qdrant is retired."""
import argparse,datetime,json,pathlib,subprocess

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group();g.add_argument('--apply',action='store_true');g.add_argument('--dry-run',action='store_true')
    p.add_argument('--max-pg-marker-delete',type=int,default=200)
    p.add_argument('--max-qdrant-marker-delete',type=int,default=200,help=argparse.SUPPRESS)
    p.add_argument('--max-qdrant-invalidated-delete',type=int,default=500,help=argparse.SUPPRESS)
    p.add_argument('--output',default='/root/.hermes/logs/memory-autopilot/safe-cleanup-latest.json');p.add_argument('--json',action='store_true');a=p.parse_args()
    cmd=['/opt/walter-memory/venv/bin/python','-m','walter_memory.hygiene','--kind','markers','--limit',str(a.max_pg_marker_delete)]
    if a.apply:cmd.append('--apply')
    r=subprocess.run(cmd,cwd='/opt/walter-memory',capture_output=True,text=True,timeout=90)
    try:action=json.loads(r.stdout)
    except (ValueError,TypeError):action={'ok':False,'error':'hygiene command failed; inspect its service log','exit_code':r.returncode}
    retired={'skipped':True,'reason':'qdrant_retired_2026-10-01'}
    ok=r.returncode==0 and action.get('ok',False)
    report={'ts':datetime.datetime.now(datetime.timezone.utc).isoformat(),'mode':'apply' if a.apply else 'dry-run','safe_only':True,
            'actions':{'pg_test_markers':action,'qdrant_marker_points':retired,'qdrant_invalidated':retired},
            'summary':{'ok':ok,'blocked':[],'errors':[] if ok else ['pg_test_markers'],'applied_actions':int(bool(action.get('quarantined')))}}
    out=pathlib.Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report) if a.json else 'memory-safe-cleanup: ok='+str(ok))
    return 0 if ok else 2

if __name__=='__main__':raise SystemExit(main())
