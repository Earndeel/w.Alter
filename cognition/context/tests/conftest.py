"""Tests never depend on the live [state] switches of config/walter-context.toml (turned on 2026-11-17): the
preflight is tested with them off unless a test switches them itself (monkeypatch of preflight.state_settings)."""
import pytest


@pytest.fixture(autouse=True)
def _state_switches_off(monkeypatch):
    from walter_context import preflight
    from walter_context.config import STATE_DEFAULTS
    monkeypatch.setattr(preflight, "state_settings", lambda path=None: dict(STATE_DEFAULTS))
