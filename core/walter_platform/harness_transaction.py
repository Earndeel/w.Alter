"""Small recoverable config transaction. Previews and manifests never contain values.

Back up every preimage before the first mutation; compare preimages before writes;
rollback refuses to overwrite any file edited since installation. Existing config
symlinks are preserved and checked again before commit. This is not a database
transaction: interruption recovery is the explicit backup manifest.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import os
import tempfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data, mode=0o600):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.walter-',dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def file_change(path, text, component):
    path=Path(path).absolute()
    if path.is_symlink() and not path.exists():
        raise ValueError('dangling configuration link; repair it before installing')
    before=path.read_bytes() if path.exists() else None
    new=text.encode()
    return {'path':str(path),'target':str(path.resolve()),'link':os.readlink(path) if path.is_symlink() else None,
            'kind':'file','component':component,'before':before,'after':new,
            'before_mode':path.stat().st_mode&0o777 if before is not None else None,
            'mode':path.stat().st_mode&0o777 if before is not None else 0o600,
            'changed':before!=new}


def link_change(path, target, component):
    path=Path(path).absolute();target=Path(target).absolute()
    if path==target or (path.is_symlink() and path.resolve()==target.resolve()):
        return None
    if path.exists() or path.is_symlink():
        raise ValueError('existing adapter or credential location differs; refusing replacement')
    return {'path':str(path),'target':str(path),'kind':'symlink','link':str(target),
            'component':component,'before':None,'after':None,'changed':True,'mode':0o600}


def _check_before(change):
    path=Path(change['path'])
    if change['kind']=='symlink':
        if path.exists() or path.is_symlink():raise RuntimeError('integration link appeared during preparation')
        return
    if (os.readlink(path) if path.is_symlink() else None)!=change['link']:
        raise RuntimeError('configuration symlink changed during preparation')
    target=Path(change['target'])
    if (target.read_bytes() if target.exists() else None)!=change['before']:
        raise RuntimeError('configuration changed during preparation')
    if change['before'] is not None and (target.stat().st_mode&0o777)!=change.get('before_mode',change['mode']):
        raise RuntimeError('configuration mode changed during preparation')


def commit(changes, *, backup_root, host):
    changes=[x for x in changes if x and x['changed']]
    for change in changes:_check_before(change)
    root=Path(backup_root)/('harness-install-'+host+'-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    root.mkdir(parents=True,mode=0o700)
    rows=[]
    for n,c in enumerate(changes):
        name=f'{n:03}.before'
        if c['before'] is not None:atomic(root/name,c['before'])
        rows.append({k:c[k] for k in ('path','target','link','kind','component','mode')}|
                    {'existed':c['before'] is not None,'before_file':name,
                     'before_sha256':digest(c['before']) if c['before'] is not None else None,
                     'before_mode':c.get('before_mode',c['mode']),
                     'after_sha256':digest(c['after']) if c['kind']=='file' else None,'applied':False})
    manifest={'version':1,'harness':host,'state':'prepared','files':rows}
    def save():atomic(root/'manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())
    save()
    try:
        for c,row in zip(changes,rows):
            _check_before(c)
            # Mark intent before the operation, so a killed process can recover it.
            row['applied']=True;manifest['state']='applying';save()
            if c['kind']=='file':atomic(Path(c['target']),c['after'],c['mode'])
            else:
                path=Path(c['path']);path.parent.mkdir(parents=True,exist_ok=True);path.symlink_to(c['link'])
        manifest['state']='applied';save()
    except Exception:
        # Recover only completed own writes, keeping any concurrently changed file intact.
        try:rollback(root,apply=True,allow_preimage=True)
        except Exception:pass
        raise RuntimeError('composition write failed; transaction backup: '+str(root)) from None
    return str(root)


def rollback(backup, *, apply=False, allow_preimage=False):
    root=Path(backup);mp=root/'manifest.json';m=json.loads(mp.read_text())
    if m.get('version')!=1 or not isinstance(m.get('files'),list):raise ValueError('unsupported transaction backup')
    selected=[];conflicts=[]
    for row in m['files']:
        if not row.get('applied'):continue
        path=Path(row['path']);target=Path(row['target'])
        if row['kind']=='symlink':
            own=path.is_symlink() and os.readlink(path)==row['link']
            before=not path.exists() and not path.is_symlink()
        else:
            stable_link=(os.readlink(path) if path.is_symlink() else None)==row['link']
            data=target.read_bytes() if target.is_file() else None
            current_mode=(target.stat().st_mode&0o777) if data is not None else None
            own=stable_link and data is not None and digest(data)==row['after_sha256'] and current_mode==row['mode']
            before=stable_link and ((data is None and not row['existed']) or
                                   (data is not None and digest(data)==row['before_sha256'] and current_mode==row.get('before_mode',row['mode'])))
            if row['existed']:
                name=row['before_file']
                if Path(name).name!=name or digest((root/name).read_bytes())!=row['before_sha256']:
                    raise ValueError('backup preimage is invalid')
        if before and (allow_preimage or m['state'] in ('prepared','applying','rolled_back')):continue
        if not own:conflicts.append(row['path'])
        else:selected.append(row)
    result={'ok':not conflicts,'applied':False,'backup':str(root),'conflicts':conflicts,
            'changes':[{'path':r['path'],'component':r['component']} for r in selected]}
    if conflicts or not apply:return result
    for row in reversed(selected):
        target=Path(row['target'])
        if row['existed']:atomic(target,(root/row['before_file']).read_bytes(),row.get('before_mode',row['mode']))
        else:target.unlink(missing_ok=True)
    m['state']='rolled_back';atomic(mp,(json.dumps(m,indent=2)+'\n').encode())
    result['applied']=True
    return result
