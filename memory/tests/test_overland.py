import importlib.util
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location('walter_memory.overland', str(Path(__file__).parent / 'overland.py') if (Path(__file__).parent / 'overland.py').exists() else str(Path(__file__).parents[1] / 'walter_memory' / 'overland.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def point(dt=None, **props):
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [2.0, 48.0]},
            'properties': {'timestamp': (dt or datetime.now(timezone.utc)).isoformat(),
                           'horizontal_accuracy': 15, **props}}


def test_private_and_idempotent():
    p = point()
    a = m.normalize({'locations': [p]})[0]
    p['properties']['locations_in_payload'] = 7
    b = m.normalize({'locations': [p]})[0]
    assert a['source_id'] == b['source_id']
    assert a['privacy_class'] == 'local_only'
    assert a['payload']['lat'] == 48.0


def test_current_wins_over_backlog():
    now = datetime.now(timezone.utc)
    batch = m.normalize({'locations': [point(now-timedelta(days=1), motion=['stationary'])],
                         'current': point(now, motion=['walking'])})
    assert m.settings_for(batch)['send_interval'] == '30s'
    batch = m.normalize({'locations': [point(now-timedelta(days=1), motion=['walking'])]})
    assert m.settings_for(batch) == {}


def test_low_battery():
    batch = m.normalize({'locations': [point(motion=['walking'], battery_level=0.1)]})
    assert m.settings_for(batch)['send_interval'] == '5m'


def test_api(monkeypatch):
    monkeypatch.setattr(m, 'TOKEN', 'test-only-token')
    save = Mock(return_value={'inserted': 1, 'duplicates': 0})
    monkeypatch.setattr(m, 'store', save)
    client = TestClient(m.app)
    headers = {'Authorization': 'Bearer test-only-token'}
    assert client.post('/overland', json={'locations': [point()]}).status_code == 401
    assert not save.called
    p = point()
    p['geometry']['coordinates'][1] = 400
    assert client.post('/overland', json={'locations': [point(), p]}, headers=headers).status_code == 422
    assert not save.called  # no partial acceptance of a bad batch
    response = client.post('/overland', json={'locations': [point()]}, headers=headers)
    assert response.json()['result'] == 'ok'
    save.side_effect = RuntimeError('private backend details')
    response = client.post('/overland', json={'locations': [point()]}, headers=headers)
    assert response.status_code == 503
    assert 'result' not in response.json()
    assert 'private' not in response.text
    assert client.get('/v1/events', headers=headers).status_code == 404
    assert client.get('/docs').status_code == 404


def test_oversize_and_bad_json(monkeypatch):
    monkeypatch.setattr(m, 'TOKEN', 'test-only-token')
    client = TestClient(m.app)
    headers = {'Authorization': 'Bearer test-only-token'}
    assert client.post('/overland', content=b'0'*(m.MAX_BYTES+1), headers=headers).status_code == 413
    assert client.post('/overland', content=b'{"locations":[NaN]}', headers=headers).status_code == 422
