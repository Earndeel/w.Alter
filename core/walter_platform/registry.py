"""Declarative module boundaries, dependencies and read-only verification.

A registry entry describes a contract, not a claim that its service is healthy.
Checks report observed files/import edges separately from integration declarations.
"""
from __future__ import annotations
import ast
import json
import os
import subprocess
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / 'modules' / 'registry.json'
HARNESS_IMPORTS = ('hermes_constants','hermes_cli','agent','tools','gateway','tui_gateway','run_agent')


def load(path=None):
    value=json.loads(Path(path or os.environ.get('WALTER_MODULE_REGISTRY',DEFAULT)).read_text())
    if value.get('version') != 1: raise ValueError('unsupported registry version')
    entries=value.get('modules',[])
    names=[m['id'] for m in entries]
    if len(set(names)) != len(names):raise ValueError('duplicate module id')
    by_id={m['id']:m for m in entries}
    for module in entries:
        for dep in module.get('requires',[]):
            if dep not in by_id:raise ValueError('unknown dependency: '+dep)
        for path in module.get('backup_paths',[]):
            if not Path(path).is_absolute() or '..' in Path(path).parts:raise ValueError('unsafe backup path')
    seen=set();visiting=set()
    def visit(name):
        if name in visiting:raise ValueError('module dependency cycle: '+name)
        if name in seen:return
        visiting.add(name)
        for dep in by_id[name].get('requires',[]):visit(dep)
        visiting.remove(name);seen.add(name)
    for name in names:visit(name)
    return value


def boundary_imports(path):
    """Static dependency test. Adapter directories are selected separately in the manifest."""
    p=Path(path);found=[]
    for f in ([p] if p.is_file() else sorted(p.rglob('*.py'))):
        if any(x in f.parts for x in ('venv','.venv','tests','__pycache__')):continue
        try: tree=ast.parse(f.read_text())
        except (OSError,SyntaxError) as e:
            found.append({'path':str(f),'problem':type(e).__name__});continue
        for node in ast.walk(tree):
            imports=([n.name for n in node.names] if isinstance(node,ast.Import) else
                     [node.module or ''] if isinstance(node,ast.ImportFrom) and node.level == 0 else [])
            for name in imports:
                if any(name==prefix or name.startswith(prefix+'.') for prefix in HARNESS_IMPORTS):
                    found.append({'path':str(f),'line':node.lineno,'import':name})
    return found


def inspect_module(module, *, scan=False):
    required=module.get('anchors',[])
    missing=[p for p in required if not Path(p).exists()]
    boundaries=[]
    if scan:
        for p in module.get('core_paths',[]):
            if not Path(p).exists():boundaries.append({'path':p,'problem':'missing core'})
            else:boundaries.extend(boundary_imports(p))
    return {'id':module['id'],'installed':not missing,'missing':missing,
            'boundary_checked':scan and bool(module.get('core_paths')),
            'forbidden_imports':boundaries,'runtime_health':'not_probed',
            'requires':module.get('requires',[]),'external':module.get('external',[]),
            'bindings':module.get('bindings',{}),'limitations':module.get('limitations',[])}


def report(*, scan=False, live=False, path=None):
    registry=load(path)
    modules=[inspect_module(m,scan=scan) for m in registry['modules']]
    if live:
        units=sorted({u for m in registry['modules'] for u in m.get('services',[])})
        try:
            result=subprocess.run(['systemctl','is-active',*units],capture_output=True,text=True,timeout=15)
            states=dict(zip(units,result.stdout.split()))
        except (OSError,subprocess.TimeoutExpired):states={}
        for m,declared in zip(modules,registry['modules']):
            m['services']={u:states.get(u,'unknown') for u in declared.get('services',[])}
            m['runtime_health']=('active' if all(x=='active' for x in m['services'].values()) else 'degraded') if m['services'] else 'no_dedicated_service'
    return {'schema_version':1,'ok':all(m['installed'] and not m['forbidden_imports'] and m['runtime_health']!='degraded' for m in modules),
            'scope':'installation/source boundaries and optional systemd state; functional health and end-to-end validation remain separate',
            'modules':modules}


def backup_paths(path=None):
    return sorted({p for m in load(path)['modules'] for p in m.get('backup_paths',[])})
