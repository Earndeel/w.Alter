"""Offline source release and isolated installation; no runtime or account activation.

This is deliberately separate from encrypted backup restoration. The source bundle
excludes credentials, runtime state, skill content and large model/env artifacts.
Missing dependency wheels/binaries remain explicit prerequisites. Never downloads.
"""
from __future__ import annotations
import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from . import contracts
from .harness_transaction import atomic, commit, file_change, rollback

MANIFEST='walter-release.json'
SOURCES=Path(__file__).resolve().parents[1]/'modules/release-sources.json'
SKIP_DIRS={'.git','.venv','venv','node_modules','__pycache__','.cache','.pytest_cache','.mypy_cache','.ruff_cache',
           'archive','reports','logs','sessions','backups','cache','locks','models','python','.hermes-runtime','drafts','.worktrees'}
SOURCE_SUFFIXES={'.py','.sh','.mjs','.js','.ts','.tsx','.html','.css','.sql','.toml','.yaml','.yml','.json','.md','.txt','.lock','.service','.timer','.conf','.in'}
LOCK_NAMES={'requirements.txt','requirements.lock','uv.lock','poetry.lock','package-lock.json','pnpm-lock.yaml','yarn.lock','pyproject.toml','package.json'}
NAME=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.+-]*\Z')
CREDENTIAL=re.compile(rb'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----|\b(?:sk-proj-|sk-or-v1-|ghp_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]{20,}|://[^\s/@:]+:[^\s/@]+@')
MAX_FILE=16*1024*1024


def _hash(data):return hashlib.sha256(data).hexdigest()
def _json(data):return (json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()
def _relative(name):
    if not isinstance(name,str):raise ValueError('unsafe release path')
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or str(p)!=name or name in ('','.'):raise ValueError('unsafe release path')
    return p


def _safe(root,name):
    p=root/str(_relative(name))
    for q in (p,*p.parents):
        if q==root:break
        if q.is_symlink():raise ValueError('release path contains a symlink')
    if not p.resolve().is_relative_to(root.resolve()):raise ValueError('release path escapes root')
    return p


def _excluded(logical):
    p=PurePosixPath(logical);name=p.name.lower()
    if any(x in SKIP_DIRS for x in p.parts):return True
    if str(p).startswith('opt/walter-skills/skills/'):return True
    if name.startswith(('.env','.credentials','.secrets')) or name in ('auth.json','credentials.json','rclone.conf','s3.env'):return True
    if name.endswith(('.env','.key','.pem','.p12','.pfx','.age','.db','.sqlite','.sqlite3','.log','.bak')):return True
    if any(x in name for x in ('credential','password','recovery.agekey')):return True
    return False


def _source(path,logical):
    if _excluded(logical) or path.is_symlink() or not path.is_file():return False
    p=PurePosixPath(logical)
    return (p.suffix in SOURCE_SUFFIXES or p.name in ('.gitignore','.python-version','Dockerfile','Makefile')
            or 'bin' in p.parts or 'LICENSE' in p.name)


def _read_source(path):
    if path.stat().st_size>MAX_FILE:raise ValueError('source file exceeds release size limit')
    data=path.read_bytes()
    if CREDENTIAL.search(data):raise ValueError('credential-like content in release source; excluded from export')
    try:data.decode('utf-8')
    except UnicodeError:raise ValueError('release source is not UTF-8 text') from None
    return data


def _command(argv,timeout=30):
    r=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    if r.returncode:raise ValueError('local release inventory command failed')
    return r.stdout


def _runtime_inventory(root,roots,execute):
    out={'python':[],'node':[],'system':{'system':platform.system(),'machine':platform.machine()},
         'execution':'local interpreter metadata only' if execute else 'not executed'}
    code='import importlib.metadata,json,sys;print(json.dumps({"version":list(sys.version_info[:3]),"packages":sorted({(d.metadata["Name"],d.version) for d in importlib.metadata.distributions()})}))'
    for logical in roots:
        p=root/logical
        if execute:
            for rel in ('venv/bin/python','.venv/bin/python','mcp/.venv/bin/python'):
                interpreter=p/rel
                if not interpreter.exists():continue
                data=json.loads(_command([str(interpreter),'-I','-c',code]))
                if any(not NAME.fullmatch(name) or not NAME.fullmatch(version) for name,version in data['packages']):
                    raise ValueError('invalid installed package identity')
                out['python'].append({'path':str(PurePosixPath(logical)/str(PurePosixPath(rel).parent.parent)),**data})
    # Harness runtimes are prerequisites, not vendored module sources or a custom runtime.
    for logical in ('opt/dsh/node_modules/@deepseek-ai/dsh/package.json',):
        p=root/logical
        if p.is_file():
            d=json.loads(p.read_text());out['node'].append({'path':logical,'name':d.get('name'),'version':d.get('version')})
    return out


def _wheels(path):
    rows=[]
    if path is None:return rows
    for p in sorted(Path(path).glob('*.whl')):
        if p.is_symlink():raise ValueError('wheel symlink is not allowed')
        if p.stat().st_size>1024*1024*1024:raise ValueError('wheel exceeds size limit')
        with zipfile.ZipFile(p) as z:
            metadata=[n for n in z.namelist() if n.endswith('.dist-info/METADATA')]
            if len(metadata)!=1:raise ValueError('wheel has invalid metadata')
            from email.parser import BytesParser
            data=BytesParser().parsebytes(z.read(metadata[0]));name=data.get('Name','');version=data.get('Version','')
            if not NAME.fullmatch(name) or not NAME.fullmatch(version):raise ValueError('invalid wheel identity')
        tail=p.name[:-4].rsplit('-',3)
        if len(tail)!=4:raise ValueError('invalid wheel filename')
        tags=[a+'-'+b+'-'+c for a in tail[-3].split('.') for b in tail[-2].split('.') for c in tail[-1].split('.')]
        rows.append({'file':p.name,'name':name,'version':version,'tags':tags,'sha256':_hash(p.read_bytes()),'bytes':p.stat().st_size})
    return rows


def build(destination, *, apply=False, root='/', catalog=None, wheelhouse=None, include_dependencies=True, sources=None):
    """Preview/export a private directory bundle; never exports backup credentials."""
    root=Path(root).resolve();destination=Path(destination).absolute()
    catalog=Path(catalog or root/'opt/walter-core/modules/catalog.json')
    compiled=contracts.compile_registry(catalog,root=root)
    policy=json.loads(Path(sources or SOURCES).read_text())
    if policy.get('version')!=1:raise ValueError('unsupported source policy')
    roots=sorted({str(PurePosixPath(m['root'])).lstrip('/') for m in compiled['modules']})
    selected_by_root={}
    excluded_by_path=set(policy.get('exclude_paths',[]))
    restored=set(policy.get('restored_anchors',[]))
    for module in compiled['modules']:
        logical=module['root'].lstrip('/')
        selected=policy.get('modules',{}).get(module['id'],policy.get('roots',{}).get(logical,[]))
        selected_by_root.setdefault(logical,set()).update(selected)
        restored.update(logical+'/'+str(_relative(p)) for p in policy.get('restored_module_anchors',{}).get(module['id'],[]))
        excluded_by_path.update(logical+'/'+str(_relative(p)) for p in policy.get('exclude_module_paths',{}).get(module['id'],[]))
    for logical in roots:
        if not (logical.startswith(('opt/walter-','walter/')) or logical=='opt/openclaw'):raise ValueError('unsupported source root')
        if destination.resolve().is_relative_to(root/logical):raise ValueError('release destination is inside a source module')
        if not selected_by_root[logical]:raise ValueError('module has no reviewed source allowlist')
    entries=[];versions={};skipped=0
    for logical in roots:
        base=_safe(root,logical)
        if not base.is_dir():raise ValueError('module source root missing')
        if (base/'.git').exists():
            versions[logical]={'commit':_command(['git','-C',str(base),'rev-parse','HEAD']).strip(),
                              'dirty':bool(_command(['git','-C',str(base),'status','--porcelain']).strip())}
        else:versions[logical]={'commit':None,'dirty':None,'provenance':'unversioned source snapshot'}
        candidates=set()
        for relative in [*selected_by_root[logical],'contracts']:
            selected=_safe(root,logical+'/'+str(_relative(relative)))
            if not selected.exists():continue
            if selected.is_file():candidates.add(selected);continue
            for folder,dirs,files in os.walk(selected,followlinks=False):
                dirs[:]=sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(folder)/d).is_symlink()
                               and not _excluded(str((Path(folder)/d/'_').relative_to(root))))
                candidates.update(Path(folder)/name for name in files)
        for p in sorted(candidates):
            rel=str(p.relative_to(root))
            if rel in excluded_by_path:skipped+=1;continue
            if not _source(p,rel):skipped+=1;continue
            data=_read_source(p)
            entries.append({'path':rel,'sha256':_hash(data),'bytes':len(data),'mode':p.stat().st_mode&0o777})
    anchors={a.lstrip('/') for m in compiled['modules'] for a in m['anchors']}
    missing=sorted(anchors-{e['path'] for e in entries}-restored)
    if missing:raise ValueError('required module source anchor excluded or missing')
    runtimes=_runtime_inventory(root,roots,include_dependencies)
    wheels=_wheels(wheelhouse)
    manifest={'version':1,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope':'module source and non-secret configuration; no data, credentials or running services',
              'modules':compiled,'files':sorted(entries,key=lambda x:x['path']),'git':versions,'runtimes':runtimes,'wheels':wheels,
              'source_policy':policy,'required_restored_anchors':sorted(anchors&restored),
              'lockfiles':[e['path'] for e in entries if PurePosixPath(e['path']).name in LOCK_NAMES],
              'excluded':['credentials and auth files','raw databases/logs/session history','skills content store','models','venvs/node_modules','git history','symlinks'],
              'prerequisites':['compatible OS/architecture, Python and Node runtimes','offline wheels for exact Python package inventory',
                               'DSH/Hermes/Codex/Claude host distributions and their dependencies','Postgres/extensions and required local services',
                               'encrypted data/config/secret restoration and module migrations','per-capability acceptance before activation']}
    result={'ok':True,'applied':False,'destination':str(destination),'modules':len(compiled['modules']),
            'files':len(entries),'bytes':sum(e['bytes'] for e in entries),'skipped_files':skipped,
            'python_environments':len(runtimes['python']),'wheels':len(wheels),'prerequisites':manifest['prerequisites']}
    if not apply:return result
    if destination.exists() or destination.is_symlink():raise ValueError('release destination already exists')
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.walter-release-',dir=destination.parent))
    try:
        for row in entries:
            data=_read_source(_safe(root,row['path']))
            if _hash(data)!=row['sha256']:raise ValueError('source changed during release build')
            atomic(stage/'payload'/row['path'],data,row['mode'])
        for row in wheels:
            source=Path(wheelhouse)/row['file'];data=source.read_bytes()
            if _hash(data)!=row['sha256']:raise ValueError('wheel changed during release build')
            atomic(stage/'wheelhouse'/row['file'],data)
        if contracts.compile_registry(catalog,root=root)!=compiled:raise ValueError('contracts changed during release build')
        atomic(stage/MANIFEST,_json(manifest))
        os.rename(stage,destination)
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True);raise
    result['applied']=True;result['manifest_sha256']=_hash((destination/MANIFEST).read_bytes());return result


def _inspect(bundle):
    bundle=Path(bundle).absolute()
    if bundle.is_symlink() or not bundle.is_dir():raise ValueError('bundle must be a real directory')
    p=_safe(bundle,MANIFEST)
    if p.stat().st_size>32*1024*1024:raise ValueError('release manifest too large')
    m=json.loads(p.read_text())
    if m.get('version')!=1 or not isinstance(m.get('files'),list):raise ValueError('unsupported release manifest')
    for module in m['modules']['modules']:
        contracts.validate(module)
        if not (module['root'].startswith(('/opt/walter-','/walter/')) or module['root']=='/opt/openclaw'):raise ValueError('unsupported release module root')
    roots={v['root'].lstrip('/') for v in m['modules']['modules']}
    for env in m['runtimes']['python']:
        logical=str(_relative(env['path']))
        if not any(logical.startswith(r+'/') for r in roots) or PurePosixPath(logical).name not in ('venv','.venv'):raise ValueError('invalid environment location')
        if any(not isinstance(n,str) or not isinstance(v,str) or not NAME.fullmatch(n) or not NAME.fullmatch(v) for n,v in env['packages']):raise ValueError('invalid environment package identity')
    seen=set()
    for row in m['files']:
        name=str(_relative(row['path']))
        if name in seen or not any(name.startswith(r+'/') for r in roots):raise ValueError('duplicate or undeclared release path')
        if _excluded(name):raise ValueError('release includes a forbidden state or credential path')
        seen.add(name);p=_safe(bundle,'payload/'+name)
        if not p.is_file() or p.stat().st_size!=row['bytes'] or row['bytes']>MAX_FILE:raise ValueError('release file is missing or has wrong size')
        if type(row['mode']) is not int or not 0<=row['mode']<=0o777:raise ValueError('invalid release file mode')
        if _hash(_read_source(p))!=row['sha256']:raise ValueError('release file hash mismatch')
    required={a.lstrip('/') for module in m['modules']['modules'] for a in module['anchors']}
    restored=set(m.get('required_restored_anchors',[]))
    permitted_restored=set(m.get('source_policy',{}).get('restored_anchors',[]))
    for module in m['modules']['modules']:
        permitted_restored.update(module['root'].lstrip('/')+'/'+str(_relative(p)) for p in m.get('source_policy',{}).get('restored_module_anchors',{}).get(module['id'],[]))
    if not restored.issubset(permitted_restored) or required-seen-restored:raise ValueError('release is missing required module source anchors')
    for module in m['modules']['modules']:
        for anchor in module['anchors']:
            if '/contracts/' in anchor and anchor.endswith('.json'):
                p=_safe(bundle,'payload/'+anchor.lstrip('/'))
                if contracts.expand(json.loads(p.read_text()),module['root'],module['contract']['target_root'])!=module:raise ValueError('release manifest differs from owner contract payload')
    core=next((v['root'] for v in m['modules']['modules'] if v['id']=='core'),'/opt/walter-core')
    catalog=_safe(bundle,'payload/'+core.lstrip('/')+'/modules/catalog.json')
    if catalog.is_file() and contracts.compile_registry(catalog,root=bundle/'payload')!=m['modules']:raise ValueError('release catalog differs from owner contracts')
    for wheel in m.get('wheels',[]):
        if Path(wheel['file']).name!=wheel['file']:raise ValueError('unsafe wheel path')
        p=_safe(bundle,'wheelhouse/'+wheel['file'])
        if not p.is_file() or p.stat().st_size!=wheel['bytes'] or wheel['bytes']>1024*1024*1024:raise ValueError('invalid wheel size')
        if _hash(p.read_bytes())!=wheel['sha256']:raise ValueError('wheel hash mismatch')
    wheel_dir=bundle/'wheelhouse'
    if wheel_dir.exists() and {p.name for p in wheel_dir.iterdir()}!={w['file'] for w in m.get('wheels',[])}:raise ValueError('undeclared wheelhouse content')
    if _wheels(wheel_dir)!=m.get('wheels',[]):raise ValueError('wheel identity or compatibility metadata mismatch')
    return bundle,m,_hash((bundle/MANIFEST).read_bytes())


def inspect(bundle):
    bundle,m,sha=_inspect(bundle)
    return {'ok':True,'bundle':str(bundle),'manifest_sha256':sha,'modules':len(m['modules']['modules']),
            'files':len(m['files']),'bytes':sum(x['bytes'] for x in m['files']),
            'python_environments':len(m['runtimes']['python']),'wheels':len(m.get('wheels',[])),
            'prerequisites':m['prerequisites'],'scope':m['scope']}


def _target(root):
    p=Path(root).absolute()
    if p in (Path('/'),Path('/opt'),Path('/root'),Path('/usr'),Path('/etc'),Path('/var'),Path('/walter')):raise ValueError('release installation requires a dedicated staging root')
    if p.resolve()!=p:raise ValueError('installation root must not contain symlinks')
    return p


def install(bundle, root, *, apply=False, backup_root=None):
    """Install source into an isolated filesystem root, preserving foreign files."""
    bundle,m,sha=_inspect(bundle);root=_target(root)
    receipt_path=_safe(root,'.walter-release/receipt.json')
    previous=json.loads(receipt_path.read_text()) if receipt_path.exists() else {'files':[]}
    owned={x['path']:x['sha256'] for x in previous.get('files',[])}
    changes=[];conflicts=[]
    for row in m['files']:
        target=_safe(root,row['path']);source=_safe(bundle,'payload/'+row['path'])
        if target.exists():
            if not target.is_file():raise ValueError('installation path is not a regular file')
            actual=_hash(target.read_bytes());actual_mode=target.stat().st_mode&0o777
            previous_row=next((r for r in previous.get('files',[]) if r['path']==row['path']),{})
            matches_new=actual==row['sha256'] and actual_mode==row['mode']
            matches_owned=actual==owned.get(row['path']) and actual_mode==previous_row.get('mode')
            if not matches_new and not matches_owned:conflicts.append(row['path']);continue
        content=_read_source(source)
        if _hash(content)!=row['sha256']:raise ValueError('bundle source changed during installation preparation')
        change=file_change(target,content.decode('utf-8'),'release-source');change['mode']=row['mode']
        change['changed']=change['changed'] or (target.exists() and target.stat().st_mode&0o777!=row['mode']);changes.append(change)
    receipt={'version':1,'manifest_sha256':sha,'files':m['files'],'scope':'source installation only'}
    changes.append(file_change(receipt_path,_json(receipt).decode(),'release-receipt'))
    pending=[x for x in changes if x['changed']]
    result={'ok':not conflicts,'applied':False,'root':str(root),'changed':bool(pending),'changes':len(pending),
            'conflicts':conflicts,'manifest_sha256':sha,'prerequisites':m['prerequisites'],
            'scope':'source installed; environments, data restoration and activation remain separate',
            'retained_previous_files':sorted(set(owned)-{x['path'] for x in m['files']})}
    if apply and result['ok'] and pending:
        if _hash((bundle/MANIFEST).read_bytes())!=sha:raise ValueError('release manifest changed during preparation')
        result['backup']=commit(changes,backup_root=backup_root or root/'.walter-release/backups',host='release')
        result['applied']=True
    return result


def _packages(python):
    code='import importlib.metadata,json,re;print(json.dumps({re.sub(r"[-_.]+","-",d.metadata["Name"]).lower():d.version for d in importlib.metadata.distributions()}))'
    return json.loads(_command([str(python),'-I','-c',code]))


def _matches_environment(target,expected):
    receipt=target/'.walter-environment.json'
    if not receipt.is_file() or json.loads(receipt.read_text())!=expected:return False
    if not (target/'bin/python').exists():return False
    actual=_packages(target/'bin/python')
    return all(actual.get(r.split('==')[0])==r.split('==')[1] for r in expected['requirements'])


def environment_plan(bundle, root, *, python=sys.executable, environments=None):
    bundle,m,sha=_inspect(bundle);root=_target(root)
    known={env['path'] for env in m['runtimes']['python']}
    selected=known if environments is None else set(environments)
    if isinstance(environments,str) or not selected.issubset(known):raise ValueError('unknown environment selection')
    info=json.loads(_command([str(python),'-I','-c',
        'import sys,json;print(json.dumps(list(sys.version_info[:2])))']))
    tag_code='try:\n from packaging.tags import sys_tags\nexcept ImportError:\n from pip._vendor.packaging.tags import sys_tags\nimport json;print(json.dumps([str(t) for t in sys_tags()]))'
    try:tags=set(json.loads(_command([str(python),'-I','-c',tag_code])))
    except ValueError:tags=set()
    available={re.sub(r'[-_.]+','-',w['name']).lower()+'=='+w['version'] for w in m.get('wheels',[]) if tags.intersection(w['tags'])}
    rows=[]
    for env in m['runtimes']['python']:
        if env['path'] not in selected:continue
        if not any(env['path'].startswith(v['root'].lstrip('/')+'/') for v in m['modules']['modules']):raise ValueError('environment outside declared module roots')
        if any(not NAME.fullmatch(n) or not NAME.fullmatch(v) for n,v in env['packages']):raise ValueError('invalid environment package identity')
        target=_safe(root,env['path']);requirements=[re.sub(r'[-_.]+','-',n).lower()+'=='+v for n,v in env['packages'] if n.lower() not in ('pip','setuptools','wheel')]
        missing=sorted(set(requirements)-available)
        expected={'manifest_sha256':sha,'requirements':requirements}
        existing_ok=_matches_environment(target,expected) if target.exists() else None
        rows.append({'path':str(target),'logical_path':env['path'],'packages':len(requirements),'requirements':requirements,
                     'missing_wheels':missing,'python_compatible':info==env['version'][:2],
                     'existing':target.exists(),'existing_matches':existing_ok,
                     'ready':not missing and info==env['version'][:2] and existing_ok is not False})
    return {'ok':all(x['ready'] for x in rows),'root':str(root),'manifest_sha256':sha,'environments':rows,
            'all_environments_selected':selected==known,'not_selected':sorted(known-selected),
            'scope':'exact package versions and compatible local wheels; native system libraries and Node dependencies remain prerequisites'}


def install_environments(bundle, root, *, python=sys.executable, apply=False, environments=None):
    """Create missing Python environments offline; never replace an existing env.

    Wheel distributions are trusted local release artifacts, not arbitrary input.
    Existing environments are checked against receipt plus installed versions.
    Package file tampering beyond version metadata is not detected by that check.
    """
    plan=environment_plan(bundle,root,python=python,environments=environments);plan['applied']=False
    if not apply or not plan['ok']:return plan
    bundle,m,sha=_inspect(bundle);created=[]
    for row in plan['environments']:
        target=Path(row['path']);receipt=target/'.walter-environment.json'
        expected={'manifest_sha256':plan['manifest_sha256'],'requirements':row['requirements']}
        if target.exists():
            if _matches_environment(target,expected):continue
            raise ValueError('existing environment differs; refusing replacement')
        target.parent.mkdir(parents=True,exist_ok=True)
        # venv entrypoint scripts embed their path: build at the final staged location.
        target.mkdir(mode=0o700)
        try:
            _command([str(python),'-I','-m','venv',str(target)],timeout=120)
            if row['requirements']:
                locked=[]
                for requirement in row['requirements']:
                    hashes=['--hash=sha256:'+w['sha256'] for w in m['wheels'] if re.sub(r'[-_.]+','-',w['name']).lower()+'=='+w['version']==requirement]
                    locked.append(requirement+' '+' '.join(hashes))
                lock=target/'.walter-requirements.txt';atomic(lock,('\n'.join(locked)+'\n').encode())
                _command([str(target/'bin/python'),'-I','-m','pip','--isolated','install','--no-index','--no-deps','--only-binary=:all:',
                          '--require-hashes','--disable-pip-version-check','--no-cache-dir','--find-links',str(bundle/'wheelhouse'),'-r',str(lock)],timeout=180)
            actual=_packages(target/'bin/python')
            if any(actual.get(r.split('==')[0])!=r.split('==')[1] for r in row['requirements']):raise ValueError('installed environment package verification failed')
            atomic(receipt,_json(expected));created.append(str(target))
        except BaseException:
            # Only this invocation's previously nonexistent env is quarantined, never foreign data.
            failed=target.with_name(target.name+'.failed-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            target.rename(failed);raise ValueError('offline environment preparation failed; partial environment quarantined') from None
    plan['applied']=bool(created);plan['created']=created;return plan
