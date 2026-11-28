from __future__ import annotations

from adaptive_operator.device_context import (
    AccessibilityState,
    ConnectionCapability,
    DeviceActivity,
    DeviceContext,
    DeviceContextStore,
    DeviceHealth,
    DeviceProfile,
    DisplayProfile,
    InputCapabilities,
    Platform,
)


def _context(*, device_id: str, activity_at: float, apps: tuple[str, ...]) -> DeviceContext:
    return DeviceContext(
        profile=DeviceProfile(
            device_id=device_id,
            platform=Platform.MACOS,
            hostname="host-from-discovery",
            connections=(
                ConnectionCapability(kind="tailscale", identity_ref="config:devices.main.connection"),
            ),
            displays=(DisplayProfile(display_id="main", width_px=3024, height_px=1964, scale=2.0),),
            installed_apps=apps,
            accessibility=AccessibilityState(available=True, provider="ax"),
            input=InputCapabilities(
                background=True,
                foreground=True,
                focus_control=True,
                pointer=True,
                keyboard=True,
            ),
        ),
        activity=DeviceActivity(
            observed_at=activity_at,
            screen_locked=False,
            foreground_app="Editor",
            idle_seconds=2.5,
            recent_keyboard=True,
            recent_pointer=False,
        ),
        health=DeviceHealth(observed_at=activity_at, cua_driver="healthy", latency_ms=42.0),
        updated_at=activity_at,
        sources=("config", "device_discovery"),
    )


def test_store_round_trips_named_device_without_hardcoded_environment(tmp_path):
    store = DeviceContextStore(tmp_path / "devices.json")
    expected = _context(device_id="configured-device", activity_at=20.0, apps=("Browser",))

    store.upsert(expected)

    assert store.get("configured-device") == expected
    assert store.list_ids() == ("configured-device",)
    assert "host-from-discovery" in (tmp_path / "devices.json").read_text(encoding="utf-8")


def test_upsert_merges_discovery_but_never_replaces_new_activity_with_stale_state(tmp_path):
    store = DeviceContextStore(tmp_path / "devices.json")
    current = _context(device_id="mac-main", activity_at=20.0, apps=("Browser",))
    stale_update = _context(device_id="mac-main", activity_at=10.0, apps=("Browser", "Editor"))
    store.upsert(current)

    merged = store.upsert(stale_update)

    assert merged.profile.installed_apps == ("Browser", "Editor")
    assert merged.activity == current.activity
    assert merged.health == current.health
    assert merged.updated_at == 20.0
    assert set(merged.sources) == {"config", "device_discovery"}


def test_context_contract_is_platform_neutral_but_lot20_only_declares_macos_live():
    assert {item.value for item in Platform} == {"macos", "windows", "android"}
    assert Platform.MACOS.live_in_lot20 is True
    assert Platform.WINDOWS.live_in_lot20 is False
    assert Platform.ANDROID.live_in_lot20 is False
