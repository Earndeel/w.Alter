"""Atomic CuaDriver backend, using Walter-owned state and portable contracts."""
from __future__ import annotations
import logging
import uuid
from typing import Any, Dict, Optional
from .capture import _CaptureMixin
from .input import _InputMixin
from .types import ActionResult, ComputerUseBackend
from .parse import _action_result_from

logger = logging.getLogger(__name__)

class DriverBackend(_CaptureMixin, _InputMixin, ComputerUseBackend):
    def __init__(self, permission_mode='standard', *, transport=None):
        if permission_mode != 'standard':
            raise ValueError('independent port requires standard permissions; host authorization is explicit')
        if transport is None:
            raise ValueError('explicit driver transport is required')
        self.permission_mode = permission_mode
        self._session = transport
        self._session_id = f'walter-{uuid.uuid4().hex}'
        self.ax_max_elements = int(getattr(self, 'config', {}).get('computer_use', {}).get('ax_max_elements', 100))
        self._clear_active_target()

    def start(self):
        try:
            self._session.start()
            self._session.call_tool('start_session', {'session': self._session_id})
        except Exception:
            self._clear_active_target()
            self._session.stop()
            raise

    def stop(self):
        try:
            if self._session._started:
                self._session.call_tool('end_session', {'session': self._session_id})
        finally:
            self._clear_active_target()
            self._session.stop()

    def is_available(self):
        return self._session is not None

    def _clear_active_target(self):
        self._active_pid = self._active_window_id = self._last_app = self._last_target = None
        self._snapshot_tokens = {}

    def _set_active_target(self, target):
        self._active_pid, self._active_window_id = target['pid'], target['window_id']
        self._snapshot_tokens = {}
        self._last_target = {'pid': self._active_pid, 'window_id': self._active_window_id}

    def bring_to_front(self, *, pid, window_id=None):
        return self._action('bring_to_front', {'pid': pid, 'window_id': window_id}, inject_session=False)

    def _action(self, name, args, *, inject_session=True):
        token = self._snapshot_tokens.get(args.get('element_index'))
        if token and self._session.supports_input_property(name, 'element_token'):
            args['element_token'] = token
        if inject_session:
            args.setdefault('session', self._session_id)
        try:
            out = self._session.call_tool(name, args)
        except Exception:
            self._clear_active_target()
            raise  # No replay or semantic success claim after an unknown completion.
        data, structured = out.get('data'), out.get('structuredContent') or {}
        message = (str(data.get('message', '')) if isinstance(data, dict) else data if isinstance(data, str) else '')
        meta = {k: v for part in (data, structured) if isinstance(part, dict) for k, v in part.items()}
        return _action_result_from(name, not out.get('isError'), message, meta, structured,
                                   requested_delivery=args.get('delivery_mode'))

    def move_cursor(self, x, y):
        if self._active_pid is None or self._active_window_id is None:
            return ActionResult(ok=False, action='move_cursor', code='target_required')
        return self._action('move_cursor', {'pid': self._active_pid, 'window_id': self._active_window_id, 'x': x, 'y': y})
