"""Hermes adapter: configuration, host types, native transport and auxiliary vision only."""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
from typing import Any, Dict, Mapping
from dataclasses import dataclass, field
from tools.computer_use.backend import ActionResult, CaptureResult as HostCaptureResult
from tools.computer_use.cua_backend import CuaDriverBackend
from ..policy import WalterPolicyMixin
from ..device_lock import DeviceCallLock
from ..lease import WorkflowLease, LEASE_ACTIONS
from ..policy import CaptureStrategy, CaptureTarget, SafeWindowStrategy, register_capture_strategy, compact_ax_state, _handle_launch_app_action, _handle_open_url_action, _handle_device_context_action, _handle_vision_target_action, _handle_click_visual_ref_action, _handle_targeted_verify_action
from ..policy import _configured_driver_command as _driver_command


def _load_hermes_config():
    from hermes_cli.config import load_config
    return load_config()


def _configured_driver_command(config=None):
    return _driver_command(_load_hermes_config() if config is None else config)


@dataclass
class CaptureResult(HostCaptureResult):
    capture_valid: bool | None = None
    capture_error: dict | None = None
    capture_coverage: dict = field(default_factory=dict)


class WalterCuaBackend(WalterPolicyMixin, CuaDriverBackend):
    _action_result = ActionResult
    _capture_result = CaptureResult

    def __init__(self, permission_mode="standard", *, observer_enabled=None):
        super().__init__(permission_mode=permission_mode, observer_enabled=observer_enabled,
                         config=_load_hermes_config(), vision_sensor=self._hermes_vision_sensor)

    def _hermes_vision_sensor(
        self, request: Any, capture: CaptureResult
    ) -> Dict[str, Any]:
        """Locate one target in one crop; never select or execute an action."""
        if not capture.png_b64:
            raise ValueError("targeted crop contains no pixels")
        try:
            from hermes_constants import get_hermes_dir
            from model_tools import _run_async
            from tools.vision_tools import vision_analyze_tool
        except Exception as exc:
            raise RuntimeError("production vision sensor is unavailable") from exc
        suffix = ".jpg" if capture.image_mime_type == "image/jpeg" else ".png"
        cache_dir = get_hermes_dir("cache/vision", "temp_vision_images")
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"walter_target_{hashlib.sha256(capture.png_b64.encode()).hexdigest()[:16]}{suffix}"
        try:
            path.write_bytes(base64.b64decode(capture.png_b64, validate=False))
            prompt = (
                "You are a visual sensor, not a planner. Locate only the target described "
                "by the goal inside this cropped application image. Return strict JSON only: "
                '{"bounds":[x,y,width,height],"confidence":0.0,"description":"short"}. '
                "Bounds are pixels relative to this returned crop image. Do not propose, "
                "select, or execute any action. If uncertain, return confidence below 0.95.\n"
                + json.dumps(request.compact(), ensure_ascii=False, separators=(",", ":"))
            )
            raw = _run_async(vision_analyze_tool(str(path), prompt))
        finally:
            try:
                path.unlink()
            except OSError:
                pass
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        analysis = parsed.get("analysis") if isinstance(parsed, Mapping) else None
        if isinstance(analysis, str):
            text = analysis.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
            parsed = json.loads(text)
        if not isinstance(parsed, Mapping):
            raise ValueError("vision sensor response is not structured")
        return dict(parsed)

def _factory(*, permission_mode: str = "standard") -> WalterCuaBackend:
    required = ("start", "stop", "capture", "list_windows")
    missing = [
        name for name in required if not callable(getattr(CuaDriverBackend, name, None))
    ]
    if missing:
        raise RuntimeError(
            "Incompatible Hermes computer-use host contract; missing "
            f"CuaDriverBackend methods: {', '.join(missing)}"
        )
    return WalterCuaBackend(permission_mode=permission_mode)


_WALTER_DEVICE_PROMPT = """Walter Operator is a device-control component, never an agent or planner.
Hermes alone interprets the user goal, chooses each computer_use action, handles surprises, and decides completion.
Use atomic actions and the natural loop: observe -> Hermes reasons -> act -> compact post-action facts.
Unexpected dialogs, missing windows, errors, or changed UI must be returned as facts for Hermes to interpret.
External information/research belongs to Walter Browse; native GUI, files, dialogs, and settings belong to Operator.
Load only the smallest relevant Walter Operator skill/reference when app or action knowledge is useful.
"""


def register(ctx) -> None:
    """Register Walter's atomic device backend without semantic goal routing."""
    required = (
        "register_computer_use_backend",
        "register_computer_use_action",
        "register_system_prompt_section",
    )
    missing = [name for name in required if not callable(getattr(ctx, name, None))]
    if missing:
        raise RuntimeError(
            "Hermes is missing Walter computer-use extension seams: "
            + ", ".join(missing)
        )
    driver_command = _configured_driver_command()
    if driver_command is not None:
        os.environ["HERMES_CUA_DRIVER_CMD"] = driver_command
    ctx.register_computer_use_backend("walter", _factory)
    ctx.register_computer_use_action(
        "launch_app",
        _handle_launch_app_action,
        properties={
            "bundle_id": {"type": "string", "description": "Exact native bundle ID when known."},
            "urls": {"type": "array", "items": {"type": "string"}, "description": "Optional URLs opened mechanically with the launch."},
            "additional_arguments": {"type": "array", "items": {"type": "string"}},
            "creates_new_application_instance": {"type": "boolean", "default": False},
        },
        destructive=False,
    )
    ctx.register_computer_use_action(
        "open_url",
        _handle_open_url_action,
        properties={},
        destructive=False,
    )
    ctx.register_computer_use_action(
        "device_context", _handle_device_context_action, properties={}, destructive=False
    )
    ctx.register_computer_use_action(
        "vision_target",
        _handle_vision_target_action,
        properties={
            "visual_query": {"type": "string"},
            "snapshot_id": {"type": "string"},
            "region": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
            "source_capture_dimensions": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
            "candidate_window_bounds": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
        },
        destructive=False,
    )
    ctx.register_computer_use_action(
        "click_visual_ref",
        _handle_click_visual_ref_action,
        properties={
            "visual_ref": {"type": "string"},
            "snapshot_id": {"type": "string"},
        },
        destructive=False,
    )
    ctx.register_computer_use_action(
        "targeted_verify",
        _handle_targeted_verify_action,
        properties={
            "snapshot_id": {"type": "string"},
        },
        destructive=False,
    )
    ctx.register_system_prompt_section(
        "walter-computer-use-boundary",
        _WALTER_DEVICE_PROMPT,
        position="after_memory",
        max_chars=900,
    )


__all__ = [
    "CaptureStrategy",
    "CaptureTarget",
    "SafeWindowStrategy",
    "WalterCuaBackend",
    "compact_ax_state",
    "register_capture_strategy",
]

# Current Hermes releases expose public tool overrides instead of backend/action
# registration. Use that seam without changing or monkey-patching host objects.
_register_extended_host = register


def _native_contract():
    from tools.computer_use import tool as host
    required = ('_reject_unsafe', '_request_approval', '_dispatch', '_scoped_sid',
                '_cua_permission_mode', 'get_computer_use_schema')
    missing = [name for name in required if not callable(getattr(host, name, None))]
    if missing:
        raise RuntimeError('incompatible Hermes Computer Use contract: ' + ', '.join(missing))
    import inspect
    inspect.signature(host._request_approval).bind('click', {})
    inspect.signature(host._dispatch).bind(None, 'capture', {}, fence=lambda: None, session_id='compat')
    if not isinstance(getattr(host, '_ACTIONS', None), dict):
        raise RuntimeError('incompatible Hermes action metadata')
    return host


class _NativeSessions:
    """Hermes session/profile/mode isolation around the Walter backend."""
    def __init__(self):
        import threading
        self.lock = threading.RLock()
        self.backends = {}

    def close(self, key=None):
        with self.lock:
            keys = [key] if key is not None else list(self.backends)
            for candidate in keys:
                value = self.backends.pop(candidate, None)
                if value is not None:
                    value[0].stop()

    def backend(self, host, session_id):
        import time
        key = host._scoped_sid(session_id)
        now = time.monotonic()
        for stale, (_, _, used) in list(self.backends.items()):
            if now - used > 900:
                self.close(stale)
        mode = host._cua_permission_mode(session_id)
        value = self.backends.get(key)
        if value is not None and value[1] != mode:
            self.close(key)
            value = None
        if value is None:
            if len(self.backends) >= 16:
                raise RuntimeError('Walter Computer session capacity reached')
            backend = _factory(permission_mode=mode)
            try:
                backend.start()
            except Exception:
                backend.stop()
                raise
        else:
            backend = value[0]
        self.backends[key] = (backend, mode, now)
        return backend


_NATIVE_SESSIONS = _NativeSessions()
_WORKFLOW_LEASES = {}


def _workflow_lease(lock):
    key = str(lock.path)
    if key not in _WORKFLOW_LEASES:
        _WORKFLOW_LEASES[key] = WorkflowLease(lock.path)
    return _WORKFLOW_LEASES[key]


def _override_handler(extra_actions):
    host = _native_contract()
    from tools.bot_desktop import lease

    def handle(args, **kwargs):
        action = str(args.get('action') or '').strip().lower()
        session_id = str(kwargs.get('session_id') or '')
        if not action or action not in host._ACTIONS and action not in extra_actions and action not in LEASE_ACTIONS:
            return json.dumps({'ok': False, 'error': 'missing or unknown action'})
        try:
            admitted = lease.assert_agent_may_act()
            if (error := host._reject_unsafe(action, args)) is not None:
                return error
            # The built-in gate remains authoritative, including YOLO/session
            # grants and fail-closed unattended behavior. New mutators also gate.
            native = host._ACTIONS.get(action)
            mutates = (native is not None and native.destructive) or action in {
                'launch_app', 'open_url', 'click_visual_ref', 'lease_acquire', 'lease_renew'}
            scopes = ([action] if mutates else []) + (
                ['bring_to_front'] if action in {'focus_app', 'launch_app', 'open_url'} or args.get('bring_to_front') or args.get('raise_window') else [])
            for scope in scopes:
                if (error := host._request_approval(scope, {**args, 'delivery_mode': 'foreground'} if scope == 'bring_to_front' else args)) is not None:
                    return error
            lock = DeviceCallLock()
            with lock.hold() as acquired:
                if not acquired:
                    return json.dumps({'ok': False, 'action': action, 'code': 'device_busy'})
                reservation = _workflow_lease(lock)
                owner = host._scoped_sid(session_id)
                if action in LEASE_ACTIONS:
                    return json.dumps(reservation.handle(owner, action, args))
                if not reservation.allowed(owner):
                    return json.dumps({'ok': False, 'action': action, 'code': 'device_reserved'})
                return admitted_call(action, args, session_id, admitted)
        except lease.HumanHasControl as exc:
            return json.dumps({'ok': False, 'action': action, 'code': 'human_has_control', 'error': str(exc)})
        except Exception as exc:
            return json.dumps({'ok': False, 'action': action, 'code': 'walter_computer_error', 'error': str(exc)})

    def admitted_call(action, args, session_id, admitted):
        try:
            with _NATIVE_SESSIONS.lock:
                lease.assert_agent_may_act()
                def fence():
                    if lease.get().epoch != admitted.epoch:
                        raise lease.HumanHasControl('Human control changed; result discarded. Capture fresh state.')
                fence()
                backend = _NATIVE_SESSIONS.backend(host, session_id)
                backend._walter_result_fence = fence
                previous = getattr(backend, '_walter_latest_capture', None)
                if action in extra_actions:
                    result = extra_actions[action][0](backend, args)
                    fence()
                    result = json.dumps(result, ensure_ascii=False)
                else:
                    result = host._dispatch(backend, action, args, fence=fence, session_id=session_id or None)
                fence()
                latest = getattr(backend, '_walter_latest_capture', None)
                if latest is not None and latest is not previous:
                    backend.arm_native_refs(latest)
                return result
        except lease.HumanHasControl as exc:
            return json.dumps({'ok': False, 'action': action, 'code': 'human_has_control', 'error': str(exc)})
        except Exception as exc:
            return json.dumps({'ok': False, 'action': action, 'code': 'walter_computer_error', 'error': str(exc)})
    return handle


def register(ctx):
    """Prefer a backend seam when available; otherwise public, explicit tool override."""
    if all(callable(getattr(ctx, name, None)) for name in (
        'register_computer_use_backend', 'register_computer_use_action')):
        return _register_extended_host(ctx)
    if not callable(getattr(ctx, 'register_tool', None)):
        raise RuntimeError('Hermes is missing Walter computer-use extension seams')
    host = _native_contract()
    from copy import deepcopy
    import atexit

    class Extension:
        def __init__(self): self.actions = {}; self.prompt = None
        def register_computer_use_backend(self, *args): pass
        def register_computer_use_action(self, name, handler, **options): self.actions[name] = (handler, options)
        def register_system_prompt_section(self, *args, **kwargs): self.prompt = (args, kwargs)
    extension = Extension()
    _register_extended_host(extension)
    schema = deepcopy(host.get_computer_use_schema())
    parameters = schema.get('parameters', schema.get('function', {}).get('parameters'))
    if not isinstance(parameters, dict):
        raise RuntimeError('unsupported Hermes computer_use schema envelope')
    properties = parameters['properties']
    properties['action']['enum'] += list(extension.actions) + sorted(LEASE_ACTIONS)
    properties['ttl_seconds'] = {'type': 'number', 'minimum': 1, 'maximum': 300,
                                'description': 'Task reservation TTL; default 120. Acquire before a multi-step desktop task; renew or release explicitly.'}
    for _, options in extension.actions.values():
        properties.update(options['properties'])
    # open_url was a native backend helper, not a native schema field.
    properties.setdefault('url', {'type':'string', 'description':'URL to open in the explicitly selected app.'})
    ctx.register_tool(name='computer_use', toolset='computer_use', schema=schema,
                      handler=_override_handler(extension.actions), check_fn=lambda: True,
                      override=True, description='Walter atomic device control with Hermes approvals')
    if extension.prompt:
        ctx.register_system_prompt_section(*extension.prompt[0], **extension.prompt[1])
    if callable(getattr(ctx, 'register_hook', None)):
        def finalize(**kwargs):
            sid = kwargs.get('session_id')
            if sid:
                key = host._scoped_sid(str(sid))
                lock = DeviceCallLock()
                with lock.hold() as acquired:
                    if acquired:
                        _workflow_lease(lock).handle(key, 'lease_release', {})
                _NATIVE_SESSIONS.close(key)
        ctx.register_hook('on_session_finalize', finalize)
    if callable(getattr(ctx, 'on_unload', None)):
        ctx.on_unload(_NATIVE_SESSIONS.close)
    atexit.register(_NATIVE_SESSIONS.close)
