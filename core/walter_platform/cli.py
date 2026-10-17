from __future__ import annotations
import argparse,json,sys
from . import registry,harness

def main(argv=None):
    p=argparse.ArgumentParser(prog='walter',description='Walter module composition and harness integration')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('modules','status','check','backup-paths'):sub.add_parser(name)
    h=sub.add_parser('harness');hs=h.add_subparsers(dest='action',required=True)
    for name in ('check','attach'):
        q=hs.add_parser(name);q.add_argument('host',choices=harness.HOSTS);q.add_argument('--home')
        if name=='attach':q.add_argument('--apply',action='store_true');q.add_argument('--backup-root')
    a=p.parse_args(argv)
    try:
        if a.command=='modules':out=registry.load()
        elif a.command=='backup-paths':out={'paths':registry.backup_paths()}
        elif a.command in ('status','check'):out=registry.report(scan=a.command=='check',live=a.command=='status')
        elif a.action=='check':out=harness.check(a.host,a.home)
        else:out=harness.attach(a.host,a.home,apply=a.apply,backup_root=a.backup_root)
        print(json.dumps(out,ensure_ascii=False,indent=2));return 0 if out.get('ok',True) else 1
    except Exception as exc:
        # Config exceptions may quote secrets; expose only known validation failures.
        message=str(exc) if type(exc) is ValueError and not isinstance(exc,(json.JSONDecodeError,tomllib_error())) else type(exc).__name__
        print(json.dumps({'ok':False,'error':message}));return 1

def tomllib_error():
    import tomllib
    return tomllib.TOMLDecodeError

if __name__=='__main__':raise SystemExit(main())
