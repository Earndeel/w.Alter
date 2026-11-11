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


def _run_env():
    # Walter Run Plane: the current run travels to the module as WALTER_RUN_ID (how it is found is the adapter's
    # detail, hooks/runctx.py: explicit environment, else the record of this harness process).
    try:
        import importlib.util
        spec=importlib.util.spec_from_file_location('walter_runctx',os.path.join(os.path.dirname(os.path.abspath(__file__)),'hooks','runctx.py'))
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        return {**os.environ,**mod.env()}
    except Exception:
        return None


def _router(*args,timeout=60,stdin=None):
    # Walter Router through its command on the PATH (its declared interface); arguments as a list, never a shell.
    out=subprocess.run(['walter-router',*args],input=stdin,capture_output=True,text=True,timeout=timeout,env=_run_env())
    if out.returncode:raise RuntimeError('router command failed')
    return json.loads(out.stdout)


def _router_error(exc):
    return json.dumps({'ok':False,'module':'router','error':type(exc).__name__,
                       'hint':'walter-router health; walter check for installation diagnostics.'})


def _route_args(request,task,level,model,provider,require,conversation):
    for value in (task,model,provider):
        if value and not _ROUTER_WORD.fullmatch(value):raise ValueError('invalid task, model or provider')
    if level not in ('','L1','L2','L3') or require not in _REQUIRE:raise ValueError('invalid level or require')
    if not (request or task or model):raise ValueError('request, task or model required')
    if model:return ['route',request or model,'--model',model,*(['--provider',provider] if provider else []),
                     *(['--task',task] if task else [])]
    if require:return ['pick',task or 'general','--require',require,*(['--level',level] if level else [])]
    return (['route',request or task]+(['--task',task] if task else [])+(['--level',level] if level else [])
            +(['--context',conversation[:600]] if conversation else []))


def router_brief():
    """Walter Router's own description for agents (tools, levels, specialities, generation, constraints)."""
    try:
        out=subprocess.run(['walter-router','brief'],capture_output=True,text=True,timeout=30)
        return out.stdout.strip() if out.returncode==0 else ''
    except Exception:return ''


def module_layer(tools,form='full'):
    """The 'Modules W.Alter' layer composed by walter-context (every module's level-1 brief, or one line each in
    form 'm0'), for this server's real tool inventory. Empty on any failure: the caller keeps its previous instructions."""
    try:
        args=['walter-context','capability','all','--form',form]
        for t in tools:args+=['--tool',t]
        out=subprocess.run(args,capture_output=True,text=True,timeout=60)
        doc=json.loads(out.stdout)
        return doc['content'] if doc.get('injection_allowed') and isinstance(doc.get('content'),str) else ''
    except Exception:return ''


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
    def module_guide(module: str='') -> str:
        """Detailed guide of a W.Alter module (manifest/GUIDE.md in its folder): components, interfaces per runtime,
        privacy and limits. Each module's level 1 (what it is, how to use it) is already in your instructions;
        open the guide only when the task needs more. Without module: where each module's presentation lives."""
        try:
            from walter_platform import presentation
            return presentation.guide(module) if module else json.dumps(presentation.catalog(),ensure_ascii=False)
        except Exception as exc:return _error(module or 'presentation',exc)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def module_index(module: str,section: str='',offset: int=0,limit: int=20) -> str:
        """Level 2 of a W.Alter module: what it contains, kept up to date by the module itself (e.g. skills by
        domain, router tasks). Without section: the overview; with section: one bounded page (next_offset)."""
        try:
            from walter_platform import presentation
            return json.dumps(presentation.index(module,section,offset,limit),ensure_ascii=False)
        except Exception as exc:return _error(module,exc)

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

    # Walter Router: the same tools as the Hermes plugin, same names; every decision and every run is the router's
    # (`walter-router route | run | ask | plans`). What they can do is the router's brief, in the server instructions.
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def walter_route(request: str='',task: str='',level: str='',model: str='',provider: str='',require: str='',
                     conversation: str='') -> str:
        """Which model Walter Router picks for a request (section Walter Router of the server instructions), with
        its execution routes and their price per million tokens. model/provider only when the user names them
        (exactly that one, or why it cannot run). Changes nothing, runs nothing."""
        try:return json.dumps(_router(*_route_args(request,task,level,model,provider,require,conversation),'--agent'),
                              ensure_ascii=False)
        except Exception as exc:return _router_error(exc)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=True))
    def walter_run(request: str,goal: str='',context: str='',task: str='',level: str='',model: str='',provider: str='',
                   require: str='',conversation: str='',toolsets: list[str]|None=None,max_turns: int=0,
                   budget_seconds: int=0,role: str='',image_urls: list[str]|None=None,aspect_ratio: str='',
                   duration: int=0,resolution: str='',paid_fallback: bool=False,constraints: dict|None=None,
                   output_schema: dict|None=None,persist: str='') -> str:
        """Do the job on the model Walter Router picks (or the one the user named, never replaced). TEXT: a sub-agent
        with Walter's tools (web through walter_browse, skills, memory) — executed by Walter Engine (a delegated
        session: reads allowed, anything needing the owner refused) once the instance binds walter_run to it, else on
        the Router's own loop; a model named by the owner always runs exactly — goal = complete instructions;
        it does not see this conversation but gets a context built for its task (mission, Walter modules, matching
        skills, memory); context = anything more it needs. constraints = {"geo": {"zone", "pays", "devise", "langue"},
        …} for local research; output_schema = the JSON its answer must follow; persist="observations" stores each
        item of its answer's "observations" list as a sourced observation of the current run. IMAGE / VIDEO / MUSIC
        / VOICE: generated, files returned — COSTS MONEY, only when the user asked. Your own model stays yours."""
        spec={k:v for k,v in dict(request=request,goal=goal,context=context,task=task,level=level,model=model,
              provider=provider,require=require,conversation=conversation,toolsets=toolsets,max_turns=max_turns,
              budget_seconds=budget_seconds,role=role,image_urls=image_urls,aspect_ratio=aspect_ratio,duration=duration,
              resolution=resolution,paid_fallback=paid_fallback,constraints=constraints,output_schema=output_schema,
              persist=persist).items() if v not in ('',0,None,[],False,{})}
        if spec.get('persist') not in (None,'observations'):
            return json.dumps({'ok':False,'error':'persist must be "observations" or empty'})
        for key in ('task','level','model','provider','require','role','aspect_ratio','resolution'):
            if key in spec and not _ROUTER_WORD.fullmatch(str(spec[key])):
                return json.dumps({'ok':False,'error':f'invalid {key}'})
        if any(not str(u).startswith(('https://','http://')) for u in spec.get('image_urls') or []):
            return json.dumps({'ok':False,'error':'image_urls must be URLs'})
        budget=max(60,min(int(budget_seconds or 900),3600))
        try:return json.dumps(_router('run',stdin=json.dumps(spec),timeout=3*budget+2700),ensure_ascii=False)
        except Exception as exc:return _router_error(exc)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True,openWorldHint=True))
    def walter_decide(question: str,options: dict[str,str],context: str='') -> str:
        """The router's decision model for a quick choice of your own: sort, yes/no, one option among several, many
        times over (a fraction of a second, a fraction of a cent). options = name -> meaning (at least two).
        Returns the choice, its confidence and the probabilities."""
        if len(options or {})<2 or any(not _ROUTER_WORD.fullmatch(str(k)) for k in options):
            return json.dumps({'ok':False,'error':'at least two options with simple names'})
        args=['ask',question,*[x for k,v in options.items() for x in ('--option',f'{k}={v}')]]+(['--context',context] if context else [])
        try:return json.dumps(_router(*args,timeout=40),ensure_ascii=False)
        except Exception as exc:return _router_error(exc)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True,openWorldHint=True))
    def audio_transcribe(paths: list[str]) -> str:
        """Transcribe audio files on the VM (voice notes from Beeper/WhatsApp/Telegram, .ogg .opus .m4a .mp3 .wav…)
        by the Router's `stt` poste: the way to read a voice note, never a provider key under walter-secret exec
        (its output is discarded). Up to 20 files, 25 MB each. Returns per file {ok, text|error}."""
        files=[str(x) for x in (paths or []) if str(x).strip()]
        if not files or len(files)>20 or any(not x.startswith('/') for x in files):
            return json.dumps({'ok':False,'error':'1 to 20 absolute file paths'})
        try:return json.dumps(_router('transcribe',*files,'--source',f'mcp-{client}',timeout=200*len(files)+30),ensure_ascii=False)
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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,openWorldHint=True))
    def walter_web(message: str,service: str='',model: str='',files: list[str]|None=None,conversation: str='',
                   request_id: str='',timeout_s: int=0) -> str:
        """Talk to a web chat service the user enabled (Walter Router rule, browser, no Walter LLM): the message
        goes as is, the reply comes back verbatim. service omitted = the only enabled one. model ONLY when the user
        asks (words of the service's own picker, e.g. a model name and/or a reasoning level); omitted = the model
        already selected there, nothing is changed. files = local paths attached (max 10, 50 MB each); produced
        images/files come back as local paths in files[].path. conversation = a named thread kept across calls;
        request_id = idempotent (a retry returns the same answer, never sends twice). Slow (seconds to minutes):
        only when the user asks for that service or for what it alone does."""
        for value in (service,conversation,request_id):
            if value and not _ROUTER_WORD.fullmatch(value):return json.dumps({'ok':False,'error':'invalid service, conversation or request_id'})
        spec={k:v for k,v in dict(message=message,service=service,model=model,files=files,conversation=conversation,
              request_id=request_id,timeout_s=timeout_s).items() if v not in ('',0,None,[])}
        try:
            out=subprocess.run(['walter-router','web'],input=json.dumps(spec),capture_output=True,text=True,
                               timeout=min(int(timeout_s or 300),600)+180,env=_run_env())
            return json.dumps(json.loads(out.stdout),ensure_ascii=False)
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


# ---- Toolset per client (lot 3 C11, 2026-11-07) -------------------------------------------------------------------
# A client may list only a core set of Walter tools (config/toolsets.toml, keyed by WALTER_CLIENT_TAG; env
# WALTER_TOOLSET / WALTER_MODULE_LAYER override it, for a stage test). The other tools stay registered in this server
# and reachable through `walter_call`, with their own argument validation. Fixed for the life of the server process
# (one tool list per session: the provider cache keeps the tools prefix).
TOOLSETS = Path(__file__).resolve().parent / 'config' / 'toolsets.toml'
LAYER_FORMS = ('full', 'm0')


def client_profile(client, path=TOOLSETS):
    """{'name', 'toolset': list of listed tools or None (= all), 'module_layer': 'full'|'m0'} for this client."""
    import tomllib
    try:conf=tomllib.loads(Path(path).read_text())
    except FileNotFoundError:conf={}
    own=(conf.get('clients') or {}).get(client) or {}
    name=os.environ.get('WALTER_TOOLSET') or own.get('toolset') or 'all'
    form=os.environ.get('WALTER_MODULE_LAYER') or own.get('module_layer') or 'full'
    if form not in LAYER_FORMS:raise ValueError('unknown module layer form')
    if name=='all':return {'name':'all','toolset':None,'module_layer':form}
    tools=(conf.get('toolsets') or {}).get(name)
    if not isinstance(tools,list) or not all(isinstance(t,str) and t for t in tools):raise ValueError('unknown toolset')
    return {'name':name,'toolset':list(tools),'module_layer':form}


def _summary(description):
    return (description or '').strip().split('\n\n')[0].replace('\n',' ').strip()


def apply_toolset(mcp,keep):
    """List only `keep` (None = everything); the other tools move behind `walter_call`. Returns the hidden names."""
    if keep is None:return []
    manager=mcp._tool_manager
    hidden={t.name:t for t in manager.list_tools() if t.name not in set(keep)}
    for name in hidden:manager.remove_tool(name)
    if not hidden:return []

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,openWorldHint=True))
    async def walter_call(tool: str='',arguments: dict|None=None,describe: bool=False) -> str:
        """Call a W.Alter tool that is not in your tool list (the module presentations name them: vault_get,
        memory_events, logs_timeline, skill_propose…). Without tool: their names and one-line summaries.
        With describe=true: that tool's full description and parameters. Otherwise runs it with `arguments`."""
        if not tool:
            return json.dumps({'tools':[{'name':n,'summary':_summary(t.description)} for n,t in sorted(hidden.items())]},
                              ensure_ascii=False)
        target=hidden.get(tool)
        if target is None:
            return json.dumps({'error':'not_a_hidden_tool','hint':'call listed tools directly','hidden':sorted(hidden)})
        if describe:
            return json.dumps({'name':tool,'description':target.description,'parameters':target.parameters},ensure_ascii=False)
        result=await target.run(arguments or {})
        return result if isinstance(result,str) else json.dumps(result,ensure_ascii=False,default=str)
    return sorted(hidden)


def toolset_note(hidden):
    """One instruction line for a client with a core toolset: where the other tools are."""
    if not hidden:return ''
    return ("## Outils W.Alter non listés\n"
            f"{len(hidden)} outils W.Alter ne sont pas dans ta liste pour l'alléger : {', '.join(hidden)}. "
            "Appelle-les directement avec `walter_call(tool, arguments)` quand la fiche du module donne leurs "
            "paramètres ; sinon `walter_call(tool, describe=true)` les donne d'abord.")
