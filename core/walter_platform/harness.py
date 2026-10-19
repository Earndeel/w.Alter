"""Host configuration ports. Preserve host model, approvals, and unrelated integrations.

Attach installs the common MCP surface. Lifecycle hooks, model routing and context engines
are separate bindings, explicitly checked instead of falsely implied by MCP presence.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile
import tomllib
from pathlib import Path

HOSTS=('codex','claude-code','dsh','hermes')
SERVER='/opt/walter-core/server.py'
PYTHON='/opt/walter-core/venv/bin/python'
HOOK='/opt/walter-core/hooks/walter_hook.py'


def default_home(host):
    return Path({'codex':os.environ.get('CODEX_HOME','/root/.codex'),
                 'claude-code':'/root/.claude', 'dsh':os.environ.get('DSH_HOME','/opt/dsh/home'),
                 'hermes':os.environ.get('HERMES_HOME','/root/.hermes')}[host])


def config_path(host,home=None):
    p=Path(home) if home else default_home(host)
    if host=='claude-code':return p.parent/(p.name+'.json')
    return p/{'codex':'config.toml','dsh':'cordis.patch.yml','hermes':'config.yaml'}[host]


def read(host,home=None):
    path=config_path(host,home)
    if not path.exists():return {},path
    text=path.read_text()
    if host=='codex':return tomllib.loads(text),path
    if host=='claude-code':return json.loads(text),path
    import yaml
    return yaml.safe_load(text) or ([] if host=='dsh' else {}),path


def _mcp(host,data):
    if host=='codex':return data.get('mcp_servers',{}).get('walter',{})
    if host in ('claude-code','hermes'):return data.get('mcpServers' if host=='claude-code' else 'mcp_servers',{}).get('walter',{})
    for patch in data:
        for entry in patch.get('insert',[]):
            if entry.get('id')=='mcp-walter':return entry.get('config',{})
    return {}


def check(host,home=None):
    data,path=read(host,home);mcp=_mcp(host,data)
    connected=mcp.get('command')==PYTHON and mcp.get('args')==[SERVER]
    p=Path(home) if home else default_home(host)
    result={'harness':host,'config_path':str(path),'common_mcp':connected,
            'verification':'configuration only; active processes need a fresh MCP handshake',
            'native':['agent_loop','permissions'], 'bindings':{}}
    if host=='codex':
        result['native']+=['model','compression']
        result['bindings']['lifecycle_hook']=data.get('notify')==[HOOK,'codex-notify']
    elif host=='claude-code':
        result['native']+=['model','compression']
        hp=p/'settings.json';hooks=json.loads(hp.read_text()).get('hooks',{}) if hp.exists() else {}
        result['bindings']['lifecycle_hook']=all(any(h.get('command')==HOOK for x in hooks.get(event,[]) for h in x.get('hooks',[])) for event in ('SessionStart','UserPromptSubmit','Stop'))
    elif host=='dsh':
        result['bindings']['model_route']=any(x.get('id')=='agent-default-model' and x.get('config',{}).get('provider')=='walter' for x in data)
        result['bindings']['lifecycle_hook']=any(x.get('id')=='hooks-walter' and Path(x.get('config',{}).get('configPath','/nonexistent')).is_file() for row in data for x in row.get('insert',[]))
        result['bindings']['context_plugin']=any('walter-context' in str(x.get('name','')) or 'walter-context' in str(x.get('id','')) for row in data for x in row.get('insert',[]))
    else:
        enabled=data.get('plugins',{}).get('enabled',[])
        result['bindings']={'computer_backend':data.get('computer_use',{}).get('backend'),
                            'context_engine':data.get('context',{}).get('engine'),
                            'memory_provider':data.get('memory',{}).get('provider'),
                            'plugins':[x for x in enabled if x.startswith('walter-')]}
        result['common_mcp_required']=False
    return result


def prepare(host,home=None):
    """Returns proposed content in memory. Never print it: host config may hold secrets."""
    data,path=read(host,home)
    if host=='hermes':
        raise ValueError('Hermes uses its native Walter adapters; MCP attachment would duplicate tools')
    command={'command':PYTHON,'args':[SERVER],'env':{'WALTER_CLIENT_TAG':host.replace('-','_')}}
    if host=='codex':
        text=path.read_text() if path.exists() else ''
        # Preserve all other server options (including per-tool approval tables).
        existing=data.get('mcp_servers',{}).get('walter',{})
        if existing.get('command')==PYTHON and existing.get('args')==[SERVER]:return path,text,False
        if 'walter' in data.get('mcp_servers',{}):
            raise ValueError('existing Walter MCP command differs; refuse to overwrite custom configuration')
        text=text.rstrip()+'\n\n[mcp_servers.walter]\ncommand = '+json.dumps(PYTHON)+'\nargs = ['+json.dumps(SERVER)+']\n\n[mcp_servers.walter.env]\nWALTER_CLIENT_TAG = "codex"\n'
        tomllib.loads(text)
        return path,text,True
    if host=='claude-code':
        servers=data.setdefault('mcpServers',{})
        if 'walter' in servers:
            if servers['walter'].get('command')==PYTHON and servers['walter'].get('args')==[SERVER]:return path,path.read_text(),False
            raise ValueError('existing Walter MCP differs; refuse to overwrite custom configuration')
        servers['walter']={'type':'stdio',**command}
        return path,json.dumps(data,ensure_ascii=False,indent=2)+'\n',True
    import yaml
    current=_mcp(host,data)
    if current:
        if current.get('command')==PYTHON and current.get('args')==[SERVER]:return path,path.read_text(),False
        raise ValueError('existing Walter MCP differs; refuse to overwrite custom configuration')
    entry={'id':'mcp-walter','name':'@deepseek-ai/dsh-mcp-client',
           'config':{'serverName':'walter','transport':'stdio',**command,'toolCallTimeoutMs':600000}}
    # Append a YAML sequence item; preserve existing expressions/comments byte for byte.
    text=(path.read_text() if path.exists() else '').rstrip()+'\n'+yaml.safe_dump([{'insert':[entry]}],sort_keys=False)
    yaml.safe_load(text)
    return path,text,True


def attach(host,home=None,*,apply=False,backup_root=None):
    expected_path=config_path(host,home)
    initial_exists=expected_path.exists()
    initial=expected_path.read_bytes() if initial_exists else None
    path,new,changed=prepare(host,home)
    if path.exists()!=initial_exists or (initial_exists and path.read_bytes()!=initial):
        raise RuntimeError('config changed during preparation')
    result={'harness':host,'path':str(path),'changed':changed,'applied':False,
            'scope':'common MCP only; see harness check for other bindings'}
    if not changed or not apply:return result
    # Resolve an existing symlink so compatibility config locations remain intact.
    dest=path.resolve() if path.is_symlink() else path
    existed=initial_exists;before=initial
    if dest.exists()!=existed or (existed and dest.read_bytes()!=before):raise RuntimeError('config changed concurrently')
    root=Path(backup_root or '/root/.hermes/backups')/('harness-attach-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    root.mkdir(parents=True,mode=0o700)
    if existed:shutil.copy2(dest,root/'config.before')
    (root/'manifest.json').write_text(json.dumps({'path':str(dest),'existed':existed,'before_sha256':hashlib.sha256(before).hexdigest() if existed else None}))
    dest.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.walter-',dir=dest.parent)
    try:
        os.fchmod(fd,(dest.stat().st_mode & 0o777) if existed else 0o600)
        with os.fdopen(fd,'w') as f:f.write(new);f.flush();os.fsync(f.fileno())
        if existed and dest.read_bytes()!=before:raise RuntimeError('config changed concurrently')
        if not existed and dest.exists():raise RuntimeError('config created concurrently')
        os.replace(tmp,dest)
    finally:
        Path(tmp).unlink(missing_ok=True)
    result.update(applied=True,backup=str(root))
    return result
