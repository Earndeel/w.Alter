"""Persistent, platform-neutral device context contracts for Computer Use V2."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol


class Platform(StrEnum):
    MACOS = "macos"
    WINDOWS = "windows"
    ANDROID = "android"

    @property
    def live_in_lot20(self) -> bool:
        return self is Platform.MACOS


@dataclass(frozen=True)
class ConnectionCapability:
    kind: str
    identity_ref: str
    available: bool = True
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class DisplayProfile:
    display_id: str
    width_px: int
    height_px: int
    scale: float | None


@dataclass(frozen=True)
class AccessibilityState:
    available: bool | None
    provider: str | None = None


@dataclass(frozen=True)
class InputCapabilities:
    background: bool
    foreground: bool
    focus_control: bool
    pointer: bool
    keyboard: bool


@dataclass(frozen=True)
class DeviceProfile:
    device_id: str
    platform: Platform
    os_name: str | None = None
    os_version: str | None = None
    hostname: str | None = None
    connections: tuple[ConnectionCapability, ...] = ()
    displays: tuple[DisplayProfile, ...] = ()
    installed_apps: tuple[str, ...] = ()
    accessibility: AccessibilityState = AccessibilityState(None)
    input: InputCapabilities = InputCapabilities(False, False, False, False, False)


@dataclass(frozen=True)
class DeviceActivity:
    observed_at: float
    screen_locked: bool | None = None
    foreground_app: str | None = None
    idle_seconds: float | None = None
    recent_input: bool | None = None
    recent_keyboard: bool | None = None
    recent_pointer: bool | None = None

    @property
    def user_active(self) -> bool | None:
        if self.screen_locked is True:
            return False
        if (
            self.recent_input is True
            or self.recent_keyboard is True
            or self.recent_pointer is True
        ):
            return True
        if self.idle_seconds is None:
            return None
        return self.idle_seconds < 30.0


@dataclass(frozen=True)
class DeviceHealth:
    observed_at: float
    cua_driver: str
    latency_ms: float | None = None


@dataclass(frozen=True)
class DeviceContext:
    profile: DeviceProfile
    activity: DeviceActivity | None
    health: DeviceHealth | None
    updated_at: float
    sources: tuple[str, ...] = ()
    source_device_calls: int = 0


class DeviceContextStore:
    """Small JSON store; discovery refreshes facts without becoming per-goal work."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def list_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._load()))

    def get(self, device_id: str) -> DeviceContext | None:
        raw = self._load().get(device_id)
        return _context_from_dict(raw) if raw is not None else None

    def upsert(self, incoming: DeviceContext) -> DeviceContext:
        if not incoming.profile.device_id.strip():
            raise ValueError("device_id cannot be empty")
        records = self._load()
        previous_raw = records.get(incoming.profile.device_id)
        merged = incoming if previous_raw is None else _merge(_context_from_dict(previous_raw), incoming)
        records[incoming.profile.device_id] = _context_to_dict(merged)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(records, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return merged

    def update_runtime_state(
        self,
        device_id: str,
        *,
        activity: DeviceActivity | None,
        health: DeviceHealth | None,
        source: str,
    ) -> DeviceContext:
        """Refresh volatile state without replacing the stable device profile."""
        current = self.get(device_id)
        if current is None:
            raise LookupError(f"cannot update unknown device {device_id!r}")
        if not source.strip():
            raise ValueError("runtime state source is required")
        candidate = DeviceContext(
            profile=current.profile,
            activity=activity,
            health=health,
            updated_at=current.updated_at,
            sources=(source,),
            source_device_calls=0,
        )
        return self.upsert(candidate)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("device context store must contain a JSON object")
        return raw


class DeviceContextSource(Protocol):
    name: str

    def discover(self, device_id: str) -> DeviceContext: ...


class DeviceContextResolver:
    """Resolve from persistent state first; discovery is TTL/refresh driven."""

    def __init__(
        self,
        store: DeviceContextStore,
        sources: tuple[DeviceContextSource, ...],
        *,
        profile_ttl_seconds: float,
    ) -> None:
        if profile_ttl_seconds <= 0:
            raise ValueError("profile_ttl_seconds must be positive")
        self.store = store
        self.sources = sources
        self.profile_ttl_seconds = profile_ttl_seconds

    def resolve(self, device_id: str, *, now: float, refresh: bool = False) -> DeviceContext:
        current = self.store.get(device_id)
        fresh = (
            current is not None
            and now - current.updated_at <= self.profile_ttl_seconds
        )
        if fresh and not refresh:
            return current
        if not self.sources:
            if current is None:
                raise LookupError(f"no context or discovery source for device {device_id!r}")
            return current
        merged = current
        for source in self.sources:
            discovered = source.discover(device_id)
            merged = discovered if merged is None else _merge(merged, discovered)
        assert merged is not None
        return self.store.upsert(merged)


def _merge(current: DeviceContext, incoming: DeviceContext) -> DeviceContext:
    if current.profile.device_id != incoming.profile.device_id:
        raise ValueError("cannot merge different devices")
    if current.profile.platform is not incoming.profile.platform:
        raise ValueError("cannot change platform for an existing device_id")
    apps = tuple(dict.fromkeys((*current.profile.installed_apps, *incoming.profile.installed_apps)))
    profile_base = incoming.profile if incoming.updated_at >= current.updated_at else current.profile
    profile = replace(profile_base, installed_apps=apps)
    activity = incoming.activity
    if current.activity is not None and (
        activity is None or current.activity.observed_at > activity.observed_at
    ):
        activity = current.activity
    health = incoming.health
    if current.health is not None and (
        health is None or current.health.observed_at > health.observed_at
    ):
        health = current.health
    return DeviceContext(
        profile=profile,
        activity=activity,
        health=health,
        updated_at=max(current.updated_at, incoming.updated_at),
        sources=tuple(dict.fromkeys((*current.sources, *incoming.sources))),
        source_device_calls=current.source_device_calls + incoming.source_device_calls,
    )


def _context_to_dict(value: DeviceContext) -> dict[str, Any]:
    raw = asdict(value)
    raw["profile"]["platform"] = value.profile.platform.value
    raw["profile"]["connections"] = list(raw["profile"]["connections"])
    raw["profile"]["displays"] = list(raw["profile"]["displays"])
    raw["profile"]["installed_apps"] = list(value.profile.installed_apps)
    raw["sources"] = list(value.sources)
    return raw


def _context_from_dict(raw: dict[str, Any]) -> DeviceContext:
    profile = raw["profile"]
    return DeviceContext(
        profile=DeviceProfile(
            device_id=profile["device_id"],
            platform=Platform(profile["platform"]),
            os_name=profile.get("os_name"),
            os_version=profile.get("os_version"),
            hostname=profile.get("hostname"),
            connections=tuple(
                ConnectionCapability(
                    kind=item["kind"],
                    identity_ref=item["identity_ref"],
                    available=item.get("available", True),
                    metadata=tuple(tuple(pair) for pair in item.get("metadata", ())),
                )
                for item in profile.get("connections", ())
            ),
            displays=tuple(DisplayProfile(**item) for item in profile.get("displays", ())),
            installed_apps=tuple(profile.get("installed_apps", ())),
            accessibility=AccessibilityState(**profile.get("accessibility", {"available": None})),
            input=InputCapabilities(**profile.get("input", {
                "background": False,
                "foreground": False,
                "focus_control": False,
                "pointer": False,
                "keyboard": False,
            })),
        ),
        activity=DeviceActivity(**raw["activity"]) if raw.get("activity") else None,
        health=DeviceHealth(**raw["health"]) if raw.get("health") else None,
        updated_at=float(raw["updated_at"]),
        sources=tuple(raw.get("sources", ())),
        source_device_calls=int(raw.get("source_device_calls", 0)),
    )
