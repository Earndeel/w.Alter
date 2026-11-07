import base64
import json
import multiprocessing
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from walter_computer.device_lock import DeviceCallLock
from walter_computer.lease import WorkflowLease
from walter_computer.operator import OperatorSessions
from walter_computer.runtime import FastVisionRequest, UserPresence, ActionEffects, ActionOrigin, InterruptionPolicy
from walter_computer.vision import GatewayVisionSensor, VisionPermission, VisionRefused, VisionUnavailable, vision_permission
from test_modularity import operator


def _reserve(path, pipe):
    pool = OperatorSessions(lambda: (_ for _ in ()).throw(AssertionError('no backend')), lock_path=path)
    result = pool.call('owner', 'lease_acquire', {'ttl_seconds': 30}, grants={'read', 'input'})
    pipe.send(result)
    pipe.recv()
    pool.close()
    pipe.send('released')


def test_task_reservation_survives_atomic_unlock_across_processes(tmp_path):
    context = multiprocessing.get_context('spawn')
    receive, send = context.Pipe()
    path = tmp_path / 'device.lock'
    process = context.Process(target=_reserve, args=(str(path), send))
    process.start()
    try:
        assert receive.poll(5) and receive.recv()['ok']
        pool = OperatorSessions(lambda: (_ for _ in ()).throw(AssertionError('must not start')), lock_path=path)
        # Atomic flock is free, but the multi-call task reservation is still active.
        with pool.device_lock.hold() as acquired:
            assert acquired
        assert pool.call('other', 'list_apps')['code'] == 'device_reserved'
        assert pool.call('other', 'lease_release')['code'] == 'device_reserved'
        assert pool.call('other', 'lease_status')['owned'] is False
        receive.send('close')
        assert receive.poll(5) and receive.recv() == 'released'
        assert pool.call('other', 'lease_status')['reserved'] is False
    finally:
        process.join(5)
        if process.is_alive():
            process.terminate(); process.join()
        assert process.exitcode == 0


def test_reservation_expiry_and_renewal_no_takeover(tmp_path):
    now = [10.0]
    owner = WorkflowLease(tmp_path / 'lock', now=lambda: now[0])
    other = WorkflowLease(tmp_path / 'lock', now=lambda: now[0])
    with DeviceCallLock(tmp_path / 'lock').hold():
        assert owner.handle('A', 'lease_acquire', {'ttl_seconds': 2})['ok']
        assert not other.allowed('A')  # same string in another process is not ownership
        assert owner.handle('A', 'lease_renew', {'ttl_seconds': 3})['ok']
        now[0] = 14
        assert other.allowed('B')
        assert owner.handle('A', 'lease_renew', {})['code'] == 'lease_expired'
        assert other.handle('B', 'lease_acquire', {})['ok']
        assert not owner.allowed('A')


def test_reservation_permission_and_symlink_fail_before_backend(tmp_path):
    pool = OperatorSessions(lambda: (_ for _ in ()).throw(AssertionError()), lock_path=tmp_path / 'lock')
    assert pool.call('A', 'lease_acquire')['code'] == 'authorization_required'
    target = tmp_path / 'untrusted'; target.write_text('{}')
    pool.lease.path.symlink_to(target)
    with pytest.raises(OSError):
        pool.call('A', 'list_apps')


def test_origin_is_per_call_and_unknown_autonomous_presence_denied():
    backend = operator()
    pool = OperatorSessions(lambda: backend)
    pool.call('A', 'list_apps', origin='autonomous')
    assert backend._walter_origin == ActionOrigin.AUTONOMOUS
    pool.call('A', 'list_apps')
    assert backend._walter_origin == ActionOrigin.FOREGROUND_USER
    decision = InterruptionPolicy().evaluate(ActionEffects(keyboard=True),
        presence=UserPresence.unknown(observed_at=time.time()), origin=ActionOrigin.AUTONOMOUS)
    assert not decision.allowed and decision.reason == 'presence_unknown'
    pool.close()


def _sensor(response=None):
    sent = []
    def request(payload):
        sent.append(payload)
        return {'choices': [{'message': {'content': json.dumps(response or {'bounds': [1, 2, 8, 9], 'confidence': .99})}}]}
    sensor = GatewayVisionSensor({'poste': 'vision', 'token_file': '/not/read/in/tests'}, request=request)
    image = SimpleNamespace(png_b64=base64.b64encode(b'\x89PNG\r\n\x1a\nsynthetic').decode(), capture_valid=True)
    req = FastVisionRequest('Synthetic button', 'private-snapshot', 12, 34, (0, 0, 100, 100), (100, 100))
    return sensor, req, image, sent


@pytest.mark.parametrize('permission', [None, VisionPermission(12, 34),
    VisionPermission(12, 34, 'redacted_cloud', True), VisionPermission(12, 34, 'local_only', True),
    VisionPermission(999, 34, 'cloud_allowed', True)])
def test_vision_private_or_mismatched_target_never_calls_gateway(permission):
    sensor, request, image, sent = _sensor()
    with vision_permission(permission), pytest.raises(VisionRefused):
        sensor(request, image)
    assert not sent


def test_vision_routes_poste_and_minimizes_payload_and_permission_lifetime():
    sensor, request, image, sent = _sensor()
    with vision_permission(VisionPermission(12, 34, 'cloud_allowed', True)):
        assert sensor(request, image)['confidence'] == .99
    assert sent[0]['model'] == 'vision'
    text = json.dumps(sent)
    assert 'private-snapshot' not in text and '"pid"' not in text and '"window_id"' not in text
    with pytest.raises(VisionRefused):
        sensor(request, image)


@pytest.mark.parametrize('bounds,confidence', [([-1, 0, 2, 3], .99), ([0, 0, 101, 3], .99),
    ([0, 0, 2, 3], float('nan')), ([0, 0, float('inf'), 3], .99), ([True, 0, 2, 3], .99)])
def test_vision_rejects_invalid_geometry(bounds, confidence):
    sensor, request, image, _ = _sensor({'bounds': bounds, 'confidence': confidence})
    with vision_permission(VisionPermission(12, 34, 'cloud_allowed', True)), pytest.raises(VisionUnavailable):
        sensor(request, image)


def test_gateway_credentials_and_redirects_are_not_exposed(tmp_path):
    token = tmp_path / 'gateway.env'; token.write_text('WALTER_LLM_TOKEN=synthetic-test-token\n'); token.chmod(0o600)
    sensor = GatewayVisionSensor({'poste': 'vision', 'token_file': str(token)})
    assert sensor._token() == 'synthetic-test-token'
    token.chmod(0o644)
    with pytest.raises(VisionUnavailable):
        sensor._token()
    from walter_computer.vision import _NoRedirect
    with pytest.raises(VisionUnavailable):
        _NoRedirect().redirect_request(None, None, None, None, None, None)


def test_hermes_honors_other_client_reservation_before_backend(tmp_path):
    from walter_computer.ports import hermes
    from test_hermes_port import _registered_override
    from tools.bot_desktop import lease
    owner = OperatorSessions(lambda: None, lock_path=tmp_path / 'device.lock')
    assert owner.call('codex', 'lease_acquire', {}, grants={'read', 'input'})['ok']
    tool = _registered_override()
    with patch.object(lease, 'assert_agent_may_act', return_value=SimpleNamespace(epoch=1)), \
         patch.object(hermes._NATIVE_SESSIONS, 'backend', side_effect=AssertionError('must not start')):
        response = json.loads(tool['handler']({'action': 'capture'}, session_id='hermes'))
    assert response['code'] == 'device_reserved'
    owner.close()
