"""Thin MCP ports to independently installed Walter modules.

Imports are lazy: removing an optional module disables its own calls, not memory/skills.
No shell exec or secret-value tool is registered here. Operator grants come from server
policy, never from model-supplied arguments. The MCP client's permission gate still applies.
"""
from __future__ import annotations
import atexit,asyncio,importlib,json,os,re,stat,subprocess,sys
from pathlib import Path
from mcp.types import ImageContent,TextContent,ToolAnnotations

_pool=None

def _module(which,name):
    # The façade locates modules through the Walter path resolver, never by a hardcoded directory.
    from walter_platform.paths import module_root
    path=module_root(which)
    if not path.is_dir():raise ModuleNotFoundError('Walter module unavailable')
    if str(path) not in sys.path:sys.path.insert(0,str(path))
    return importlib.import_module(name)

def _error(module,exc):
    return json.dumps({'ok':False,'module':module,'error':type(exc).__name__,
                       'hint':'Run walter check for installation and dependency diagnostics.'})

def _policy(client):
    path=Path('/opt/walter-core/modules/computer-policy.json')
    info=path.stat()
    if info.st_uid not in {0,os.getuid()} or stat.S_IMODE(info.st_mode)&0o022:
        raise PermissionError('untrusted computer policy')
    data=json.loads(path.read_text())
    return frozenset(data.get('clients',{}).get(client,[]))

def _computer_pool():
    global _pool
    if _pool is None:
        operator=_module('computer','walter_computer.operator')
        config=_module('computer','walter_computer.config')
        _pool=operator.OperatorSessions(config.make_operator)
        atexit.register(_pool.close)
    return _pool

_ROUTER_WORD=re.compile(r'[A-Za-z0-9_.:/-]{1,64}')   # task, role, level, plan id: never a shell word
_REQUIRE=('','unrestricted','open_weights','video_input')
WALTER_LLM_URL='http://127.0.0.1:8894/v1/chat/completions'


def _router(*args,timeout=60):
    # Walter Router through its command on the PATH (its declared interface); arguments as a list, never a shell.
    out=subprocess.run(['walter-router',*args],capture_output=True,text=True,timeout=timeout)
    if out.returncode:raise RuntimeError('router command failed')
    return json.loads(out.stdout)


def _router_error(exc):
    return json.dumps({'ok':False,'module':'router','error':type(exc).__name__,
                       'hint':'walter-router health; walter check for installation diagnostics.'})


def _router_decision(request,task,level,require,conversation,*,agent):
    if (task and not _ROUTER_WORD.fullmatch(task)) or level not in ('','L1','L2','L3') or require not in _REQUIRE:
        raise ValueError('invalid task, level or require')
    if not (request or task):raise ValueError('request or task required')
    if require:args=['pick',task or 'general','--require',require]+(['--level',level] if level else [])
    else:args=(['route',request or task]+(['--task',task] if task else [])+(['--level',level] if level else [])
                +(['--context',conversation[:600]] if conversation else []))
    return _router(*args,*(['--agent'] if agent else []))


def router_brief():
    """Walter Router's own description for agents (tools, levels, specialities, generation, constraints)."""
    try:
        out=subprocess.run(['walter-router','brief'],capture_output=True,text=True,timeout=30)
        return out.stdout.strip() if out.returncode==0 else ''
    except Exception:return ''


def _llm_token():
    # This server's own walter-llm agent token, in the instance's state (0600), never in the code or the logs.
    root=subprocess.run(['walter','instance','path'],capture_output=True,text=True,timeout=30).stdout.strip()
    for line in (Path(root)/'state'/'core'/'llm.env').read_text().splitlines():
        if line.startswith('WALTER_LLM_TOKEN='):return line.split('=',1)[1].strip()
    raise PermissionError('no walter-llm token for this server')


def _walter_llm(model,prompt,timeout=900):
    import urllib.request
    body=json.dumps({'model':model,'messages':[{'role':'user','content':prompt}]}).encode()
    req=urllib.request.Request(WALTER_LLM_URL,data=body,headers={'Authorization':'Bearer '+_llm_token(),
                                                                 'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as resp:  # noqa: S310 (loopback gateway)
        data=json.loads(resp.read()); ran=resp.headers.get('X-Walter-Route')
    return data['choices'][0]['message']['content'],ran


def register(mcp,client='unknown',*,local_control=True):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def walter_modules(module: str='') -> str:
        """Discover Walter's installed modules, shared interfaces, dependencies and per-harness limits.
        These are installation declarations; walter check validates boundaries, walter_health probes services.
        Use before choosing a native equivalent. A missing module does not disable the others."""
        try:
            from walter_platform.registry import load,inspect_module
            rows=[m for m in load()['modules'] if not module or m['id']==module]
            return json.dumps({'modules':[dict(m,observed=inspect_module(m)) for m in rows]},ensure_ascii=False)
        except Exception as exc:return _error('registry',exc)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def secret_search(query: str='', kind: str='', limit: int=20) -> str:
        """Find Bitwarden entries via Walter Secrets. Returns metadata and handles, never passwords,
        tokens, OTP values or cookies. kind: login, card, identity, note, ssh_key or empty.
        Use secret_reference then the local walter-secret exec CLI under your host's execution permissions."""
        try:return json.dumps(_module('secrets','walter_secrets.service').search(query,kind or None,limit),ensure_ascii=False)
        except Exception as exc:return _error('secrets',exc)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def secret_reference(item: str,field: str) -> str:
        """Return a Walter Secret reference for an entry and field, without disclosing its value.
        References are identifiers, not authorization tokens. Bind locally with walter-secret exec;
        do not attempt Hermes placeholder substitution in another harness."""
        try:return json.dumps(_module('secrets','walter_secrets.service').reference(item,field),ensure_ascii=False)
        except Exception as exc:return _error('secrets',exc)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def walter_browse(query: str='',url: str='',objective: str='',expected_fields: dict|None=None,
                           required_fields: list[str]|None=None,content_only: bool=False,profile: str='',
                           capability: str='',session_id: str='',min_records: int=1,mode: str='auto') -> str:
        """Walter's shared web search and extraction engine, also used by Hermes. Supply query OR public URL.
        For URL reading set content_only=true; structured extraction uses expected_fields aliases and
        required_fields. Internal engine selection stays in Walter. Authenticated interaction uses browser_session."""
        args=dict(query=query or None,url=url or None,objective=objective,expected_fields=expected_fields,
                  required_fields=required_fields or [],content_only=content_only,profile=profile or None,
                  capability=capability or None,session_id=session_id or None,min_records=min_records,mode=mode)
        try:return await _module('browse','walter_browse').browse(args)
        except Exception as exc:return _error('browse',exc)

    # Walter Router: the same four tools as the Hermes plugin, same names. What they can do (specialities, levels,
    # generation, constraints) is the router's own brief, in the server instructions. The harness keeps its model.
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def walter_route(request: str='',task: str='',level: str='',require: str='',conversation: str='') -> str:
        """Which model Walter Router picks for a request: choice, why, execution routes with their price per million
        tokens (see the Walter Router section of the server instructions). Pass the request verbatim; leave task
        empty and the router classifies it; conversation = one line on earlier turns when the request depends on them.
        Changes nothing and runs no model."""
        try:return json.dumps(_router_decision(request,task,level,require,conversation,agent=True),ensure_ascii=False)
        except Exception as exc:return _router_error(exc)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,openWorldHint=True))
    def walter_run(goal: str,request: str='',task: str='',level: str='',conversation: str='',context: str='') -> str:
        """Have the model Walter Router picks answer a self-contained TEXT sub-task (analysis, comparison, code,
        writing, synthesis), in one call through walter-llm, without tools. goal = complete instructions (it does not
        see this conversation); context = facts it needs. Returns its answer and the route that ran it. Your own model
        stays yours; media: walter_generate."""
        try:
            d=_router_decision(request or goal[:500],task,level,'',conversation,agent=False)
            if not d.get('execution'):
                return json.dumps({'ok':False,'error':'text sub-tasks only: use walter_generate for media',
                                   'task':d.get('task')},ensure_ascii=False)
            model=d['task']+('/'+d['level'] if d.get('task')=='general' and d.get('level') else '')
            prompt=goal+('\n\nContexte :\n'+context if context else '')
            text,ran=_walter_llm(model,prompt)
            return json.dumps({'ok':True,'task':d['task'],'level':d.get('level'),'route':ran,'output':text},ensure_ascii=False)
        except Exception as exc:return _router_error(exc)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=True))
    def walter_generate(request: str,task: str='',role: str='',image_urls: list[str]|None=None,aspect_ratio: str='',
                        duration: int=0,resolution: str='',paid_fallback: bool=False) -> str:
        """Generate an image, video, music track or voice-over on the model Walter Router picks, prompt rewritten for
        it. COSTS MONEY: only when the user asked for it. role = video objective (premium, action, ugc, budget,
        default); image_urls = public URLs of input images. Returns local file paths, cost and the prompt used."""
        args=['generate',request]
        for flag,value in (('--task',task),('--role',role),('--aspect-ratio',aspect_ratio),('--resolution',resolution)):
            if value:
                if not _ROUTER_WORD.fullmatch(value):return json.dumps({'ok':False,'error':f'invalid {flag[2:]}'})
                args+=[flag,value]
        for url in image_urls or []:
            if not url.startswith(('https://','http://')):return json.dumps({'ok':False,'error':'image_urls must be URLs'})
            args+=['--image-url',url]
        if duration:args+=['--duration',str(int(duration))]
        if paid_fallback:args.append('--paid-fallback')
        try:return json.dumps(_router(*args,timeout=1800),ensure_ascii=False)
        except Exception as exc:return _router_error(exc)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def walter_plans(action: str='list',plan_id: str='',vendor: str='',plan: str='',price_usd_month: float|None=None,
                     models: list[str]|None=None,since: str='',until: str='',note: str='',why: str='') -> str:
        """The user's AI subscriptions as Walter Router knows them: list, or record a change the user tells you
        (set: new plan, price, end of an offer, included models; retire: cancellation). Plan ids lowercase-dashed
        (openai-plus, google-ai-pro). Only on the user's word: never invent a plan or a price."""
        if action not in ('list','set','retire') or (action!='list' and not _ROUTER_WORD.fullmatch(plan_id or '-')):
            return json.dumps({'ok':False,'error':'action list|set|retire; plan_id required to change a plan'})
        args=['plans',action]+([plan_id] if action!='list' else [])
        if action=='set':
            for flag,value in (('--vendor',vendor),('--plan',plan),('--since',since),('--until',until),('--note',note)):
                if value:args+=[flag,value]
            if price_usd_month is not None:args+=['--price',str(float(price_usd_month))]
            if models:args+=['--models',','.join(m for m in models if _ROUTER_WORD.fullmatch(m))]
        if action!='list' and why:args+=['--why',why]
        try:return json.dumps(_router(*args),ensure_ascii=False)
        except Exception as exc:return _router_error(exc)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=True))
    async def computer_use(session_id: str,action: str,arguments: dict|None=None):
        """Call Walter Computer Use directly without delegating to Hermes. Atomic actions: list_apps,
        list_windows, device_context, capture, click, type, key, scroll, drag, set_value, focus_app,
        launch_app, open_url, click_visual_ref, targeted_verify, wait, close. Capture an exact app
        before input; close when done. Host approvals and user task authorization apply to input/pixels.
        Server policy sets scopes; arguments cannot grant permissions. Vision requires a configured sensor."""
        try:
            if not local_control:
                return json.dumps({'ok':False,'code':'computer_requires_local_stdio_client'})
            namespace=client+':'+session_id
            result=await asyncio.to_thread(_computer_pool().call,namespace,action,arguments or {},grants=_policy(client))
            if isinstance(result,dict) and result.get('png_b64'):
                pixels=result.pop('png_b64')
                return [TextContent(type='text',text=json.dumps(result,ensure_ascii=False)),
                        ImageContent(type='image',data=pixels,mimeType='image/png')]
            return json.dumps(result,ensure_ascii=False,default=str)
        except Exception as exc:return _error('computer',exc)
