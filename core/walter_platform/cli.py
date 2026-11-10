from __future__ import annotations
import argparse,json,sys
from . import registry,harness

def main(argv=None):
    p=argparse.ArgumentParser(prog='walter',description='Walter module composition and harness integration')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('modules','status','check','backup-paths'):sub.add_parser(name)
    c=sub.add_parser('contracts');cs=c.add_subparsers(dest='contract_action',required=True)
    for name in ('check','render'):
        q=cs.add_parser(name);q.add_argument('--catalog');q.add_argument('--root',default='/')
        if name=='render':q.add_argument('--format',choices=('json','markdown'),default='json')
    q=sub.add_parser('path');q.add_argument('module');q.add_argument('parts',nargs='*')
    q=sub.add_parser('layout');q.add_argument('layout_action',nargs='?',choices=('show','move','verify','rollback','env'),default='show');q.add_argument('target',nargs='?',help='module (move) or backup folder (verify, rollback)');q.add_argument('--to');q.add_argument('--apply',action='store_true');q.add_argument('--backup');q.add_argument('--allow-dirty',action='store_true');q.add_argument('--no-systemd',action='store_true')
    q=sub.add_parser('standby');q.add_argument('standby_action',nargs='?',choices=('status','start','stop','ensure','sweep'),default='status');q.add_argument('group',nargs='?');q.add_argument('--by',default='agent')
    q=sub.add_parser('instance');q.add_argument('instance_action',nargs='?',choices=('show','check','path','render','config','harness'),default='show');q.add_argument('parts',nargs='*')
    q=sub.add_parser('present');q.add_argument('level',choices=('notes','note','catalog','summary','manifest','guide','index'));q.add_argument('module',nargs='?');q.add_argument('--form',choices=('full','m0'),default='full');q.add_argument('--m1',action='append',default=[]);q.add_argument('--level',choices=('M0','M1'),default='M1');q.add_argument('--section',default='');q.add_argument('--offset',type=int,default=0);q.add_argument('--limit',type=int,default=20)
    sub.add_parser('matrix')
    q=sub.add_parser('engine');q.add_argument('engine_action',choices=('kernel',));q.add_argument('--install');q.add_argument('--home')
    sub.add_parser('doctor')
    q=sub.add_parser('export');q.add_argument('destination');q.add_argument('--apply',action='store_true');q.add_argument('--wheelhouse')
    q=sub.add_parser('install');q.add_argument('bundle');q.add_argument('--root',required=True);q.add_argument('--apply',action='store_true');q.add_argument('--backup-root')
    r=sub.add_parser('release');rs=r.add_subparsers(dest='release_action',required=True)
    q=rs.add_parser('inspect');q.add_argument('bundle')
    q=rs.add_parser('environments');q.add_argument('bundle');q.add_argument('--root',required=True);q.add_argument('--python',default=sys.executable);q.add_argument('--apply',action='store_true')
    q=rs.add_parser('rollback');q.add_argument('backup');q.add_argument('--apply',action='store_true')
    h=sub.add_parser('harness');hs=h.add_subparsers(dest='action',required=True)
    for name in ('check','attach','install'):
        q=hs.add_parser(name);q.add_argument('host',choices=harness.HOSTS);q.add_argument('--home')
        if name in ('attach','install'):q.add_argument('--apply',action='store_true');q.add_argument('--backup-root')
    rollback=hs.add_parser('rollback');rollback.add_argument('backup');rollback.add_argument('--apply',action='store_true')
    a=p.parse_args(argv)
    try:
        if a.command=='modules':out=registry.load()
        elif a.command=='backup-paths':out={'paths':registry.backup_paths()}
        elif a.command in ('status','check'):out=registry.report(scan=a.command=='check',live=a.command=='status')
        elif a.command=='contracts':
            from . import contracts
            if a.contract_action=='check':out=contracts.check(a.catalog,root=a.root)
            else:
                out=contracts.compile_registry(a.catalog,root=a.root)
                if a.format=='markdown':
                    print(contracts.render_markdown(out),end='');return 0
        elif a.command=='path':
            from . import paths
            print(paths.module_path(a.module,*a.parts));return 0
        elif a.command=='layout':
            from . import paths
            if a.layout_action=='show':out=paths.layout()
            else:
                from . import move
                if not a.target:raise ValueError('usage: walter layout '+a.layout_action+' <'+('module' if a.layout_action=='move' else 'backup')+'>')
                if a.layout_action=='move':
                    m=move.Move(a.target,a.to)
                    if not a.apply:out=m.plan()
                    else:
                        if not a.backup:raise ValueError('--apply needs --backup <folder> (instance backups/changes)')
                        out=m.apply(a.backup,systemd=not a.no_systemd,allow_dirty=a.allow_dirty)
                elif a.layout_action=='env':
                    if not a.to:raise ValueError('usage: walter layout env <environment> --to <dest> [--apply --backup <folder>]')
                    if not a.apply:out=move.env_plan(a.target,a.to)
                    else:
                        if not a.backup:raise ValueError('--apply needs --backup <folder>')
                        man=move.env_apply(a.target,a.to,a.backup);out={**man,'verify':move.env_verify(man)}
                elif a.layout_action=='verify':
                    import pathlib
                    man=json.loads((pathlib.Path(a.target)/'manifest.json').read_text())
                    out=move.Move.from_manifest(man).verify(man)
                else:
                    import pathlib
                    kind=json.loads((pathlib.Path(a.target)/'manifest.json').read_text()).get('kind')
                    out=move.env_rollback(a.target) if kind=='env' else move.rollback(a.target,systemd=not a.no_systemd)
        elif a.command=='standby':
            from . import standby
            act=a.standby_action
            if act in ('start','stop','ensure') and not a.group:raise ValueError('usage: walter standby '+act+' <group>')
            out=(standby.status() if act=='status' else standby.sweep() if act=='sweep' else
                 standby.start(a.group,by=a.by) if act=='start' else standby.ensure(a.group,by=a.by) if act=='ensure' else
                 standby.stop(a.group))
        elif a.command=='instance':
            from . import instance
            if a.instance_action=='path':
                print(instance.path(*a.parts));return 0
            if a.instance_action=='config':
                if len(a.parts)!=2:raise ValueError('usage: walter instance config <module> <file>')
                print(instance.config(*a.parts));return 0
            if a.instance_action=='harness':
                if len(a.parts)!=1:raise ValueError('usage: walter instance harness <runtime>')
                print(instance.harness(a.parts[0]));return 0
            if a.instance_action=='render':
                sys.stdout.write(instance.render(sys.stdin.read()));return 0
            out=instance.check() if a.instance_action=='check' else instance.show()
        elif a.command=='present':
            from . import presentation
            if a.level in ('note','summary','manifest','guide','index') and not a.module:raise ValueError('usage: walter present '+a.level+' <module>')
            if a.level in ('summary','manifest','guide'):
                print(getattr(presentation,a.level)(a.module));return 0
            m1=[x for v in a.m1 for x in v.split(',') if x]
            out=(presentation.notes(a.form,m1) if a.level=='notes' else presentation.catalog() if a.level=='catalog' else
                 presentation.note(a.module,a.level) if a.level=='note' else
                 presentation.index(a.module,a.section,a.offset,a.limit))
        elif a.command=='engine':
            from . import engine
            out=engine.kernel(a.install,a.home)
        elif a.command=='matrix':
            from . import composition
            out=composition.matrix()
        elif a.command=='doctor':
            from . import contracts
            out={'installation':registry.report(scan=True,live=True),'contracts':contracts.check(),
                 'grants':_grants(),
                 'scope':'installation, source contracts, systemd and authorizations; inspect matrix for qualification limits'}
            out['ok']=out['installation']['ok'] and out['contracts']['ok'] and out['grants']['ok']
        elif a.command in ('export','install','release'):
            from . import release
            if a.command=='export':out=release.build(a.destination,apply=a.apply,wheelhouse=a.wheelhouse)
            elif a.command=='install':out=release.install(a.bundle,a.root,apply=a.apply,backup_root=a.backup_root)
            elif a.release_action=='inspect':out=release.inspect(a.bundle)
            elif a.release_action=='environments':out=release.install_environments(a.bundle,a.root,python=a.python,apply=a.apply)
            else:out=release.rollback(a.backup,apply=a.apply)
        elif a.action=='check':out=harness.check(a.host,a.home)
        elif a.action=='attach':out=harness.attach(a.host,a.home,apply=a.apply,backup_root=a.backup_root)
        elif a.action=='install':
            from . import composition
            out=composition.install(a.host,a.home,apply=a.apply,backup_root=a.backup_root)
        elif a.action=='rollback':
            from . import composition
            out=composition.rollback(a.backup,apply=a.apply)
        print(json.dumps(out,ensure_ascii=False,indent=2));return 0 if out.get('ok',True) else 1
    except Exception as exc:
        # Config exceptions may quote secrets; expose only known validation failures.
        message=str(exc) if type(exc) is ValueError and not isinstance(exc,(json.JSONDecodeError,tomllib_error())) else type(exc).__name__
        print(json.dumps({'ok':False,'error':message}));return 1

def _grants():
    """Walter's authorizations, asked through walter-secrets' interface (metadata only)."""
    import subprocess
    try:
        r=subprocess.run(['walter-secret','grants'],capture_output=True,text=True,timeout=180)
        d=json.loads(r.stdout)
    except (OSError,subprocess.TimeoutExpired,ValueError):
        return {'ok':False,'problems':['walter-secret grants unavailable']}
    return {'ok':d.get('ok',False),'count':len(d.get('grants',[])),
            'problems':[f"{g['id']}: {p}" for g in d.get('grants',[]) for p in g.get('problems',[])]}

def tomllib_error():
    import tomllib
    return tomllib.TOMLDecodeError

if __name__=='__main__':raise SystemExit(main())
