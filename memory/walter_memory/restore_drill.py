"""Offsite reconstruction rehearsal in a disposable, networkless PG container.

Restored configuration is inspected, never executed. No service, timer, consumer,
provider, Mac action or message sender is started from the restored tree. This is
not a clean-VM installation test. Only counters/identifiers enter the report.
"""
from __future__ import annotations

import argparse
import ast
import datetime
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
import uuid

from . import backup_bundle


class DrillError(RuntimeError):
    pass


def command(argv, *, timeout=600, stdin=None):
    result = subprocess.run(argv, stdin=stdin, capture_output=True, timeout=timeout)
    if result.returncode:
        # Never echo decrypted values or restore SQL diagnostics to model/log output.
        raise DrillError(f"{Path(argv[0]).name} failed (exit {result.returncode})")
    return result.stdout


def restore_tree(archive_path, root):
    """Restore only inside root; defer/rebase symlinks so they cannot escape it."""
    root=Path(root);root.mkdir(mode=0o700,parents=True,exist_ok=False)
    links=[]; directories=[]; seen=set(); count=0
    with tarfile.open(archive_path,'r|') as archive:
        for item in archive:
            name=PurePosixPath(item.name)
            if name.is_absolute() or '..' in name.parts or str(name) in seen:
                raise ValueError('unsafe or duplicate archive member')
            seen.add(str(name));target=root/str(name)
            if item.issym():
                links.append((target,item.linkname));continue
            if not (item.isdir() or item.isfile()):
                raise ValueError('unsupported restore member')
            target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            if item.isdir():
                target.mkdir(mode=0o700,exist_ok=True);directories.append((target,item.mode & 0o777))
            else:
                with target.open('xb') as out,archive.extractfile(item) as inp:
                    shutil.copyfileobj(inp,out,1024*1024)
                target.chmod(item.mode & 0o777);count+=1
    for target,value in links:
        logical=PurePosixPath(value)
        destination=root/str(logical).lstrip('/') if logical.is_absolute() else target.parent/value
        destination=Path(os.path.normpath(destination))
        if not destination.is_relative_to(root):raise ValueError('symlink escapes restore root')
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        target.symlink_to(os.path.relpath(destination,target.parent))
    for directory,mode in reversed(directories):directory.chmod(mode)
    return {'files':count,'rebased_links':len(links)}


def container_command(name,image,data):
    return ['docker','run','-d','--pull','never','--name',name,'--network','none',
        '--read-only','--cpus','1','--memory','4g','--pids-limit','256',
        '--security-opt','no-new-privileges','--cap-drop','ALL',
        '--cap-add','CHOWN','--cap-add','DAC_OVERRIDE','--cap-add','FOWNER','--cap-add','SETUID','--cap-add','SETGID',
        '--tmpfs','/tmp:rw,noexec,nosuid,size=256m','--tmpfs','/var/run/postgresql:rw,noexec,nosuid,size=16m',
        '--mount',f'type=bind,source={data},target=/var/lib/postgresql/data',
        '-e','POSTGRES_HOST_AUTH_METHOD=trust',image,'postgres']


def check_sqlite(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        ok=db.execute('pragma quick_check').fetchone()[0]=='ok'
        tables={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
        counts={t:db.execute(f'select count(*) from "{t}"').fetchone()[0] for t in ('messages','sessions') if t in tables}
        if not ok:raise DrillError('SQLite integrity check failed')
        return {'ok':ok,'tables':len(tables),'counts':counts}
    finally:db.close()


def validate_sources(restored):
    """Parse executable module sources; archived skill examples are data, not imports."""
    restored=Path(restored)
    registry=restored/'opt/walter-core/modules/registry.json'
    roots=({restored/m['root'].lstrip('/') for m in json.loads(registry.read_text())['modules']}
           if registry.exists() else set((restored/'opt').glob('walter-*')))
    parsed=0; artifacts=[]
    for module in sorted(roots):
        for source in module.rglob('*.py'):
            rel=source.relative_to(module)
            if source.is_symlink() or any(p in {'.git','venv','.venv','node_modules','__pycache__'} for p in rel.parts):
                continue
            knowledge=rel.parts[0] in {'skills','.worktrees'}
            try:
                ast.parse(source.read_bytes(),filename=str(source));parsed+=1
            except SyntaxError as exc:
                location=str(source.relative_to(restored))+':'+str(exc.lineno)
                if knowledge:
                    artifacts.append({'path':location,'type':'SyntaxError','scope':'non-runtime skill artifact'})
                else:
                    raise DrillError('restored Python source invalid: '+location) from None
    return {'parsed':parsed,'non_runtime_artifacts':artifacts}


def production_versions():
    versions={}
    for path in sorted(Path('/opt').glob('walter-*')):
        if not (path/'.git').exists():continue
        result=subprocess.run(['git','-C',str(path),'rev-parse','HEAD'],capture_output=True,text=True,timeout=10)
        dirty=subprocess.run(['git','-C',str(path),'status','--porcelain'],capture_output=True,text=True,timeout=10)
        versions[path.name]={'commit':result.stdout.strip() if result.returncode==0 else None,
                             'dirty':bool(dirty.stdout.strip())}
    return versions

def drill(report_path: Path, *, remote='gdrive:W.Alter Backups', image=None, scratch_parent='/var/tmp'):
    started=time.monotonic();report={'version':1,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope':'isolated container + restored filesystem; not a clean VM',
        'external_restored_actions':False,'backups':{},'steps':{},'ok':False,
        'production_versions_start':production_versions()}
    name='walter-restore-drill-'+uuid.uuid4().hex[:12];container=False;scratch=None
    report_path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.umask(0o077)
    try:
      free=shutil.disk_usage(scratch_parent).free
      pg_bytes=int(command(['docker','exec','hindsight-pg','psql','-U','hindsight','-d','hindsight',
          '-X','-A','-t','-c','select pg_database_size(current_database())']).decode())
      minimum=max(12*1024**3,pg_bytes*2+4*1024**3)
      report['resource_preflight']={'free_bytes':free,'production_database_bytes':pg_bytes,'minimum_free_bytes':minimum,
          'margin':'2x PG size + 4 GiB for downloads, config, SQLite and index/WAL work; floor 12 GiB'}
      if free < minimum:raise DrillError('insufficient scratch space for current PG size and reconstruction margin')
      scratch=tempfile.mkdtemp(prefix='walter-restore-isolated-',dir=scratch_parent)
      work=Path(scratch);key='/root/.hermes/vault/walter-recovery.agekey'
      stage_start=time.monotonic()
      payloads={}
      for kind in ('pg','statedb','config'):
          listing=command(['rclone','lsf',remote+'/'+kind],timeout=120).decode().splitlines()
          candidates=[n for n in listing if re.fullmatch(r'[A-Za-z0-9_.-]+\.age',n)]
          if not candidates:raise DrillError('no backup for '+kind)
          latest=max(candidates);encrypted=work/(kind+'.age')
          command(['rclone','copyto',remote+'/'+kind+'/'+latest,str(encrypted)],timeout=600)
          clear=work/kind
          command(['age','-d','-i',key,'-o',str(clear),str(encrypted)],timeout=600)
          encrypted.unlink()
          if kind in ('config','statedb'):
              unpacked=work/(kind+'.unpacked')
              command(['zstd','-q','-d',str(clear),'-o',str(unpacked)],timeout=300)
              clear.unlink();clear=unpacked
          payloads[kind]=clear
          report['backups'][kind]={'file':latest,'decrypted_bytes':clear.stat().st_size}
      report['steps']['download_decrypt_seconds']=round(time.monotonic()-stage_start,3)
      report['config_verification']=backup_bundle.verify(payloads['config'])
      restored=work/'root'
      report['filesystem_restore']=restore_tree(payloads['config'],restored)
      report['restored_contracts']=backup_bundle.contracts_check(restored)
      sources,required,absent=backup_bundle.inventory(restored)
      report['restored_inventory']={'sources':len(sources),'required':len(required),'optional_absent':len(absent)}
      report['main_sqlite']=check_sqlite(payloads['statedb'])
      report['profile_sqlite']={str(p.relative_to(restored)):check_sqlite(p)
                               for p in sorted((restored/'root/.hermes/profiles').glob('*/*.db'))}
      validation=validate_sources(restored)
      report['restored_python_sources_parsed']=validation['parsed']
      report['non_runtime_artifacts']=validation['non_runtime_artifacts']
      image=image or command(['docker','inspect','hindsight-pg','--format','{{.Image}}']).decode().strip()
      report['postgres_image']=image
      data=work/'pgdata';data.mkdir(mode=0o700)
      container=True
      command(container_command(name,image,data),timeout=120)
      report['isolation']=json.loads(command(['docker','inspect',name,'--format',
          '{{json .HostConfig}}']).decode())
      # Keep only the isolation contract, never environment or application config.
      report['isolation']={k:report['isolation'][k] for k in ('NetworkMode','ReadonlyRootfs','PortBindings','Memory','NanoCpus')}
      if report['isolation']['NetworkMode']!='none' or report['isolation']['PortBindings']:
          raise DrillError('container isolation contract failed')
      ready=False
      for _ in range(120):
          r=subprocess.run(['docker','exec',name,'pg_isready','-U','postgres'],capture_output=True)
          if r.returncode==0:ready=True;break
          time.sleep(1)
      if not ready:raise DrillError('isolated postgres startup timed out')
      command(['docker','exec',name,'createdb','-U','postgres','walter_restore'])
      stage_start=time.monotonic()
      with payloads['pg'].open('rb') as src:
          command(['docker','exec','-i',name,'pg_restore','--exit-on-error','--no-owner','--no-privileges',
                   '-U','postgres','-d','walter_restore'],stdin=src,timeout=2400)
      report['steps']['postgres_restore_seconds']=round(time.monotonic()-stage_start,3)
      query="""select json_build_object(
        'core_events',(select count(*) from core.events),
        'walter_log_events',(select count(*) from walter_logs.events),
        'objects',(select count(*) from core.objects),
        'skills',(select count(*) from skills.catalog),
        'models_tasks',(select count(*) from models.tasks),
        'checkpoints',(select count(*) from ingestion.checkpoints),
        'bus_cursors',(select count(*) from bus.cursors))"""
      report['postgres_counts']=json.loads(command(['docker','exec',name,'psql','-U','postgres','-d','walter_restore',
                  '-X','-A','-t','-v','ON_ERROR_STOP=1','-c',query]).decode())
      report['limits']=['No clean VM or boot test','Restored services/consumers deliberately not started',
          'Python dependency inventories restored; full environments not rebuilt',
          'Raw Vault bytes remain external; recovery credentials and catalogue restored',
          'Recovery key availability outside this VM not independently proven',
          'RPO/RTO targets require owner decision; this report measures the rehearsal only']
      report['ok']=True
    except Exception as exc:
        report['error']={'type':type(exc).__name__,'stage':'restore rehearsal failed; raw diagnostics withheld'}
        if isinstance(exc,DrillError):report['error']['reason']=str(exc)
    finally:
        if container:
            result=subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=60)
            report['container_removed']=result.returncode==0
        if scratch and (not container or report.get('container_removed')):
            shutil.rmtree(scratch)
            report['scratch_removed']=True
        elif scratch:
            report['scratch_retained']=scratch
        report['production_versions_end']=production_versions()
        report['production_changed_during_drill']=report['production_versions_start']!=report['production_versions_end']
        report['elapsed_seconds']=round(time.monotonic()-started,3)
        report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        report_path.write_text(json.dumps(report,indent=2,default=str));report_path.chmod(0o600)
    return report


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--report',required=True);ap.add_argument('--image')
    args=ap.parse_args();report=drill(Path(args.report),image=args.image)
    print(json.dumps({'ok':report['ok'],'elapsed_seconds':report['elapsed_seconds'],'report':args.report}))
    raise SystemExit(0 if report['ok'] else 1)


if __name__=='__main__':main()
