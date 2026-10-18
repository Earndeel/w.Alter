"""Encrypted-offsite configuration payload: module sources plus their integration state.

This module builds/verifies a tar payload; the offsite runner applies zstd + age.
It never prints file contents or credentials. Source state.db is backed up separately.
"""
from __future__ import annotations
import argparse,datetime,hashlib,importlib.util,io,json,os,pathlib,shlex,sqlite3,subprocess,tarfile,tempfile

MANIFEST='walter-backup-manifest.json'
CORE_MODULES=('core','memory','router','skills','context','llm','soul','voice-memory','raw-vault')
MODULE_ANCHORS={'core':'server.py','memory':'walter_memory/events.py','router':'walter_router/cli.py',
                'skills':'walter_skills/api.py','context':'walter_context/session.py','llm':'gateway.py',
                'soul':'identity.md','voice-memory':'server.py','raw-vault':'rawvault.py'}
SKIP_PARTS={'venv','.venv','node_modules','__pycache__','.cache','.pytest_cache','.mypy_cache','.ruff_cache','.hermes-runtime'}
SKIP_PREFIXES=('root/.hermes/hermes-agent/.git','opt/walter-voice-memory/models',
               'root/.hermes/skills/.curator_backups','opt/dsh/home/sessions')
PROFILE_TRANSIENT={'cache','audio_cache','image_cache','images','sessions','sandboxes','workspace','logs','lsp'}

def excluded(name):
    p=pathlib.PurePosixPath(name)
    if any(x in SKIP_PARTS for x in p.parts):return True
    if any(name==x or name.startswith(x+'/') for x in SKIP_PREFIXES):return True
    if name.startswith('root/.hermes/profiles/'):
        if any(x in PROFILE_TRANSIENT for x in p.parts[4:]):return True
        if p.name.endswith(('.db','.db-wal','.db-shm')):return True
    return False

def contracts_check(root):
    """Reject stale generated registries before writing a backup payload.

    Old archives without a contract catalogue retain the v1 registry interface.
    Only the pure compiler is loaded; no optional module or MCP server imports.
    """
    catalog=root/'opt/walter-core/modules/catalog.json'
    if not catalog.exists():return {'legacy_registry':True}
    compiler=pathlib.Path('/opt/walter-core/walter_platform/contracts.py')
    if not compiler.is_file():raise RuntimeError('contract compiler unavailable')
    spec=importlib.util.spec_from_file_location('_walter_backup_contracts',compiler)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.check(catalog,root=root,registry=catalog.with_name('registry.json'))
    if not result['ok']:raise RuntimeError('module registry differs from owner contracts; regenerate before backup')
    return result

def module_backup_paths(root):
    """Read the composition contract without importing the capability server."""
    contracts_check(root)
    registry=root/'opt/walter-core/modules/registry.json'
    if not registry.exists():return []
    data=json.loads(registry.read_text())
    if data.get('version')!=1:raise RuntimeError('unsupported module registry version')
    paths=set()
    for module in data.get('modules',[]):
        for value in [*module.get('backup_paths',[]),*module.get('anchors',[])]:
            p=pathlib.PurePosixPath(value)
            if not p.is_absolute() or '..' in p.parts:raise RuntimeError('unsafe module backup path')
            paths.add(str(p).lstrip('/'))
    return sorted(paths)

def inventory(root):
    """Mandatory core and integration anchors; optional roots are explicitly inventoried."""
    required={f'opt/walter-{m}' for m in CORE_MODULES}
    required.update(f'opt/walter-{m}/{entry}' for m,entry in MODULE_ANCHORS.items())
    required.update(('root/.hermes/config.yaml','root/.hermes/.env','root/.pgpass',
                     'root/.hermes/walter-llm','root/.config/rclone/rclone.conf',
                     'root/.config/systemd/user/hermes-gateway.service',
                     'opt/openclaw/hermes_voice_bridge.py'))
    required.update(module_backup_paths(root))
    sources=set(required)
    for p in (root/'opt').glob('walter-*'):
        if p.is_dir():sources.add(str(p.relative_to(root)))
    optional=['root/.hermes/SOUL.md','root/.hermes/memories','root/.hermes/skills',
              'root/.hermes/plugins','root/.hermes/cron/jobs.json','root/.hermes/docs',
              'root/.hermes/vault','root/.hermes/hindsight','root/.hermes/webhook_subscriptions.json',
              'root/.hermes/scripts','root/.hermes/services','root/.hermes/raw-vault',
              'root/.hermes/kardex','root/.hermes/bin','root/.hermes/hooks',
              'root/.hermes/google-accounts','root/.hermes/profiles','root/.hermes/hermes-agent',
              'root/.hermes/desktop-backend.env','root/.config/systemd/user','root/.cloudflared',
              'root/.ssh/config','root/.ssh/known_hosts','root/.codex/config.toml','root/.codex/auth.json',
              'root/.codex/AGENTS.md','root/.claude/settings.json','root/.claude.json','root/CLAUDE.md',
              'etc/systemd/system','etc/asterisk','etc/logrotate.d/walter-hermes',
              'etc/iptables','etc/ssh/sshd_config.d','etc/rclone','usr/local/sbin','opt/openclaw','opt/dsh']
    absent=[]
    for n in optional:
        p=root/n
        if p.exists() or p.is_symlink():sources.add(n)
        else:absent.append(n)
    for p in (root/'usr/local/bin').glob('walter-*'):sources.add(str(p.relative_to(root)))
    # Current Desktop has a protected credential dependency outside its module directory.
    if (root/'etc/systemd/system/hermes-desktop-backend.service').exists():
        required.update(('etc/systemd/system/hermes-desktop-backend.service',
                         'etc/systemd/system/hermes-desktop-tailscale.service','root/.hermes/desktop-backend.env'))
    # Credential/config dependencies declared by Walter services, even outside module roots.
    for unit_root in ('etc/systemd/system','root/.config/systemd/user'):
        for p in (root/unit_root).rglob('*'):
            if p.suffix not in ('.service','.conf') or not p.is_file():continue
            if not any(x in str(p.relative_to(root/unit_root)).lower() for x in
                       ('walter','hermes','hindsight','raw-vault','memory-','voice-router','camoufox')):continue
            for line in p.read_text(errors='replace').splitlines():
                if not line.strip().startswith('EnvironmentFile='):continue
                for value in shlex.split(line.strip().split('=',1)[1]):
                    optional_env=value.startswith('-');value=value.lstrip('-')
                    if not value.startswith('/') or '%' in value:continue
                    name=value.lstrip('/')
                    if (root/name).exists():sources.add(name);required.add(name)
                    elif not optional_env:raise RuntimeError('service EnvironmentFile missing: '+name)
    # Preserve the SSH identities used by Walter's Mac connection; never read/print key values.
    if root==pathlib.Path('/'):
        r=subprocess.run(['ssh','-G','mac'],capture_output=True,text=True,timeout=10)
        if r.returncode:raise RuntimeError('cannot resolve Mac SSH integration')
        for line in r.stdout.splitlines():
            if line.startswith('identityfile '):
                p=pathlib.Path(line.split(' ',1)[1]).expanduser()
                if p.is_file():sources.add(str(p).lstrip('/'));required.add(str(p).lstrip('/'))
    missing=[n for n in required if not (root/n).exists()]
    if missing:raise RuntimeError('required backup sources missing: '+', '.join(sorted(missing)))
    # Parent roots subsume their children, without dereferencing symlinks.
    sources=sorted(n for n in sources if not any(n.startswith(x+'/') for x in sources if x!=n))
    return sources,sorted(required),absent

def dependencies(root):
    out={}
    envs=list((root/'opt').glob('walter-*/venv/bin/python'))
    envs += list((root/'opt').glob('walter-*/.venv/bin/python'))
    envs += [root/'root/.hermes/hermes-agent/venv/bin/python',root/'root/.hermes/hindsight-venv/bin/python',
             root/'root/walter-computer-use/.venv/bin/python',root/'root/.venv/scrapling/bin/python',
             root/'opt/walter-colab/mcp/.venv/bin/python',root/'opt/walter-colab/python/bin/python']
    code='import importlib.metadata,json; print(json.dumps(sorted({(d.metadata["Name"],d.version) for d in importlib.metadata.distributions()})))'
    for p in envs:
        if p.exists():
            r=subprocess.run([str(p),'-I','-c',code],capture_output=True,text=True,timeout=25)
            if r.returncode:raise RuntimeError('cannot inventory Python packages: '+str(p))
            out[str(p.relative_to(root))]=json.loads(r.stdout)
    return out

class DigestReader:
    def __init__(self,f):self.f=f;self.hash=hashlib.sha256()
    def read(self,n=-1):
        b=self.f.read(n);self.hash.update(b);return b

def create(output,root=pathlib.Path('/'),sources=None,required=None,include_dependencies=True):
    root=pathlib.Path(root).resolve();output=pathlib.Path(output)
    contract_state=contracts_check(root)
    if sources is None:sources,required,absent=inventory(root)
    else:absent=[];required=required or sources
    for n in required:
        if not (root/n).exists():raise RuntimeError('required backup source missing: '+n)
    entries={};snapshots=[];visited=set()
    output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    try:
      with tarfile.open(output,'w',dereference=False) as archive:
        def parents(name):
            # Preserve private ancestor modes (.hermes/.ssh), without walking unrelated files.
            # A symlinked ancestor is represented as its logical directory; explicit source
            # symlinks are preserved by add(). This keeps leaf snapshots independently restorable.
            for parent in reversed(pathlib.PurePosixPath(name).parents):
                n=str(parent)
                if n=='.' or n in entries:continue
                st=(root/n).stat();info=tarfile.TarInfo(n);info.type=tarfile.DIRTYPE
                info.mode=st.st_mode & 0o777;info.uid=st.st_uid;info.gid=st.st_gid;info.mtime=st.st_mtime
                archive.addfile(info);entries[n]={'kind':'directory','mode':info.mode}
        def add(p,name):
            if name in visited or excluded(name):return
            visited.add(name);parents(name)
            info=archive.gettarinfo(str(p),arcname=name)
            info.mode &= 0o7777
            if info.isfile():
                with p.open('rb') as f:
                    before=os.fstat(f.fileno());reader=DigestReader(f);archive.addfile(info,reader);after=os.fstat(f.fileno())
                    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                        raise RuntimeError('source changed during backup: '+name)
                    entries[name]={'kind':'file','bytes':info.size,'sha256':reader.hash.hexdigest(),'mode':info.mode}
            elif info.isdir():
                if name not in entries:archive.addfile(info)
                entries[name]={'kind':'directory','mode':info.mode}
                for child in sorted(p.iterdir()):add(child,name+'/'+child.name)
            elif info.issym() or info.islnk():
                archive.addfile(info);entries[name]={'kind':'symlink','target':info.linkname,'mode':info.mode}
            # Sockets/devices/pipes are not portable configuration payloads.
        for n in sources:add(root/n,n)
        # Consistent profile database copies, never an uncoordinated tar of SQLite/WAL.
        for db in sorted((root/'root/.hermes/profiles').glob('*/*.db')):
            name=str(db.relative_to(root))
            if not any(name.startswith(n+'/') for n in sources):continue
            with tempfile.TemporaryDirectory() as tmp:
                snap=pathlib.Path(tmp)/db.name
                source=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=20)
                dest=sqlite3.connect(snap);source.backup(dest,pages=256,sleep=.01)
                assert dest.execute('pragma quick_check').fetchone()[0]=='ok'
                dest.close();source.close()
                # Snapshot bypasses exclusion of the live database.
                info=archive.gettarinfo(str(snap),arcname=name)
                info.mode=db.stat().st_mode & 0o777
                with snap.open('rb') as f:
                    reader=DigestReader(f);archive.addfile(info,reader)
                entries[name]={'kind':'sqlite_snapshot','bytes':info.size,'sha256':reader.hash.hexdigest(),'mode':info.mode};snapshots.append(name)
        missing=[n for n in required if n not in entries]
        if missing:raise RuntimeError('required paths not archived: '+', '.join(missing))
        if contracts_check(root)!=contract_state:raise RuntimeError('module contracts changed during backup')
        manifest={'contract_check':contract_state,'version':2,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'sources':sources,'required':required,'optional_absent':absent,'entries':entries,
                  'sqlite_snapshots':snapshots,'python_packages':dependencies(root) if include_dependencies else {},
                  'separate_payloads':{'postgres':'all schemas, including walter_logs and module state',
                                       'hermes_main_state':'walter-statedb-backup snapshot without FTS',
                                       'raw_vault':'existing encrypted/clear Drive objects; restore registry from PG'},
                  'excluded_rebuildable':sorted(SKIP_PARTS)+list(SKIP_PREFIXES),
                  'restore_contract':'Preserve absolute layout; recreate venvs from package inventories; restore PG and main SQLite separately. Configuration verification is not a full clean-machine install test.'}
        body=json.dumps(manifest,ensure_ascii=False,indent=2).encode();info=tarfile.TarInfo(MANIFEST);info.size=len(body);info.mode=0o600;archive.addfile(info,io.BytesIO(body))
      return verify(output)
    except BaseException:
      output.unlink(missing_ok=True);raise

def verify(path,expected_required=()):
    entries={};manifest=None
    # Stream: don't extract secrets, don't retain the whole tar in memory.
    with tarfile.open(fileobj=path if hasattr(path,'read') else None,name=None if hasattr(path,'read') else path,mode='r|') as archive:
        for item in archive:
            name=item.name.rstrip('/')
            if name.startswith('/') or '..' in pathlib.PurePosixPath(name).parts:raise ValueError('unsafe archive path')
            if name==MANIFEST:
                manifest=json.load(archive.extractfile(item));continue
            if name in entries:raise ValueError('duplicate archive member: '+name)
            if item.isfile():
                h=hashlib.sha256();f=archive.extractfile(item)
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
                entries[name]={'sha256':h.hexdigest(),'bytes':item.size,'mode':item.mode}
            elif item.isdir():entries[name]={'kind':'directory','mode':item.mode}
            elif item.issym() or item.islnk():entries[name]={'kind':'symlink','target':item.linkname,'mode':item.mode}
            else:raise ValueError('unsupported archive member: '+name)
    if not manifest or manifest.get('version') not in (1,2):raise ValueError('missing/unsupported backup manifest')
    declared=manifest['entries']
    if set(declared)!=set(entries):raise ValueError('archive members differ from manifest')
    for name,record in declared.items():
        actual=entries[name]
        if record['kind'] in ('file','sqlite_snapshot'):
            if record['sha256']!=actual.get('sha256') or record['bytes']!=actual.get('bytes'):raise ValueError('checksum mismatch: '+name)
        elif any(actual.get(k)!=v for k,v in record.items()):raise ValueError('member metadata mismatch: '+name)
        if 'mode' in record and record['mode']!=actual['mode']:raise ValueError('mode mismatch: '+name)
    missing=(set(manifest['required'])|set(expected_required))-set(entries)
    if missing:raise ValueError('required paths missing: '+', '.join(sorted(missing)))
    return {'ok':True,'entries':len(entries),'required':len(manifest['required']),
            'modules':sorted(n for n in manifest['sources'] if n.startswith('opt/walter-')),
            'sqlite_snapshots':len(manifest['sqlite_snapshots']),'python_environments':len(manifest['python_packages'])}

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['create','verify']);p.add_argument('path');p.add_argument('--check-current',action='store_true');a=p.parse_args()
    if a.action=='create':result=create(a.path)
    else:
        import sys
        expected=inventory(pathlib.Path('/'))[1] if a.check_current else ()
        result=verify(sys.stdin.buffer if a.path=='-' else a.path,expected)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
