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
    sub.add_parser('layout')
    q=sub.add_parser('instance');q.add_argument('instance_action',nargs='?',choices=('show','check','path','render','config'),default='show');q.add_argument('parts',nargs='*')
    sub.add_parser('matrix')
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
            out=paths.layout()
        elif a.command=='instance':
            from . import instance
            if a.instance_action=='path':
                print(instance.path(*a.parts));return 0
            if a.instance_action=='config':
                if len(a.parts)!=2:raise ValueError('usage: walter instance config <module> <file>')
                print(instance.config(*a.parts));return 0
            if a.instance_action=='render':
                sys.stdout.write(instance.render(sys.stdin.read()));return 0
            out=instance.check() if a.instance_action=='check' else instance.show()
        elif a.command=='matrix':
            from . import composition
            out=composition.matrix()
        elif a.command=='doctor':
            from . import contracts
            out={'installation':registry.report(scan=True,live=True),'contracts':contracts.check(),
                 'scope':'installation, source contracts and systemd; inspect matrix for qualification limits'}
            out['ok']=out['installation']['ok'] and out['contracts']['ok']
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

def tomllib_error():
    import tomllib
    return tomllib.TOMLDecodeError

if __name__=='__main__':raise SystemExit(main())
