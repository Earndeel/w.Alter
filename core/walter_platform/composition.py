"""Declarative host composition installer; no runtime/model calls or secret output.

Only supported host settings are managed. Unknown/custom Walter bindings conflict
instead of being replaced. Native model/compaction remain native where required.
Identity for Codex/Claude is an explicit profile cwd, never a replacement of global
operator instructions. Preparing a composition does not prove live tool usage.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import re
from pathlib import Path
import tomllib

from . import harness
from .harness_transaction import file_change, link_change, commit, rollback

ROOT=Path(__file__).resolve().parents[1]
COMPOSITIONS=ROOT/'compositions'
SKILL_DIR=str(ROOT/'skills')


def _context_port():
    """DSH entry of walter-context, located through the path resolver."""
    from .paths import module_path
    return str(module_path('context','ports','dsh','index.mjs'))


def definition(host):
    if host not in harness.HOSTS:raise ValueError('unknown harness')
    data=json.loads((COMPOSITIONS/(host+'.json')).read_text())
    if data.get('version')!=1 or data.get('id')!=host:raise ValueError('invalid composition definition')
    return data


def _managed_text(original, content, name):
    """Append/refresh our fenced section while preserving unrelated instruction bytes."""
    if original==content:return original
    pattern=re.compile(r'<!-- walter:'+re.escape(name)+r' sha256=([a-f0-9]{64}) -->\n(.*?)\n<!-- /walter:'+re.escape(name)+r' -->',re.S)
    matches=list(pattern.finditer(original))
    if len(matches)>1:raise ValueError('duplicate managed instruction sections')
    body=content.rstrip('\n');sha=hashlib.sha256(body.encode()).hexdigest()
    block=f'<!-- walter:{name} sha256={sha} -->\n{body}\n<!-- /walter:{name} -->'
    if matches:
        m=matches[0]
        if hashlib.sha256(m[2].encode()).hexdigest()!=m[1]:raise ValueError('managed instructions were edited; refusing overwrite')
        return original[:m.start()]+block+original[m.end():]
    if '<!-- walter:'+name in original:raise ValueError('invalid managed instruction section')
    return original+('' if not original else '\n\n')+block+'\n'


def _hook_data(data, spec, host):
    hooks=data.setdefault('hooks',{})
    for event,timeout in spec['hooks'].items():
        entries=hooks.setdefault(event,[])
        if any(h.get('command')==harness.HOOK for e in entries for h in e.get('hooks',[])):continue
        item={'hooks':[{'type':'command','command':harness.HOOK,'timeout':timeout}]}
        if event.startswith('PostToolUse'):item['matcher']='bash' if host=='dsh' else 'Bash'
        entries.append(item)
    return data


def _dsh_addition(data, entry):
    if any(row.get('id')==entry['id'] for row in data):
        raise ValueError('Walter DSH plugin has separate override patches; resolve them explicitly')
    found=[e for row in data for e in row.get('insert',[]) if e.get('id')==entry['id']]
    if len(found)>1:raise ValueError('duplicate Walter DSH composition entry')
    if found:
        e=found[0]
        if e.get('disabled') or e.get('name')!=entry['name']:raise ValueError('custom or disabled Walter DSH plugin conflicts')
        for k,v in entry.get('config',{}).items():
            if e.get('config',{}).get(k)!=v:raise ValueError('custom Walter DSH plugin configuration conflicts')
        return None
    return {'insert':[entry]}


def _dsh_patch(data, ident, config=None, **extra):
    found=[x for x in data if x.get('id')==ident]
    if len(found)>1:raise ValueError('duplicate DSH patch target requires manual reconciliation')
    if found:
        for k,v in (config or {}).items():
            if found[0].get('config',{}).get(k)!=v:raise ValueError('existing DSH setting conflicts with composition')
        if any(found[0].get(k)!=v for k,v in extra.items()):raise ValueError('existing DSH context setting conflicts')
        return None
    return {'id':ident,**({'config':config} if config is not None else {}),**extra}


def _plan(host,home=None,profile_dir=None):
    spec=definition(host);p=Path(home) if home is not None else harness.default_home(host)
    p=p.absolute();changes=[];prerequisites=[]
    def require(path,component):
        ok=Path(path).exists();prerequisites.append({'component':component,'path':str(path),'available':ok});return ok
    def file(path,text,component):changes.append(file_change(path,text,component))
    def link(path,target,component):
        if require(target,component):
            change=link_change(path,target,component)
            if change:changes.append(change)
    require(harness.PYTHON,'mcp_environment');require(harness.SERVER,'mcp');require(harness.HOOK,'lifecycle')
    # The source renderer remains walter-soul; installing does not edit its sources.
    source=Path(spec['identity_source'])
    identity=p/('SOUL.md' if host=='hermes' else 'AGENTS.md')
    if spec['identity_scope']=='workspace':
        profile=Path(profile_dir) if profile_dir else p/'walter-profile' if home is not None else Path('/opt/walter-profiles')/host
        identity=profile/('CLAUDE.md' if host=='claude-code' else 'AGENTS.md')
    if require(source,'identity'):
        before=identity.read_text() if identity.exists() else ''
        file(identity,_managed_text(before,source.read_text(),'identity'),'identity')
    # Shared skill bridge only: the skill catalogue and its learning stay in Walter Skills.
    if host in ('codex','claude-code'):
        skill=p/'skills/walter-skills/SKILL.md';src=Path(spec['skill_source'])
        if require(src,'skills'):
            if skill.exists() and skill.read_text()!=src.read_text():raise ValueError('existing Walter skill bridge differs; refusing overwrite')
            file(skill,src.read_text(),'skills')
    data,path=harness.read(host,p)
    original=path.read_text() if path.exists() else ''
    if host=='codex':
        _,text,_=harness.prepare(host,p)
        notify=spec['hooks']['notify'];existing=data.get('notify')
        if existing is not None and existing!=notify:raise ValueError('custom Codex notify hook conflicts; explicit composition is required')
        if existing is None:text='notify = '+json.dumps(notify)+'\n'+text
        tomllib.loads(text);file(path,text,'mcp,lifecycle')
    elif host=='claude-code':
        _,text,_=harness.prepare(host,p);file(path,text,'mcp')
        hp=p/'settings.json';hd=json.loads(hp.read_text()) if hp.exists() else {}
        file(hp,json.dumps(_hook_data(hd,spec,host),ensure_ascii=False,indent=2)+'\n','lifecycle')
    elif host=='dsh':
        import yaml
        _,text,_=harness.prepare(host,p);data=yaml.safe_load(text) or []
        hp=p/'walter-hooks.json';hd=json.loads(hp.read_text()) if hp.exists() else {}
        file(hp,json.dumps(_hook_data(hd,spec,host),ensure_ascii=False,indent=2)+'\n','lifecycle')
        additions=[];merged=False
        def add(item):
            if item:additions.append(item);data.append(item)
        add(_dsh_addition(data,{'id':'hooks-walter','name':'@deepseek-ai/dsh-hooks-claude-code','config':{'configPath':str(hp)}}))
        skill=[x for x in data if x.get('id')=='skill-filesystem']
        if skill:
            dirs=skill[0].setdefault('config',{}).setdefault('customSkillDirs',[])
            if SKILL_DIR not in dirs:dirs.append(SKILL_DIR);merged=True
        else:add(_dsh_patch(data,'skill-filesystem',{'customSkillDirs':[SKILL_DIR]}))
        add(_dsh_patch(data,'agent-default-model',{'provider':spec['provider'],'model':spec['model']}))
        # Preserve unrelated providers; an existing Walter provider must agree on the transport.
        provider={'displayName':'W.Alter (Walter Router)','api':'openai-completions','baseURL':spec['endpoint'],
                  'apiKeyEnv':'WALTER_LLM_TOKEN','models':[{'id':name,'name':'Walter '+name,'contextWindow':200000} for name in ('coding','general','document')]}
        llm=[x for x in data if x.get('id')=='llm-pi-ai']
        if llm:
            providers=llm[0].get('config',{}).get('providers',{})
            existing=providers.get('walter')
            if existing is None:
                llm[0].setdefault('config',{}).setdefault('providers',{})['walter']=provider;merged=True
            else:
                if any(existing.get(k)!=provider[k] for k in ('api','baseURL','apiKeyEnv')):raise ValueError('custom Walter provider transport conflicts')
                if spec['model'] not in {m.get('id') for m in existing.get('models',[])}:raise ValueError('Walter task is missing from DSH provider')
        else:add({'id':'llm-pi-ai','config':{'providers':{'walter':provider}}})
        cp=p/'.credentials.yaml'
        if not cp.exists():link(cp,spec['credential_source'],'credentials')
        else:require(cp,'credentials')
        add(_dsh_patch(data,'credentials',{'path':str(cp)}))
        add(_dsh_patch(data,'compaction-basic',disabled=True))
        add(_dsh_addition(data,{'id':'walter-context','name':_context_port()}))
        for dependency in (_context_port(),'/opt/dsh/node_modules/@deepseek-ai/dsh/package.json','/opt/dsh/node_modules/@deepseek-ai/dsh-hooks-claude-code/package.json'):
            require(dependency,'dsh_runtime')
        if merged:text=yaml.safe_dump(data,sort_keys=False)
        elif additions:text=text.rstrip()+'\n'+yaml.safe_dump(additions,sort_keys=False)
        yaml.safe_load(text);file(path,text,'mcp,lifecycle,skills,model,context')
    else:
        import yaml
        plugins=data.setdefault('plugins',{});enabled=plugins.setdefault('enabled',[]);disabled=plugins.get('disabled',[])
        memory_provider=data.get('memory',{}).get('provider')
        wanted=list(spec['plugins'])
        if memory_provider=='walter-memory':wanted.append(memory_provider)   # Hindsight retired 2026-10-19
        else:prerequisites.append({'component':'memory_provider','available':False,'reason':'current provider has no declared Walter composition'})
        for name in wanted:
            if name in disabled:raise ValueError('required Hermes adapter explicitly disabled')
            # Public memory providers are selected by memory.provider, not the
            # general plugin allowlist (plugins.disabled is still respected).
            if name!=memory_provider and name not in enabled:enabled.append(name)
            link(p/'plugins'/name,Path('/root/.hermes/plugins')/name,'plugin:'+name)
        current=data.setdefault('context',{}).get('engine')
        if current not in (None,spec['context']):raise ValueError('Hermes context differs; no unqualified context migration is allowed')
        data['context']['engine']=spec['context']
        for section,key,value in [('computer_use','backend','walter')]:
            block=data.setdefault(section,{})
            if block.get(key) not in (None,value):raise ValueError('existing Hermes capability backend conflicts')
            block[key]=value
        # Public tool override is required only for the Walter computer adapter.
        entry=plugins.setdefault('entries',{}).setdefault('walter-computer-use',{})
        if entry.get('allow_tool_override') is False:raise ValueError('Hermes computer override is explicitly disabled')
        entry['allow_tool_override']=True
        hooks=data.setdefault('hooks',{})
        for event,item in spec['hooks'].items():
            group=hooks.setdefault(event,[])
            if not any(x.get('command')==item['command'] for x in group):group.append(item)
        # Preserve native provider/model, auth, approval and memory settings.
        if data==(yaml.safe_load(original) or {}):text=original
        else:text=yaml.safe_dump(data,sort_keys=False,allow_unicode=True)
        file(path,text,'plugins,lifecycle,context')
    # Reject aliases which would be written twice in a transaction.
    targets=[c['target'] for c in changes if c['changed']]
    if len(targets)!=len(set(targets)):raise ValueError('composition targets alias the same configuration file')
    return spec,changes,prerequisites,identity


def install(host,home=None,*,apply=False,backup_root=None,profile_dir=None):
    spec,changes,prerequisites,identity=_plan(host,home,profile_dir)
    pending=[c for c in changes if c['changed']]
    result={'ok':all(p['available'] for p in prerequisites),'harness':host,'version':spec['version'],
            'applied':False,'changed':bool(pending),'identity_path':str(identity),'identity_scope':spec['identity_scope'],
            'native':spec['native'],'prerequisites':prerequisites,
            'changes':[{'path':c['path'],'component':c['component'],'operation':'create' if c['before'] is None else 'update'} for c in pending],
            'verification':'configuration composition only; restart clients and run capability acceptance separately',
            'limitations':spec.get('limitations',[])}
    if apply and result['ok'] and pending:
        result['backup']=commit(changes,backup_root=backup_root or '/root/.hermes/backups',host=host)
        result['applied']=True
    return result


def matrix():
    from .harness_matrix import matrix as build
    return build()
