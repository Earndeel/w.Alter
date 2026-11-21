from __future__ import annotations

import json

from adaptive_operator.device_context import DeviceContextStore
from adaptive_operator.macos_shadow import (
    FixedSshMacProbeRunner,
    LocalMacContextSource,
    MacPresenceProbe,
    PresenceProbeResult,
)


def test_local_context_uses_runtime_config_and_tailscale_without_device_call(tmp_path):
    remote = tmp_path / "remote-cua.json"
    remote.write_text(
        json.dumps(
            {
                "host": "mac-tailnet-name",
                "username": "configured-user",
                "identity_file": "/secret/key/path",
                "known_hosts_file": "/secret/known-hosts",
                "remote_driver_path": "/Applications/CuaDriver/cua-driver",
                "ssh_path": "/usr/bin/ssh",
            }
        ),
        encoding="utf-8",
    )
    tailscale = {
        "Peer": {
            "node-key": {
                "HostName": "mac-tailnet-name",
                "DNSName": "mac-tailnet-name.example.ts.net.",
                "OS": "macOS",
                "Online": True,
                "TailscaleIPs": ["100.64.0.9"],
                "ID": "peer-stable-id",
            }
        }
    }

    discovered = LocalMacContextSource(
        remote_config_path=remote,
        tailscale_status_reader=lambda: tailscale,
        now=lambda: 100.0,
    ).discover("configured-mac")

    assert discovered.profile.device_id == "configured-mac"
    assert discovered.profile.platform.value == "macos"
    assert discovered.profile.hostname == "mac-tailnet-name"
    assert discovered.profile.os_name == "macOS"
    assert discovered.profile.connections[0].kind == "tailscale"
    assert discovered.profile.connections[0].available is True
    assert discovered.profile.connections[0].identity_ref == "runtime:tailscale:peer-stable-id"
    assert discovered.profile.accessibility.available is None
    assert "/secret/key/path" not in json.dumps(discovered.profile.connections[0].metadata)
    assert discovered.sources == ("runtime_config", "tailscale_local")
    assert discovered.source_device_calls == 0


def test_local_context_source_matches_configured_tailscale_ip(tmp_path):
    config = tmp_path / "remote.json"
    config.write_text(json.dumps({"host": "192.0.2.10"}), encoding="utf-8")
    status = {
        "Peer": {
            "peer-key": {
                "ID": "peer-id",
                "OS": "macOS",
                "HostName": "studio-mac",
                "DNSName": "studio-mac.example.ts.net.",
                "TailscaleIPs": ["192.0.2.10"],
                "Online": True,
            }
        }
    }

    context = LocalMacContextSource(
        remote_config_path=config,
        tailscale_status_reader=lambda: status,
        now=lambda: 50.0,
    ).discover("configured-mac")

    assert context.profile.hostname == "192.0.2.10"
    assert context.profile.connections[0].available is True
    assert context.source_device_calls == 0


def test_presence_probe_uses_one_fixed_read_only_batch_and_preserves_unknowns():
    seen = []

    def run(command):
        seen.append(command)
        return {
            "os_version": "15.6",
            "idle_ns": "4200000000",
            "screen_locked": "unknown",
            "foreground_app": "Finder",
            "display_px": "2880x1800",
            "driver_status": "healthy",
        }

    result = MacPresenceProbe(run_fixed_batch=run, now=lambda: 200.0).probe()

    assert len(seen) == 1
    assert seen[0] == MacPresenceProbe.READ_ONLY_BATCH
    assert result.activity.observed_at == 200.0
    assert result.activity.idle_seconds == 4.2
    assert result.activity.screen_locked is None
    assert result.activity.foreground_app == "Finder"
    assert result.activity.recent_keyboard is None
    assert result.activity.recent_pointer is None
    assert result.activity.recent_input is True
    assert result.display_width_px == 2880
    assert result.display_height_px == 1800
    assert result.driver_status == "healthy"
    assert result.additional_device_calls == 1
    assert result.mutations == 0
    assert result.screenshots == 0
    assert result.focus_changes == 0


def test_presence_cache_prevents_rediscovery_until_ttl(tmp_path):
    calls = 0

    def probe():
        nonlocal calls
        calls += 1
        return PresenceProbeResult.from_mapping(
            {"idle_ns": "1000000000", "screen_locked": "false", "foreground_app": "Finder"},
            observed_at=100.0 + calls,
            additional_device_calls=1,
        )

    store = DeviceContextStore(tmp_path / "device-context.json")
    source = LocalMacContextSource.synthetic_for_test(device_id="mac", now=100.0)
    store.upsert(source)
    resolver = MacPresenceProbe.cached(store=store, device_id="mac", probe=probe, ttl_seconds=15.0)

    first = resolver.resolve(now=110.0)
    second = resolver.resolve(now=112.0)

    assert calls == 1
    assert first.additional_device_calls == 1
    assert second.additional_device_calls == 0
    assert second.cache_hit is True


def test_fixed_ssh_runner_uses_only_config_and_constant_remote_command(tmp_path):
    config = tmp_path / "remote-cua.json"
    config.write_text(
        json.dumps(
            {
                "host": "mac.example.ts.net",
                "username": "mac-user",
                "identity_file": str(tmp_path / "id"),
                "known_hosts_file": str(tmp_path / "known-hosts"),
                "ssh_path": "/usr/bin/ssh",
                "connect_timeout_seconds": 8,
            }
        ),
        encoding="utf-8",
    )
    seen = []

    def execute(argv, timeout):
        seen.append((argv, timeout))
        return (
            "os_version=15.6\nidle_ns=2500000000\nscreen_locked=unknown\n"
            "foreground_app=Finder\ndisplay_px=2880x1800\ndriver_status=healthy\n"
        )

    result = FixedSshMacProbeRunner(config_path=config, execute=execute)(
        FixedSshMacProbeRunner.BATCH_NAME
    )

    argv, timeout = seen[0]
    assert argv[0] == "/usr/bin/ssh"
    assert argv[-1] == FixedSshMacProbeRunner.REMOTE_COMMAND
    assert "mac-user@mac.example.ts.net" in argv
    assert timeout == 12
    assert result == {
        "os_version": "15.6",
        "idle_ns": "2500000000",
        "screen_locked": "unknown",
        "foreground_app": "Finder",
        "display_px": "2880x1800",
        "driver_status": "healthy",
    }
