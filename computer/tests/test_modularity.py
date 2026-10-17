import ast
import base64
from pathlib import Path
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from types import SimpleNamespace
import pytest

from walter_computer.operator import Operator, OperatorSessions, required_scopes
from walter_computer.policy import SafeWindowStrategy
from walter_computer.runtime import UserPresence, VisualRefStore, VisualRefStale
from walter_computer.transport import normalize_result

ROOT = Path(__file__).resolve().parents[1]

class FakeTransport:
    def __init__(self):
        self._started = False
        self.capabilities_discovered = True
        self.calls = []
        self.token = 'snapshot-A'
        self.fail = False
    def start(self): self._started = True
    def stop(self): self._started = False
    def supports_input_property(self, *args): return True
    def supports_capability(self, *args, **kwargs): return True
    def _has_tool(self, name): return True
    def call_tool(self, name, args, **kwargs):
        self.calls.append((name, dict(args)))
        if self.fail and name == 'click':
            raise RuntimeError('completion unknown')
        payload = {}
        if name == 'list_windows':
            payload = {'windows': [{'pid': 42, 'window_id': 7, 'app_name': 'Demo', 'title': 'Demo', 'is_on_screen': True, 'bounds': {'width': 800, 'height': 600}}]}
        if name == 'get_window_state':
            payload = {'elements': [{'element_index': 1, 'role': 'AXButton', 'label': 'Synthetic', 'frame': {'x': 10, 'y': 20, 'w': 40, 'h': 20}, 'element_token': self.token}]}
        if name == 'click':
            payload = {'effect': 'confirmed', 'verified': True}
        return {'data': '', 'images': [], 'structuredContent': payload, 'isError': False}
    def _call_tool_via_cli(self, *args): raise RuntimeError('no secondary transport')


def operator(transport=None):
    op = Operator(config={'computer_use': {}}, transport=transport or FakeTransport(), observer_enabled=False)
    op.presence = SimpleNamespace(resolve=lambda **kwargs: UserPresence.unknown(observed_at=time.time()))
    return op


def test_import_without_hermes_or_optional_dependencies():
    script = "import sys; sys.path.insert(0, sys.argv[1]); from walter_computer.operator import Operator; assert not any(x.startswith(('hermes_cli','tools.computer_use')) for x in sys.modules)"
    subprocess.run([sys.executable, '-I', '-S', '-c', script, str(ROOT)], check=True)


def test_no_harness_imports_outside_port():
    for path in (ROOT / 'walter_computer').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith(('hermes', 'tools.', 'model_tools'))


def test_exact_target_and_snapshot_token_preserved():
    transport = FakeTransport()
    op = operator(transport)
    capture = op.capture(mode='ax', app='Demo', pid=42, window_id=7)
    op.arm_native_refs(capture)
    result = op.click(element=1)
    assert result.ok and result.effect == 'confirmed'
    name, args = transport.calls[-1]
    assert name == 'click'
    assert (args['pid'], args['window_id'], args['element_token']) == (42, 7, 'snapshot-A')


def test_no_target_cannot_dispatch_input():
    op = operator()
    result = op.click(element=1)
    assert not result.ok
    assert not any(name == 'click' for name, _ in op._session.calls)


def test_snapshot_replacement_disarms_managed_refs():
    op = operator()
    op.arm_native_refs(op.capture(mode='ax', app='Demo', pid=42, window_id=7))
    op._session.token = 'snapshot-B'
    op.capture(mode='ax', app='Demo', pid=42, window_id=7)
    result = op.click(element=1)
    assert not result.ok
    assert result.code in {'stale_element_ref', 'snapshot_changed', 'native_ref_stale', 'stale_ref', 'stale_element_token'}


def test_failed_capture_clears_previous_target():
    op = operator()
    op.capture(mode='ax', app='Demo', pid=42, window_id=7)
    op.capture(mode='ax', app='Missing')
    assert op._active_pid is None
    assert not op.click(x=20, y=30).ok


def test_denied_input_does_not_create_transport():
    def factory():
        raise AssertionError('must not instantiate transport')
    pool = OperatorSessions(factory)
    result = pool.call('test', 'click', {'element': 1})
    assert result['code'] == 'authorization_required'
    assert result['required_scopes'] == ['input']


def test_pixels_and_foreground_have_separate_scopes():
    assert required_scopes('capture', {'mode': 'ax'}) == {'read', 'pixels'}
    assert required_scopes('click', {'bring_to_front': True}) == {'read', 'input', 'foreground'}
    assert required_scopes('vision_target', {}) == {'read', 'pixels', 'vision'}


def test_independent_sessions_and_cleanup():
    backends = []
    def factory():
        backend = operator(); backends.append(backend); return backend
    pool = OperatorSessions(factory)
    pool.call('A', 'capture', {'mode': 'ax', 'app': 'Demo', 'pid': 42, 'window_id': 7}, grants={'read', 'pixels'})
    result = pool.call('B', 'click', {'element': 1}, grants={'read', 'input'})
    assert not result['ok']
    assert backends[0]._session_id != backends[1]._session_id
    pool.close()
    assert all(not b._session._started for b in backends)


def test_transport_failure_is_not_replayed_and_discards_session():
    op = operator()
    pool = OperatorSessions(lambda: op)
    pool.call('A', 'capture', {'mode': 'ax', 'app': 'Demo', 'pid': 42, 'window_id': 7}, grants={'read', 'pixels'})
    op._session.fail = True
    with pytest.raises(RuntimeError, match='completion unknown'):
        pool.call('A', 'click', {'element': 1}, grants={'read', 'input'})
    assert len([name for name, _ in op._session.calls if name == 'click']) == 1
    assert 'A' not in pool._sessions
    assert op._active_pid is None


def test_driver_error_and_native_image_metadata_preserved():
    result = normalize_result({'isError': True, 'content': [{'type':'text','text':'denied'}, {'type':'image','data':'synthetic','mimeType':'image/png'}]})
    assert result['isError'] is True
    assert result['image_mime_types'] == ['image/png']


def test_sessions_serialized_and_idle_closed():
    class Backend:
        def __init__(self): self.started=False; self.active=0; self.peak=0
        def start(self): self.started=True
        def stop(self): self.started=False
        def list_apps(self):
            self.active+=1; self.peak=max(self.peak,self.active); time.sleep(.01); self.active-=1
            return []
    backend=Backend(); pool=OperatorSessions(lambda:backend,idle_seconds=0.03)
    threads=[threading.Thread(target=lambda:pool.call('A','list_apps')) for _ in range(4)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert backend.peak == 1
    time.sleep(.04)
    pool.call('B','close')
    assert not backend.started
