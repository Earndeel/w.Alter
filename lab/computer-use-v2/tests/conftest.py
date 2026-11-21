from __future__ import annotations

import pytest

from adaptive_operator.device_context import (
    AccessibilityState,
    ConnectionCapability,
    DeviceActivity,
    DeviceContext,
    DeviceHealth,
    DeviceProfile,
    DisplayProfile,
    InputCapabilities,
    Platform,
)


@pytest.fixture
def base_context() -> DeviceContext:
    return DeviceContext(
        profile=DeviceProfile(
            device_id="mac-main",
            platform=Platform.MACOS,
            hostname="discovered-host",
            connections=(ConnectionCapability("tailscale", "config:devices.mac-main"),),
            displays=(DisplayProfile("main", 3024, 1964, 2.0),),
            installed_apps=("Browser",),
            accessibility=AccessibilityState(True, "ax"),
            input=InputCapabilities(True, True, True, True, True),
        ),
        activity=DeviceActivity(
            observed_at=100.0,
            screen_locked=False,
            foreground_app="Editor",
            idle_seconds=5.0,
            recent_keyboard=True,
            recent_pointer=False,
        ),
        health=DeviceHealth(observed_at=100.0, cua_driver="healthy", latency_ms=40.0),
        updated_at=100.0,
        sources=("config",),
    )
