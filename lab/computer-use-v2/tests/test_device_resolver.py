from __future__ import annotations

from dataclasses import replace

import pytest

from adaptive_operator.device_context import (
    DeviceContext,
    DeviceContextResolver,
    DeviceContextStore,
)


class Source:
    def __init__(self, name: str, context: DeviceContext) -> None:
        self.name = name
        self.context = context
        self.calls = 0

    def discover(self, device_id: str) -> DeviceContext:
        self.calls += 1
        assert device_id == self.context.profile.device_id
        return replace(self.context, sources=(self.name,))


def test_resolver_uses_fresh_persistent_context_without_rediscovering(base_context, tmp_path):
    store = DeviceContextStore(tmp_path / "devices.json")
    store.upsert(base_context)
    source = Source("tailscale_discovery", base_context)
    resolver = DeviceContextResolver(store, (source,), profile_ttl_seconds=300)

    resolved = resolver.resolve(base_context.profile.device_id, now=base_context.updated_at + 10)

    assert resolved == base_context
    assert source.calls == 0


def test_resolver_refreshes_stale_context_from_config_and_discovery_sources(base_context, tmp_path):
    store = DeviceContextStore(tmp_path / "devices.json")
    store.upsert(base_context)
    changed = replace(
        base_context,
        profile=replace(base_context.profile, installed_apps=("Browser", "Editor")),
        updated_at=base_context.updated_at + 500,
    )
    source = Source("device_discovery", changed)
    resolver = DeviceContextResolver(store, (source,), profile_ttl_seconds=300)

    resolved = resolver.resolve(base_context.profile.device_id, now=base_context.updated_at + 500)

    assert source.calls == 1
    assert resolved.profile.installed_apps == ("Browser", "Editor")
    assert "device_discovery" in resolved.sources


def test_partial_discovery_refresh_preserves_stable_profile_fields(base_context, tmp_path):
    store = DeviceContextStore(tmp_path / "devices.json")
    store.upsert(base_context)
    partial_activity = DeviceContext(
        profile=replace(
            base_context.profile,
            hostname=None,
            connections=(),
            displays=(),
            installed_apps=(),
            accessibility=type(base_context.profile.accessibility)(False),
            input=type(base_context.profile.input)(False, False, False, False, False),
        ),
        activity=replace(
            base_context.activity,
            observed_at=base_context.updated_at + 20,
            idle_seconds=1.0,
        ),
        health=None,
        updated_at=base_context.updated_at + 20,
        sources=("activity-probe",),
    )

    merged = store.update_runtime_state(
        base_context.profile.device_id,
        activity=partial_activity.activity,
        health=None,
        source="activity-probe",
    )

    assert merged.profile.hostname == base_context.profile.hostname
    assert merged.profile.connections == base_context.profile.connections
    assert merged.profile.displays == base_context.profile.displays
    assert merged.profile.accessibility == base_context.profile.accessibility
    assert merged.profile.input == base_context.profile.input
    assert merged.activity.observed_at == base_context.updated_at + 20
    assert merged.updated_at == base_context.updated_at
    assert merged.sources == ("config", "activity-probe")


def test_stale_profile_cannot_overwrite_newer_device_identity(base_context, tmp_path):
    store = DeviceContextStore(tmp_path / "devices.json")
    store.upsert(base_context)
    stale = replace(
        base_context,
        profile=replace(base_context.profile, hostname="stale-host", connections=()),
        updated_at=base_context.updated_at - 10,
        sources=("stale-discovery",),
    )
    merged = store.upsert(stale)
    assert merged.profile.hostname == base_context.profile.hostname
    assert merged.profile.connections == base_context.profile.connections
    assert merged.updated_at == base_context.updated_at


def test_device_id_cannot_change_platform_during_merge(base_context, tmp_path):
    from adaptive_operator.device_context import Platform

    store = DeviceContextStore(tmp_path / "devices.json")
    store.upsert(base_context)
    changed_platform = replace(
        base_context,
        profile=replace(base_context.profile, platform=Platform.WINDOWS),
        updated_at=base_context.updated_at + 1,
    )
    with pytest.raises(ValueError, match="platform"):
        store.upsert(changed_platform)


def test_explicit_refresh_bypasses_ttl_without_hardcoding_transport(base_context, tmp_path):
    store = DeviceContextStore(tmp_path / "devices.json")
    store.upsert(base_context)
    source = Source("configured_source", base_context)
    resolver = DeviceContextResolver(store, (source,), profile_ttl_seconds=9999)

    resolver.resolve(base_context.profile.device_id, now=base_context.updated_at + 1, refresh=True)

    assert source.calls == 1
