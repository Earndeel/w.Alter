import pytest
from walter_computer import device_lock

@pytest.fixture(autouse=True)
def isolated_device_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(device_lock, 'configured_lock_path', lambda: tmp_path/'device.lock')
