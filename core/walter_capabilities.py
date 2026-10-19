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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def model_route(task: str='',level: str='') -> str:
        """Read Walter Router's selected model for a task, or list tasks with an empty task.
        Does not change choices, buy credits or run a model. Codex/Claude keep their primary model."""
        if not re.fullmatch(r'[a-zA-Z0-9_-]{0,64}',task) or not re.fullmatch(r'[a-zA-Z0-9_-]{0,16}',level):
            return json.dumps({'ok':False,'error':'invalid task or level'})
        args=['walter-router','pick',task] if task else ['walter-router','tasks']
        if task and level:args+=['--level',level]
        try:
            out=subprocess.run(args,capture_output=True,text=True,timeout=30)
            if out.returncode:return json.dumps({'ok':False,'error':'router lookup failed','exit_code':out.returncode})
            return json.dumps(json.loads(out.stdout),ensure_ascii=False)
        except Exception as exc:return _error('router',exc)

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
