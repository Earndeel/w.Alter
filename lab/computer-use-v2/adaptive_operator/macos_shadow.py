"""Read-only macOS DeviceContext and User Presence sources for shadow mode."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping

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


class LocalMacContextSource:
    """Resolve stable Mac routing facts from local runtime state only."""

    name = "local_macos_runtime"

    def __init__(
        self,
        *,
        remote_config_path: str | Path,
        tailscale_status_reader: Callable[[], Mapping[str, Any]],
        now: Callable[[], float],
    ) -> None:
        self.remote_config_path = Path(remote_config_path)
        self.tailscale_status_reader = tailscale_status_reader
        self.now = now

    def discover(self, device_id: str) -> DeviceContext:
        config = json.loads(self.remote_config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("remote CUA config must be a JSON object")
        host = str(config.get("host") or "").strip()
        if not host:
            raise ValueError("remote CUA host is missing")
        peer = _matching_macos_peer(self.tailscale_status_reader(), host)
        identity = str(peer.get("ID") or peer.get("PublicKey") or host)
        metadata = tuple(
            (key, str(value))
            for key, value in (
                ("dns_name", peer.get("DNSName")),
                ("route", (peer.get("TailscaleIPs") or [None])[0]),
            )
            if value
        )
        observed = float(self.now())
        return DeviceContext(
            profile=DeviceProfile(
                device_id=device_id,
                platform=Platform.MACOS,
                os_name="macOS",
                hostname=host,
                connections=(
                    ConnectionCapability(
                        kind="tailscale",
                        identity_ref=f"runtime:tailscale:{identity}",
                        available=bool(peer.get("Online")),
                        metadata=metadata,
                    ),
                ),
                accessibility=AccessibilityState(None),
                input=InputCapabilities(False, False, False, False, False),
            ),
            activity=None,
            health=None,
            updated_at=observed,
            sources=("runtime_config", "tailscale_local"),
            source_device_calls=0,
        )

    @staticmethod
    def synthetic_for_test(*, device_id: str, now: float) -> DeviceContext:
        return DeviceContext(
            profile=DeviceProfile(
                device_id=device_id,
                platform=Platform.MACOS,
                os_name="macOS",
            ),
            activity=None,
            health=None,
            updated_at=now,
            sources=("test",),
            source_device_calls=0,
        )


@dataclass(frozen=True)
class PresenceProbeResult:
    activity: DeviceActivity
    os_version: str | None = None
    display_width_px: int | None = None
    display_height_px: int | None = None
    driver_status: str | None = None
    additional_device_calls: int = 0
    mutations: int = 0
    screenshots: int = 0
    focus_changes: int = 0
    cache_hit: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any],
        *,
        observed_at: float,
        additional_device_calls: int,
        cache_hit: bool = False,
    ) -> PresenceProbeResult:
        idle_ns = _optional_float(raw.get("idle_ns"))
        idle_seconds = None if idle_ns is None else max(idle_ns, 0.0) / 1_000_000_000
        display_width, display_height = _display_size(raw.get("display_px"))
        return cls(
            activity=DeviceActivity(
                observed_at=observed_at,
                screen_locked=_optional_bool(raw.get("screen_locked")),
                foreground_app=_optional_text(raw.get("foreground_app")),
                idle_seconds=idle_seconds,
                recent_input=(idle_seconds < 15.0 if idle_seconds is not None else None),
                recent_keyboard=None,
                recent_pointer=None,
            ),
            os_version=_optional_text(raw.get("os_version")),
            display_width_px=display_width,
            display_height_px=display_height,
            driver_status=_optional_text(raw.get("driver_status")),
            additional_device_calls=additional_device_calls,
            cache_hit=cache_hit,
        )


class MacPresenceProbe:
    """One fixed, read-only remote batch; never accepts model-controlled text."""

    READ_ONLY_BATCH = "macos_presence_v1"

    def __init__(
        self,
        *,
        run_fixed_batch: Callable[[str], Mapping[str, Any]],
        now: Callable[[], float],
    ) -> None:
        self.run_fixed_batch = run_fixed_batch
        self.now = now

    def probe(self) -> PresenceProbeResult:
        raw = self.run_fixed_batch(self.READ_ONLY_BATCH)
        return PresenceProbeResult.from_mapping(
            raw,
            observed_at=float(self.now()),
            additional_device_calls=1,
        )

    @staticmethod
    def cached(
        *,
        store: DeviceContextStore,
        device_id: str,
        probe: Callable[[], PresenceProbeResult],
        ttl_seconds: float,
    ) -> CachedMacPresence:
        return CachedMacPresence(
            store=store,
            device_id=device_id,
            probe=probe,
            ttl_seconds=ttl_seconds,
        )


class FixedSshMacProbeRunner:
    """Run one constant read-only command over the configured SSH route."""

    BATCH_NAME = MacPresenceProbe.READ_ONLY_BATCH
    REMOTE_COMMAND = (
        "os_version=$(/usr/bin/sw_vers -productVersion 2>/dev/null); "
        "idle_ns=$(/usr/sbin/ioreg -c IOHIDSystem -d 1 2>/dev/null | "
        "/usr/bin/sed -n 's/.*\"HIDIdleTime\" = \\([0-9][0-9]*\\).*/\\1/p' | "
        "/usr/bin/head -n 1); "
        "foreground_app=$(/usr/bin/lsappinfo front 2>/dev/null | "
        "/usr/bin/sed -n 's/.*\"name\"=\"\\([^\"]*\\)\".*/\\1/p'); "
        "display_px=$(/usr/sbin/system_profiler SPDisplaysDataType 2>/dev/null | "
        "/usr/bin/sed -n 's/^[[:space:]]*Resolution: \\([0-9][0-9]*\\) x \\([0-9][0-9]*\\).*/\\1x\\2/p' | "
        "/usr/bin/head -n 1); "
        "if $HOME/.local/bin/cua-driver status >/dev/null 2>&1; then "
        "driver_status=healthy; else driver_status=unavailable; fi; "
        "/usr/bin/printf 'os_version=%s\\nidle_ns=%s\\nscreen_locked=unknown\\nforeground_app=%s\\ndisplay_px=%s\\ndriver_status=%s\\n' "
        '"$os_version" "$idle_ns" "$foreground_app" "$display_px" "$driver_status"'
    )

    def __init__(
        self,
        *,
        config_path: str | Path,
        execute: Callable[[list[str], int], str] | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.execute = execute or self._execute

    def __call__(self, batch_name: str) -> dict[str, str]:
        if batch_name != self.BATCH_NAME:
            raise ValueError("unknown read-only Mac probe batch")
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("remote CUA config must be a JSON object")
        connect_timeout = int(config.get("connect_timeout_seconds", 8))
        ssh_path = str(config.get("ssh_path") or "/usr/bin/ssh")
        identity = str(Path(str(config["identity_file"])).expanduser())
        known_hosts = str(Path(str(config["known_hosts_file"])).expanduser())
        destination = f"{config['username']}@{config['host']}"
        argv = [
            ssh_path,
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", f"ConnectTimeout={connect_timeout}",
            "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={known_hosts}",
            "-i", identity,
            destination,
            self.REMOTE_COMMAND,
        ]
        output = self.execute(argv, connect_timeout + 4)
        values: dict[str, str] = {}
        allowed = {
            "os_version",
            "idle_ns",
            "screen_locked",
            "foreground_app",
            "display_px",
            "driver_status",
        }
        for line in output.splitlines():
            key, separator, value = line.partition("=")
            if separator and key in allowed:
                values[key] = value.strip()
        return values

    @staticmethod
    def _execute(argv: list[str], timeout: int) -> str:
        completed = subprocess.run(
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return completed.stdout


class CachedMacPresence:
    def __init__(
        self,
        *,
        store: DeviceContextStore,
        device_id: str,
        probe: Callable[[], PresenceProbeResult],
        ttl_seconds: float,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("presence TTL must be positive")
        self.store = store
        self.device_id = device_id
        self.probe = probe
        self.ttl_seconds = ttl_seconds

    def resolve(self, *, now: float) -> PresenceProbeResult:
        current = self.store.get(self.device_id)
        if current is None:
            raise LookupError(f"unknown device {self.device_id!r}")
        if (
            current.activity is not None
            and now - current.activity.observed_at <= self.ttl_seconds
        ):
            return PresenceProbeResult(
                activity=current.activity,
                os_version=current.profile.os_version,
                display_width_px=(
                    current.profile.displays[0].width_px
                    if current.profile.displays else None
                ),
                display_height_px=(
                    current.profile.displays[0].height_px
                    if current.profile.displays else None
                ),
                driver_status=(current.health.cua_driver if current.health else None),
                additional_device_calls=0,
                cache_hit=True,
            )
        result = self.probe()
        displays = current.profile.displays
        if result.display_width_px and result.display_height_px:
            displays = (
                DisplayProfile(
                    display_id="main",
                    width_px=result.display_width_px,
                    height_px=result.display_height_px,
                    scale=None,
                ),
            )
        if (
            (result.os_version and current.profile.os_version != result.os_version)
            or displays != current.profile.displays
        ):
            current = self.store.upsert(
                replace(
                    current,
                    profile=replace(
                        current.profile,
                        os_version=result.os_version or current.profile.os_version,
                        displays=displays,
                    ),
                )
            )
        health = current.health
        if result.driver_status:
            health = DeviceHealth(
                observed_at=result.activity.observed_at,
                cua_driver=result.driver_status,
            )
        self.store.update_runtime_state(
            self.device_id,
            activity=result.activity,
            health=health,
            source="macos_presence_read_only",
        )
        return result


def _matching_macos_peer(status: Mapping[str, Any], host: str) -> Mapping[str, Any]:
    peers = status.get("Peer")
    if not isinstance(peers, dict):
        raise LookupError("Tailscale peer inventory is unavailable")
    candidates = [item for item in peers.values() if isinstance(item, dict)]
    for peer in candidates:
        dns = str(peer.get("DNSName") or "").rstrip(".")
        peer_hosts = {
            str(peer.get("HostName") or ""),
            dns,
            dns.split(".")[0],
            *(str(value) for value in (peer.get("TailscaleIPs") or ())),
        }
        if (
            str(peer.get("OS") or "").casefold() in {"macos", "darwin"}
            and host in peer_hosts
        ):
            return peer
    raise LookupError(f"no macOS Tailscale peer matches configured host {host!r}")


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold() if value is not None else ""
    if text in {"true", "1", "yes", "locked"}:
        return True
    if text in {"false", "0", "no", "unlocked"}:
        return False
    return None


def _display_size(value: Any) -> tuple[int | None, int | None]:
    text = str(value).strip().lower() if value is not None else ""
    left, separator, right = text.partition("x")
    if not separator:
        return None, None
    try:
        width, height = int(left), int(right)
    except ValueError:
        return None, None
    if width <= 0 or height <= 0:
        return None, None
    return width, height