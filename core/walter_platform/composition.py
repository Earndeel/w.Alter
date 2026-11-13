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
import os
import re
from pathlib import Path
import tomllib

from . import harness
from .harness_transaction import file_change, link_change, commit, rollback

ROOT=Path(__file__).resolve().parents[1]
COMPOSITIONS=ROOT/'compositions'
ENGINE_COMPOSITIONS=ROOT/'engine'/'compositions'   # engine composition sources (E1, 2026-11-09)
SKILL_DIR=str(ROOT/'skills')
DSH_LIB=Path('/opt/dsh/node_modules/@deepseek-ai')
DSH_OWNER_TURN=ROOT/'hooks'/'dsh'/'owner-turn.mjs'
# Lot E2 (2026-11-10): who accepts a turn and publishes its events. hook = walter_hook.py (UserPromptSubmit/Stop, the
# E1 state); shadow = the engine plugins only observe beside the hook; native = the plugins do it, the hook keeps
# SessionStart and PostToolUse. Switch: [dsh.engine] intake in @instance/config/core/engine.toml.
ENGINE_PLUGINS=ROOT/'engine'/'plugins'
ENGINE_INTAKE=('hook','shadow','native')
ENGINE_ROWS=('walter-intake','walter-events','walter-policy','walter-budget')
ENGINE_POLICY=('off','enforce')                     # lot E3: Walter's one execution policy in the engine
NATIVE_HOOKS=('UserPromptSubmit','Stop')            # what the native plugins take over from walter_hook.py
# Lot 1 (2026-11-07, /walter/docs/DECISIONS.md): DSH is only the agent loop and technical tool execution. Every DSH
# row that competes with a Walter module is off: identity → soul, skills → walter-skills, web → walter_browse,
# context/compaction → walter-context, models/titles → Walter Router; DeepSeek telemetry, accounts and providers.
DSH_OFF=('tool-web','tool-skill','skill-filesystem','web','web-search-deepseek','web-fetch-http',
         'session-telemetry-otel','session-log-deepseek','plugin-package-inventory-deepseek',
         'deepseek-llm-api-extensions','deepseek-account','llm-deepseek','llm-deepseek-account')
DSH_PRESET_OWNED={'persona':'soul','skill-filesystem':'skills','tool-skill':'skills','tool-web':'browse'}
# Lean runtime (2026-11-07, owner: « DSH doit uniquement fournir les primitives du runtime »): DSH's own orchestration
# (goals, plan mode, todo list, sub-agents, workflows, MCP resource browsing) is off; delegation is Walter's
# (walter_run → Walter Router), the working plan is Walter Memory's (SessionState). 0 calls in 156 DSH sessions;
# each tool card cost every request ~11K chars. Kept: agent loop, bash/fs/search/jobs, ask-user, present, compaction.
DSH_ORCHESTRATION=('goal','goal-round-driver','command-goal','tool-goal','plan-mode','subagent','subagent-spawn-in-process',
                   'subagent-fork-in-process','tool-subagent-control','tool-subagent-list-agents','tool-subagent',
                   'tool-subagent-fork','workflow-ptc','tool-workflow','tool-ralph','tool-todo','mcp-resources')
DSH_PRESET_GROUPS_OFF=('planning','delegation')   # preset groups holding only orchestration rows
DSH_OFF=DSH_OFF+DSH_ORCHESTRATION
# Web surface (2026-11-07, owner « pas de boutons inutiles »): Walter Router picks the model, the agent profile is
# Walter's, DSH packages are managed by Walter; the DeepSeek brand gives way to the instance's face (walter-ui).
DSH_WEB_OFF=('preset-ptc','preset-minimal','preset-cordis','account-controller','ui-brand-official',
             'ui-model-selection','ui-agent-preset','ui-plugin-manager','ui-settings-plugin-inventory',
             'ui-settings-plugins','ui-settings-shell','ui-settings-agent-loop','ui-settings-subagent',
             'ui-settings-web-search')
DSH_TASKS=('coding','general','document','summarization','auto')   # Walter Router tasks offered to DSH (live order)
DSH_TITLE={'targetWords':5,'targetCjkCharacters':10,'maxInputBytes':4096,'maxOutputTokens':64,'timeoutMs':60000,
           'provider':'walter','model':'summarization'}


def engine_values(*, instance=True):
    """Engine composition values: the module's neutral config/engine.toml, overridden key by key by the instance's
    (`walter instance config core engine.toml`). instance=False = neutral defaults only (tests, fresh homes)."""
    from .paths import module_path
    data=tomllib.loads(module_path('core','config','engine.toml').read_text())
    if instance:
        from . import instance as inst
        override=inst.path('config','core','engine.toml')
        if override.is_file():
            for section,values in tomllib.loads(override.read_text()).items():
                if isinstance(values,dict):
                    for key,sub in values.items():
                        if isinstance(sub,dict):data.setdefault(section,{}).setdefault(key,{}).update(sub)
                        else:data.setdefault(section,{})[key]=sub
                else:data[section]=values
    return data


def engine_intake(values):
    # WALTER_ENGINE_INTAKE: a test or Lab home composed in another mode (`--home`), never set for the live service
    mode=str(os.environ.get('WALTER_ENGINE_INTAKE') or values.get('dsh',{}).get('engine',{}).get('intake','hook'))
    if mode not in ENGINE_INTAKE:raise ValueError('unknown [dsh.engine] intake (hook, shadow or native)')
    return mode


def engine_policy(values):
    # WALTER_ENGINE_POLICY: a test or Lab home composed otherwise (`--home`), never set for the live service
    mode=str(os.environ.get('WALTER_ENGINE_POLICY') or values.get('dsh',{}).get('engine',{}).get('policy','off'))
    if mode not in ENGINE_POLICY:raise ValueError('unknown [dsh.engine] policy (off or enforce)')
    return mode


ENGINE_SUBAGENTS=('off','on')                       # lot E5: the kernel's in-process sub-agents under Walter's policy
# Kept when sub-agents are on: the in-process runtime, the delegation tool (spawn) and its control/list tools. Fork,
# workflows, Ralph, Codex/Claude Code children stay off: one way to delegate, the engine's own.
SUBAGENT_KEEP=('subagent','subagent-spawn-in-process','tool-subagent','tool-subagent-control','tool-subagent-list-agents')
SUBAGENT_DROP=('tool-subagent-codex','tool-subagent-claude-code')
SUBAGENT_MAX_DEPTH=3                               # = core/security policy never.max_depth (children ≤ 3 levels)


def engine_subagents(values):
    # WALTER_ENGINE_SUBAGENTS: a test or Lab home composed otherwise (`--home`), never set for the live service
    mode=str(os.environ.get('WALTER_ENGINE_SUBAGENTS') or values.get('dsh',{}).get('engine',{}).get('subagents','off'))
    if mode not in ENGINE_SUBAGENTS:raise ValueError('unknown [dsh.engine] subagents (off or on)')
    return mode


ENGINE_API=('off','on')                             # lot E4: the engine's own API door (core/interfaces/api)
ENGINE_API_PLUGIN=ROOT/'interfaces'/'api'/'index.mjs'
WEB_LOGIN_PLUGIN=ROOT/'interfaces'/'web'/'login-link.mjs'


def _web_login_file():
    # a test home overrides it (WALTER_ENGINE_WEB_LOGIN) so it never replaces the live link
    from . import instance as inst
    return os.environ.get('WALTER_ENGINE_WEB_LOGIN') or inst.path('state','core','engine','web','login-url')


def engine_api(values):
    # WALTER_ENGINE_API: a test or Lab home composed otherwise (`--home`), never set for the live service
    mode=str(os.environ.get('WALTER_ENGINE_API') or values.get('dsh',{}).get('engine',{}).get('api','off'))
    if mode not in ENGINE_API:raise ValueError('unknown [dsh.engine] api (off or on)')
    return mode


def _dsh_api(values):
    """Fenced `dsh-api` block of the web profile (lot E4): the Engine API lives in the long-running web host only,
    never in a headless run. Port, state and token file come from the instance; a test home overrides them with
    WALTER_ENGINE_API_PORT / WALTER_ENGINE_API_STATE so it never shares the live address table."""
    from . import instance as inst
    eng=values.get('dsh',{}).get('engine',{})
    port=int(os.environ.get('WALTER_ENGINE_API_PORT') or eng.get('api_port') or 8895)
    state=os.environ.get('WALTER_ENGINE_API_STATE')
    cfg={'port':port,'stateDir':state or str(inst.path('state','core','engine','api')),
         'tokenFile':str(Path(state)/'api.token') if state else str(inst.path('bootstrap','engine','api.token')),
         'workspace':str(inst.path('workspace'))}
    import yaml
    return ('# Engine API (lot E4): one door for Telegram, the web and Walter modules; loopback, token in a header.\n'
            +yaml.safe_dump([{'insert':[{'id':'walter-engine-api','name':str(ENGINE_API_PLUGIN),'config':cfg}]}],sort_keys=False,allow_unicode=True,width=120))


def _drop_managed(original,name):
    """Removes a fenced Walter block that is no longer wanted (switch turned off), refusing a hand-edited one."""
    pattern=re.compile(r'# walter:'+re.escape(name)+r' json-sha256=([a-f0-9]{64}) rows=(\d+)\n(.*?)\n# /walter:'+re.escape(name)+r'\n?\n?',re.S)
    m=pattern.search(original)
    if not m:return original
    rows=_yaml_rows(m[3]);n=int(m[2])
    if _rows_sha([r for r,_ in rows[:n]])!=m[1]:raise ValueError('managed DSH profile section was edited; refusing removal')
    foreign=''.join(raw for _,raw in rows[n:]).strip('\n')
    return original[:m.start()]+(foreign+'\n' if foreign else '')+original[m.end():]


def engine_budget(values):
    """[dsh.budget] as the budget plugin reads it: general ceilings and the ceilings of each ContextPlan level."""
    b=values.get('dsh',{}).get('budget',{})
    def minutes(v,what):
        if isinstance(v,bool) or not isinstance(v,(int,float)) or v<=0:raise ValueError(f'[dsh.budget] {what}: a positive number of minutes')
        return int(v*60_000)
    def steps(v,what):
        if isinstance(v,bool) or not isinstance(v,int) or v<0:raise ValueError(f'[dsh.budget] {what}: a whole number of steps')
        return v
    out={}
    if 'max_steps' in b:out['maxSteps']=steps(b['max_steps'],'max_steps')
    if 'grace_steps' in b:out['graceSteps']=steps(b['grace_steps'],'grace_steps')
    if 'max_turn_min' in b:out['maxTurnMs']=minutes(b['max_turn_min'],'max_turn_min')
    if 'grace_min' in b:out['graceMs']=minutes(b['grace_min'],'grace_min')
    levels={}
    for name,row in sorted((b.get('levels') or {}).items()):
        if not isinstance(row,dict):raise ValueError(f'[dsh.budget.levels] {name}: a table')
        levels[name]={'checkpoint':steps(row.get('checkpoint',0),f'{name}.checkpoint'),
                      'maxSteps':steps(row['max_steps'],f'{name}.max_steps'),
                      'maxTurnMs':minutes(row['max_turn_min'],f'{name}.max_turn_min')}
    if levels:out['levels']=levels
    return out


def _engine_rows(mode,policy='off'):
    """The engine's intake and events plugins for this mode (none for `hook`), and its policy plugin when enforced.
    Locations come from the instance and from Walter Memory's public client (its gateway credential file), never
    written here by hand."""
    if mode=='hook' and policy=='off':return []
    import subprocess
    from . import instance as inst
    # Walter Memory's public client names its credential file (the shared runtime has it; this CLI may not)
    out=subprocess.run(['walter-python','-c','from walter_memory import client; print(client.ENV_FILE)'],
                       capture_output=True,text=True,timeout=60)
    if out.returncode or not out.stdout.strip():raise ValueError('Walter Memory client unavailable: no gateway credential for the engine plugins')
    rows=[]
    if policy=='enforce':   # first: the door every tool call of every agent goes through
        rows.append({'id':'walter-policy','name':str(ENGINE_PLUGINS/'policy'/'index.mjs'),
                     'config':{'interface':'web','stateDir':str(inst.path('state','core','security')),'tokenFile':out.stdout.strip()}})
        rows.append({'id':'walter-budget','name':str(ENGINE_PLUGINS/'budget'/'index.mjs'),
                     'config':{'stateDir':str(inst.path('state','core','security')),**engine_budget(engine_values())}})
    if mode=='hook':return rows
    cfg={'mode':mode,'runtime':'dsh','stateDir':str(inst.path('state','core','engine','intake')),
         'runsDir':str(inst.path('state','runs','current')),'tokenFile':out.stdout.strip()}
    return rows+[{'id':'walter-intake','name':str(ENGINE_PLUGINS/'intake'/'index.mjs'),'config':cfg},
                 {'id':'walter-events','name':str(ENGINE_PLUGINS/'events'/'index.mjs'),'config':dict(cfg)}]


def _dsh_face(values):
    """Fenced `dsh-face` block of the web profile: the instance's face (name, greeting) and sign-in lifetime, from
    the engine/compositions template. Before 2026-11-09 these rows were written by hand in the live home."""
    from string import Template
    from .paths import module_path
    web=values.get('dsh',{}).get('web',{})
    days=web.get('cookie_max_age_days')
    if not isinstance(days,int) or isinstance(days,bool) or days<1:raise ValueError('engine.toml [dsh.web] cookie_max_age_days must be a positive integer')
    text=Template((ENGINE_COMPOSITIONS/'dsh-face.patch.yml').read_text()).substitute(
        cookie_max_age_days=days,ui_port=json.dumps(str(module_path('core','ports','dsh-web-ui','index.js'))),
        name=json.dumps(str(web.get('name') or 'Walter'),ensure_ascii=False),
        tagline=json.dumps(str(web.get('tagline') or ''),ensure_ascii=False))
    return text


def _unfenced_rows(text):
    """Parsed rows of a DSH patch outside every Walter fence (hand-written or DSH's own)."""
    rest=re.sub(r'# walter:([\w-]+) [^\n]*\n.*?\n# /walter:\1\n?','',text,flags=re.S)
    return _dsh_yaml(rest)


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


def _yaml_rows(text):
    """Top-level rows of a DSH patch as (parsed row, raw source slice); raw slices keep `!!js` tags and layout."""
    import yaml
    node=yaml.compose(text,Loader=yaml.SafeLoader)
    if node is None:return []
    if not isinstance(node,yaml.SequenceNode):raise ValueError('DSH profile patch is not a list of rows')
    starts=[text.rfind('\n',0,item.start_mark.index)+1 for item in node.value]
    raws=[text[s:e] for s,e in zip(starts,starts[1:]+[len(text)])]
    return [(_dsh_yaml(raw)[0],raw) for raw in raws]


def _rows_sha(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def _managed_yaml(original, content, name, anchor=None):
    """`_managed_text` for YAML files: the Walter block is fenced by YAML comments, other bytes are preserved.
    The fence records a hash of the parsed Walter rows and their count, not of their bytes: DSH web re-serialises
    the file when it saves a UI setting and appends its own rows at the end of the document, inside the fence when
    the block is last (2026-11-07, `ui-settings-general`). Re-indentation is therefore not an edit, and rows after
    Walter's are DSH's: they are kept, moved just after the block. Changing a Walter row is still refused."""
    fence=re.escape(name)
    pattern=re.compile(r'# walter:'+fence+r' (sha256|json-sha256)=([a-f0-9]{64})(?: rows=(\d+))?\n(.*?)\n# /walter:'+fence+r'\n?',re.S)
    matches=list(pattern.finditer(original))
    if len(matches)>1:raise ValueError('duplicate managed DSH profile sections')
    body=content.rstrip('\n');walter=_dsh_yaml(body)
    block=f'# walter:{name} json-sha256={_rows_sha(walter)} rows={len(walter)}\n{body}\n# /walter:{name}\n'
    if matches:
        m=matches[0];kind,sha,count,old=m[1],m[2],m[3],m[4]
        rows=_yaml_rows(old)
        if kind=='json-sha256':
            n=int(count or 0)
            if _rows_sha([r for r,_ in rows[:n]])!=sha:raise ValueError('managed DSH profile section was edited; refusing overwrite')
        elif hashlib.sha256(old.encode()).hexdigest()==sha:n=len(rows)
        else:   # legacy byte hash: accept only a re-serialisation of exactly what Walter writes today
            n=len(walter)
            if [r for r,_ in rows[:n]]!=walter:raise ValueError('managed DSH profile section was edited; refusing overwrite')
        foreign=''.join(raw for _,raw in rows[n:]).strip('\n')
        return original[:m.start()]+block+(foreign+'\n' if foreign else '')+original[m.end():]
    if '# walter:'+name+' ' in original:raise ValueError('invalid managed DSH profile section')
    original=re.sub(r'(?m)^\[\]\s*$\n?','',original)   # DSH writes an empty profile patch as `[]`
    at=original.find('# walter:'+anchor+' ') if anchor else -1
    if at>=0:   # a new block goes just before the anchor block: the composed order stays the one DSH has always seen
        return original[:at]+block+'\n'+original[at:]
    return original.rstrip('\n')+('\n\n' if original.strip() else '')+block


def _dsh_yaml(text):
    """Parse a DSH patch keeping `!!js` expressions as {'__js__': source}."""
    import yaml
    class Loader(yaml.SafeLoader):pass
    Loader.add_constructor('tag:yaml.org,2002:js',lambda loader,node:{'__js__':loader.construct_scalar(node)})
    return yaml.load(text,Loader) or []


def _dsh_preset(port,subagents=False):
    """Walter's `standard` agent preset: the one shipped with dsh-web-app minus the rows a Walter module owns;
    compaction-basic → walter-context (single compaction owner). Same preset id, so saved sessions keep resolving.
    With sub-agents (lot E5) the `delegation` group keeps only the spawn tool (depth ≤ SUBAGENT_MAX_DEPTH) and its
    control/list tools."""
    rows=_dsh_yaml((DSH_LIB/'dsh-web-app'/'presets'/'standard.patch.yml').read_text())
    row=next(e for r in rows for e in r.get('insert',[]) if e.get('id')=='preset-standard')
    keep=SUBAGENT_KEEP if subagents else ()
    def walk(entries):
        out=[]
        for e in entries:
            if e.get('id') in DSH_PRESET_OWNED or (e.get('id') in DSH_ORCHESTRATION and e.get('id') not in keep):continue
            if subagents and e.get('id') in SUBAGENT_DROP:continue
            if e.get('group') and e.get('id') in DSH_PRESET_GROUPS_OFF and not (subagents and e.get('id')=='delegation'):continue
            # one-shot: the call waits for the child's answer (parallel calls in one step run together), so a turn's
            # result holds what its children found; a long child can still run as a job (run_in_background)
            if e.get('id')=='tool-subagent' and subagents:e={**e,'config':{**(e.get('config') or {}),'maxDepth':SUBAGENT_MAX_DEPTH,'backgroundMode':'one-shot'}}
            gate=e.get('disabled')
            if isinstance(gate,dict):   # bash/pwsh platform switch; Walter hosts are Linux
                if gate['__js__'].replace('"',"'") not in ("process.platform === 'win32'","process.platform !== 'win32'"):
                    raise ValueError('unknown expression in shipped DSH preset')
                if '!==' in gate['__js__']:continue
                e={k:v for k,v in e.items() if k!='disabled'}
            if e.get('id')=='compaction-basic':e={'id':'walter-context','name':port}
            if e.get('group') and isinstance(e.get('config'),list):e={**e,'config':walk(e['config'])}
            out.append(e)
        return out
    config={**row['config'],'plugins':walk(row['config']['plugins'])}
    if '__js__' in json.dumps(config):raise ValueError('unsupported expression in shipped DSH preset')
    return {'id':'preset-standard','config':config}


def _dsh_web_profile(port,subagents=False):
    """Managed section of the DSH web profile patch (rows that exist only in the web composition)."""
    import yaml
    head=('# DSH web GUI: no developer surface text (HMR, pnpm, harness source) in the prompt.\n'
          '- id: web-runtime\n  config:\n    openBrowser: !!js ctx.webStartup.openBrowser\n    printUrl: false\n'
          '    surfaceContext: false\n    trustedHosts: !!js ctx.webStartup.trustedHosts\n'
          # sign-in link (launch token) never in the journal: a root-only file of the instance (owner, 2026-11-11)
          +'# Web sign-in link: written to a root-only file of the instance, never printed to the journal.\n'
          +yaml.safe_dump([{'insert':[{'id':'walter-web-login','name':str(WEB_LOGIN_PLUGIN),
                                       'config':{'file':str(_web_login_file())}}]}],sort_keys=False,allow_unicode=True,width=120)
          +'# Presets that carry the DSH "coding agent" persona and DSH skills/web/compaction; DeepSeek account UI;\n'
          '# web controls Walter owns (model, agent profile, packages) and the DeepSeek brand.\n')
    head+=''.join(f'- id: {x}\n  disabled: true\n' for x in DSH_WEB_OFF)
    # dsh-web-app re-enables some orchestration rows after the global patch: the profile layer is applied last.
    head+='# DSH orchestration (goals, plan mode, sub-agents, workflows, todo, MCP resources): Walter owns it.\n'
    head+=''.join(f'- id: {x}\n  disabled: true\n' for x in DSH_ORCHESTRATION if not (subagents and x in SUBAGENT_KEEP))
    return head+'# Walter "standard" preset (generated from the shipped one by walter-core composition).\n'+yaml.safe_dump([_dsh_preset(port,subagents)],sort_keys=False,allow_unicode=True,width=120)


def _dsh_headless_profile(port):
    """Managed section of the headless profile patch: it has no agent presets, so the engine is a global row."""
    return '# One compaction owner: walter-context (the web profile gets it inside its agent preset).\n- insert:\n  - id: walter-context\n    name: '+port+'\n'


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
        values=engine_values();mode=engine_intake(values);policy=engine_policy(values)
        hp=p/'walter-hooks.json';hd=json.loads(hp.read_text()) if hp.exists() else {}
        hd=_hook_data(hd,spec,host)
        if mode=='native':      # the engine's plugins accept turns and publish their end: no second adapter
            for event in NATIVE_HOOKS:
                kept=[e for e in hd.get('hooks',{}).get(event,[]) if not any(h.get('command')==harness.HOOK for h in e.get('hooks',[]))]
                if kept:hd['hooks'][event]=kept
                else:hd.get('hooks',{}).pop(event,None)
        if 'hooks' in hd:      # the definition's order, whatever came and went (a rollback to `hook` is byte-identical)
            hd['hooks']={k:hd['hooks'][k] for k in [*[e for e in spec['hooks'] if e in hd['hooks']],*[e for e in hd['hooks'] if e not in spec['hooks']]]}
        file(hp,json.dumps(hd,ensure_ascii=False,indent=2)+'\n','lifecycle')
        additions=[];merged=False
        def add(item):
            if item:additions.append(item);data.append(item)
        add(_dsh_addition(data,{'id':'hooks-walter','name':'@deepseek-ai/dsh-hooks-claude-code','config':{'configPath':str(hp)}}))
        # Engine plugins (lot E2): replaced as a whole when the mode or a location changes, removed for `hook`.
        wanted=_engine_rows(mode,policy);have=[e for r in data for e in r.get('insert',[]) if e.get('id') in ENGINE_ROWS]
        if have!=wanted:
            for row in [r for r in data if any(e.get('id') in ENGINE_ROWS for e in r.get('insert',[]))]:
                row['insert']=[e for e in row['insert'] if e.get('id') not in ENGINE_ROWS]
                if not row['insert']:data.remove(row)
            merged=True
        # Records which part of each step the owner wrote, so the hook ignores DSH runtime notices (lot 1); in native
        # mode the intake plugin reads the owner's text itself.
        if mode=='native':
            for row in [r for r in data if any(e.get('id')=='walter-owner-turn' for e in r.get('insert',[]))]:
                row['insert']=[e for e in row['insert'] if e.get('id')!='walter-owner-turn'];merged=True
                if not row['insert']:data.remove(row)
        else:add(_dsh_addition(data,{'id':'walter-owner-turn','name':str(DSH_OWNER_TURN)}))
        if wanted and have!=wanted:add({'insert':wanted})
        # Rows a Walter module replaces: turned off, any local config kept (lot 1, 2026-11-07).
        subagents=engine_subagents(values)=='on'
        for ident in DSH_OFF:
            rows=[x for x in data if x.get('id')==ident]
            if subagents and ident in SUBAGENT_KEEP:   # back to the shipped composition for these rows (E5)
                for x in rows:
                    if x=={'id':ident,'disabled':True}:data.remove(x);merged=True
                continue
            if len(rows)>1:raise ValueError('duplicate DSH patch target requires manual reconciliation')
            if not rows:add({'id':ident,'disabled':True})
            elif rows[0].get('disabled') is not True:rows[0]['disabled']=True;merged=True
        # Lot 2 (2026-11-07): `auto` = the preflight's plan picks the Router task and tier; the earlier default
        # (`coding`, set by this composition) moves to it. Any other default stays a conflict to reconcile by hand.
        old=[x for x in data if x.get('id')=='agent-default-model']
        if (spec['model']=='auto' and len(old)==1 and old[0].get('config',{}).get('provider')==spec['provider']
                and old[0].get('config',{}).get('model')=='coding'):
            old[0]['config']['model']='auto';merged=True
        add(_dsh_patch(data,'agent-default-model',{'provider':spec['provider'],'model':spec['model']}))
        add(_dsh_patch(data,'system-prompt',{'includeHarnessIdentity':False,'personaPrefix':'','personaSuffix':''}))
        add(_dsh_patch(data,'session-title-llm',DSH_TITLE))
        # Preserve unrelated providers; an existing Walter provider must agree on the transport.
        values=engine_values();names=values.get('dsh',{}).get('model_names',{})
        label=lambda name:str(names.get(name) or 'Walter '+name)   # display names: @instance/config/core/engine.toml
        # Long prompt-cache retention: walter-llm forwards it to providers that support it (set by hand in the live
        # home before 2026-11-09; now part of the source, so a fresh home composes the same).
        cache={'cacheRetention':'long','compat':{'supportsLongCacheRetention':True}}
        provider={'displayName':'W.Alter (Walter Router)','api':'openai-completions','baseURL':spec['endpoint'],
                  'apiKeyEnv':'WALTER_LLM_TOKEN',**cache,'models':[{'id':name,'name':label(name),'contextWindow':200000} for name in DSH_TASKS]}
        llm=[x for x in data if x.get('id')=='llm-pi-ai']
        if llm:
            providers=llm[0].get('config',{}).get('providers',{})
            existing=providers.get('walter')
            if existing is None:
                llm[0].setdefault('config',{}).setdefault('providers',{})['walter']=provider;merged=True
            else:
                if any(existing.get(k)!=provider[k] for k in ('api','baseURL','apiKeyEnv')):raise ValueError('custom Walter provider transport conflicts')
                for k,v in cache.items():   # added when missing; a value set otherwise is kept
                    if k not in existing:existing[k]=v;merged=True
                for name in DSH_TASKS:
                    if name not in {m.get('id') for m in existing.get('models',[])}:
                        existing.setdefault('models',[]).append({'id':name,'name':label(name),'contextWindow':200000});merged=True
                for m in existing.get('models',[]):   # a configured display name is the instance's: it wins
                    if m.get('id') in names and m.get('name')!=label(m['id']):m['name']=label(m['id']);merged=True
                if spec['model'] not in {m.get('id') for m in existing.get('models',[])}:raise ValueError('Walter task is missing from DSH provider')
        else:add({'id':'llm-pi-ai','config':{'providers':{'walter':provider}}})
        cp=p/'.credentials.yaml'
        if not cp.exists():link(cp,spec['credential_source'],'credentials')
        else:require(cp,'credentials')
        add(_dsh_patch(data,'credentials',{'path':str(cp)}))
        add(_dsh_patch(data,'compaction-basic',disabled=True))
        # walter-context is mounted per profile (preset for web, global row for headless): a global row here would
        # run a second engine beside the preset's. Remove the pre-2026-11-07 global row.
        for row in [r for r in data if any(e.get('id')=='walter-context' for e in r.get('insert',[]))]:
            row['insert']=[e for e in row['insert'] if e.get('id')!='walter-context'];merged=True
            if not row['insert']:data.remove(row)
        for dependency in (_context_port(),str(DSH_OWNER_TURN),'/opt/dsh/node_modules/@deepseek-ai/dsh/package.json','/opt/dsh/node_modules/@deepseek-ai/dsh-hooks-claude-code/package.json'):
            require(dependency,'dsh_runtime')
        if merged:text=('# W.Alter composition for DeepSeek Harness, written by walter-core (`walter compose install dsh`).\n'
                        '# DSH = agent loop + technical tools; identity, context, memory, skills, web and models are Walter modules.\n'
                        +yaml.safe_dump(data,sort_keys=False,allow_unicode=True,width=120))
        elif additions:text=text.rstrip()+'\n'+yaml.safe_dump(additions,sort_keys=False,allow_unicode=True,width=120)
        yaml.safe_load(text);file(path,text,'mcp,lifecycle,skills,model,context')
        if require(DSH_LIB/'dsh-web-app'/'presets'/'standard.patch.yml','dsh_runtime'):
            for profile,block in (('web',lambda port:_dsh_web_profile(port,subagents)),('headless',_dsh_headless_profile)):
                wp=p/'profiles'/profile/'cordis.patch.yml'
                before=wp.read_text() if wp.exists() else ''
                after=before
                if profile=='web':
                    # The instance's face is rendered too (E1): rows written by hand for the same targets would
                    # compose twice, so they are a conflict to remove explicitly, never silently replaced.
                    hand=[r for r in _unfenced_rows(before) if r.get('id')=='connection'
                          or any(e.get('id')=='walter-ui' for e in r.get('insert',[]))]
                    if hand:raise ValueError('hand-written DSH web face rows (connection, walter-ui) duplicate the rendered dsh-face block; remove them first')
                    after=_managed_yaml(after,_dsh_face(values),'dsh-face',anchor='dsh-web')
                    after=(_managed_yaml(after,_dsh_api(values),'dsh-api',anchor='dsh-web') if engine_api(values)=='on'
                           else _drop_managed(after,'dsh-api'))
                after=_managed_yaml(after,block(_context_port()),'dsh-'+profile)
                _dsh_yaml(after)
                if after!=before:file(wp,after,'identity,context,skills,browse')
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
