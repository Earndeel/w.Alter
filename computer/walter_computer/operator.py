"""Host-neutral, session-scoped Computer Use facade.

Authorization is a host-supplied per-call set of scopes. It must be granted by
trusted client policy, never copied from arbitrary model output. The facade
never substitutes for the host's approval/sandbox mechanism.
"""
from __future__ import annotations
from dataclasses import asdict, is_dataclass
import threading
import re
import time
from .driver import DriverBackend
from .device_lock import DeviceCallLock
from .lease import WorkflowLease, LEASE_ACTIONS
from .vision import vision_permission
from .input_safety import reject_unsafe
from .runtime import ActionOrigin
from .policy import WalterPolicyMixin, _handle_device_context_action, _handle_launch_app_action, _handle_open_url_action, _handle_vision_target_action, _handle_click_visual_ref_action, _handle_targeted_verify_action

class Operator(WalterPolicyMixin, DriverBackend):
    pass

READ_ACTIONS = frozenset({'capture', 'list_apps', 'list_windows', 'device_context', 'wait', 'targeted_verify', 'close'})
INPUT_ACTIONS = frozenset({'click', 'drag', 'scroll', 'type', 'key', 'set_value', 'focus_app', 'launch_app', 'open_url', 'click_visual_ref'})
ACTIONS = READ_ACTIONS | INPUT_ACTIONS | {'vision_target'} | LEASE_ACTIONS
_HANDLERS = {'device_context': _handle_device_context_action, 'launch_app': _handle_launch_app_action,
             'open_url': _handle_open_url_action, 'vision_target': _handle_vision_target_action,
             'click_visual_ref': _handle_click_visual_ref_action, 'targeted_verify': _handle_targeted_verify_action}


def required_scopes(action, arguments):
    if action not in ACTIONS:
        raise ValueError('unknown Walter Computer action')
    required = {'read'}
    if action in INPUT_ACTIONS or action in {'lease_acquire', 'lease_renew'}:
        required.add('input')
    if action in {'focus_app', 'launch_app', 'open_url'} or arguments.get('bring_to_front') or arguments.get('raise_window') or arguments.get('delivery_mode') == 'foreground':
        required.add('foreground')
    if action in {'capture', 'targeted_verify', 'launch_app', 'open_url'}:
        required.add('pixels')
    if action == 'vision_target':
        required |= {'pixels', 'vision'}
    return frozenset(required)


def _dispatch(backend, action, arguments):
    args = dict(arguments)
    if action in _HANDLERS:
        return _HANDLERS[action](backend, args)
    if action == 'capture':
        args.setdefault('mode', 'ax')
        result = backend.capture(**args)
        backend.arm_native_refs(result)
        if args['mode'] == 'ax':
            result.png_b64 = None
            result.png_bytes_len = 0
        return result
    if action == 'wait':
        return backend.wait(float(args.get('seconds', 1)))
    if action in {'list_apps', 'list_windows'}:
        if args:
            raise ValueError(f'{action} takes no arguments')
        return getattr(backend, action)()
    # Native input never silently retargets to an app named in a later call.
    if action == 'focus_app':
        return backend.focus_app(**args)
    requested_app = args.pop('app', None)
    if requested_app and str(requested_app).casefold() != str(backend._last_app).casefold():
        raise ValueError('input app differs from captured target; capture the exact app first')
    return getattr(backend, 'type_text' if action == 'type' else action)(**args)


class OperatorSessions:
    """Bounded session pool; serial calls, target state and grants isolated per ID.

    A shared lock also serializes device actions across clients. Caller owns
    session-ID namespace and must close sessions at client shutdown. Idle
    sessions are reclaimed before calls (default 15 minutes).
    """
    def __init__(self, factory, *, max_sessions=16, idle_seconds=900, lock_path=None):
        self.factory = factory
        self.device_lock = DeviceCallLock(lock_path)
        self.lease = WorkflowLease(self.device_lock.path)
        self._lease_sessions = set()
        self.max_sessions = max_sessions
        self.idle_seconds = idle_seconds
        self._sessions = {}
        self._lock = threading.RLock()

    def call(self, session_id, action, arguments=None, *, grants=frozenset({'read'}), origin=None, vision_authorization=None):
        if not isinstance(session_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', session_id):
            raise ValueError('invalid session_id')
        args = dict(arguments or {})
        required = required_scopes(action, args)
        origin = ActionOrigin(origin or ActionOrigin.FOREGROUND_USER)
        if refusal := reject_unsafe(action, args):
            return {'ok': False, 'code': 'unsafe_input_blocked', 'action': action, **refusal}
        missing = required - frozenset(grants)
        if missing:
            return {'ok': False, 'code': 'authorization_required', 'action': action, 'required_scopes': sorted(missing)}
        with self.device_lock.hold() as acquired:
            if not acquired:
                return {'ok': False, 'action': action, 'code': 'device_busy'}
            if action in LEASE_ACTIONS:
                result = self.lease.handle(session_id, action, args)
                if result.get('ok') and action in {'lease_acquire', 'lease_renew'}:
                    self._lease_sessions.add(session_id)
                if action == 'lease_release' and result.get('ok'):
                    self._lease_sessions.discard(session_id)
                return result
            if action != 'close' and not self.lease.allowed(session_id):
                return {'ok': False, 'action': action, 'code': 'device_reserved'}
            if action == 'close':
                self.lease.handle(session_id, 'lease_release', {})
                self._lease_sessions.discard(session_id)
            with vision_permission(vision_authorization):
                return self._call_locked(session_id, action, args, origin)

    def _call_locked(self, session_id, action, args, origin):
        with self._lock:
            now = time.monotonic()
            for stale, (_, accessed) in list(self._sessions.items()):
                if now - accessed > self.idle_seconds:
                    self._close(stale)
            if action == 'close':
                self._close(session_id)
                return {'ok': True, 'action': 'close'}
            if session_id not in self._sessions:
                if len(self._sessions) >= self.max_sessions:
                    return {'ok': False, 'code': 'session_capacity'}
                backend = self.factory()
                try:
                    backend.start()
                except Exception:
                    backend.stop()
                    raise
                self._sessions[session_id] = (backend, now)
            backend, _ = self._sessions[session_id]
            if origin is not None:
                backend._walter_origin = origin
            self._sessions[session_id] = (backend, now)
            try:
                result = _dispatch(backend, action, args)
            except Exception:
                self._close(session_id)
                raise
            return asdict(result) if is_dataclass(result) else result

    def _close(self, session_id):
        item = self._sessions.pop(session_id, None)
        if item is not None:
            item[0].stop()

    def close(self):
        with self.device_lock.hold() as acquired:
            if acquired:
                for session_id in self._lease_sessions:
                    self.lease.handle(session_id, 'lease_release', {})
                self._lease_sessions.clear()
        with self._lock:
            for session_id in list(self._sessions):
                self._close(session_id)
