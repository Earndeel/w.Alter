"""Small production runtime contracts for Walter Operator on macOS.

This module contains no planner.  It reports device facts, classifies the
side-effects of one selected primitive, and returns control to Hermes.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold() if value is not None else ""
    if text in {"true", "1", "yes", "locked"}:
        return True
    if text in {"false", "0", "no", "unlocked"}:
        return False
    return None


def _idle_seconds(raw: Mapping[str, Any]) -> float | None:
    value = raw.get("idle_duration", raw.get("idle_seconds"))
    if value is not None:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None
    idle_ns = raw.get("idle_ns")
    if idle_ns is None:
        return None
    try:
        return max(0.0, float(idle_ns)) / 1_000_000_000
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class UserPresence:
    screen_locked: bool | None
    desktop_unlocked: bool | None
    foreground_app: str | None
    foreground_window: str | None
    idle_duration: float | None
    recent_keyboard_activity: bool | None
    recent_pointer_activity: bool | None
    user_active: bool | None
    observation_timestamp: float
    confidence: float | None
    source: str

    @classmethod
    def unknown(cls, *, observed_at: float, source: str = "unavailable") -> "UserPresence":
        return cls(
            screen_locked=None,
            desktop_unlocked=None,
            foreground_app=None,
            foreground_window=None,
            idle_duration=None,
            recent_keyboard_activity=None,
            recent_pointer_activity=None,
            user_active=None,
            observation_timestamp=float(observed_at),
            confidence=None,
            source=source,
        )

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any],
        *,
        observed_at: float,
        source: str,
        confidence: float | None,
        active_threshold_seconds: float = 30.0,
    ) -> "UserPresence":
        screen_locked = _optional_bool(raw.get("screen_locked"))
        desktop_unlocked = _optional_bool(raw.get("desktop_unlocked"))
        if desktop_unlocked is None and screen_locked is not None:
            desktop_unlocked = not screen_locked
        idle = _idle_seconds(raw)
        recent_keyboard = _optional_bool(
            raw.get("recent_keyboard_activity", raw.get("recent_keyboard"))
        )
        recent_pointer = _optional_bool(
            raw.get("recent_pointer_activity", raw.get("recent_pointer"))
        )
        explicit_active = _optional_bool(raw.get("user_active"))
        if screen_locked is True:
            user_active = False
        elif explicit_active is not None:
            user_active = explicit_active
        elif recent_keyboard is True or recent_pointer is True:
            user_active = True
        elif idle is not None:
            user_active = idle < active_threshold_seconds
        else:
            user_active = None
        normalized_confidence = None
        if confidence is not None:
            normalized_confidence = max(0.0, min(float(confidence), 1.0))
        return cls(
            screen_locked=screen_locked,
            desktop_unlocked=desktop_unlocked,
            foreground_app=_optional_text(raw.get("foreground_app")),
            foreground_window=_optional_text(raw.get("foreground_window")),
            idle_duration=idle,
            recent_keyboard_activity=recent_keyboard,
            recent_pointer_activity=recent_pointer,
            user_active=user_active,
            observation_timestamp=float(observed_at),
            confidence=normalized_confidence,
            source=str(source or "unknown"),
        )

    def compact(self) -> dict[str, Any]:
        return {
            "screen_locked": self.screen_locked,
            "desktop_unlocked": self.desktop_unlocked,
            "foreground_app": self.foreground_app,
            "foreground_window": self.foreground_window,
            "idle_duration": self.idle_duration,
            "recent_keyboard_activity": self.recent_keyboard_activity,
            "recent_pointer_activity": self.recent_pointer_activity,
            "user_active": self.user_active,
            "observation_timestamp": self.observation_timestamp,
            "confidence": self.confidence,
            "source": self.source,
        }


class UserPresenceCache:
    """TTL cache around one bounded, read-only presence source."""

    def __init__(self, *, probe: Callable[[], UserPresence], ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            raise ValueError("presence TTL must be positive")
        self.probe = probe
        self.ttl_seconds = float(ttl_seconds)
        self._cached: UserPresence | None = None

    def resolve(self, *, now: float) -> UserPresence:
        if (
            self._cached is not None
            and float(now) - self._cached.observation_timestamp <= self.ttl_seconds
        ):
            return self._cached
        try:
            current = self.probe()
        except Exception:
            current = UserPresence.unknown(observed_at=float(now))
        self._cached = current
        return current


class ActionOrigin(StrEnum):
    FOREGROUND_USER = "foreground_user"
    AUTONOMOUS = "autonomous"


@dataclass(frozen=True)
class ActionEffects:
    read_only: bool = False
    visible_ui: bool = False
    focus_change: bool = False
    pointer: bool = False
    keyboard: bool = False
    desktop_change: bool = False
    destructive: bool = False
    closes_unsaved_work: bool = False
    sensitive_permission: bool = False
    irreversible: bool = False
    restart_or_shutdown: bool = False

    @property
    def level(self) -> str:
        if any((
            self.destructive,
            self.closes_unsaved_work,
            self.sensitive_permission,
            self.irreversible,
            self.restart_or_shutdown,
        )):
            return "L2"
        if any((
            self.visible_ui,
            self.focus_change,
            self.pointer,
            self.keyboard,
            self.desktop_change,
        )):
            return "L1"
        return "L0"


@dataclass(frozen=True)
class InterruptionDecision:
    level: str
    allowed: bool
    warning_required: bool
    defer: bool
    needs_confirmation: bool
    reason: str | None
    user_active: bool | None

    def compact(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "allowed": self.allowed,
            "warning_required": self.warning_required,
            "defer": self.defer,
            "needs_confirmation": self.needs_confirmation,
            "reason": self.reason,
            "user_active": self.user_active,
        }


class InterruptionPolicy:
    """Effect-derived gate for one atomic operation; never chooses the operation."""

    def evaluate(
        self,
        effects: ActionEffects,
        *,
        presence: UserPresence | None,
        origin: ActionOrigin,
        confirmation_granted: bool = False,
    ) -> InterruptionDecision:
        level = effects.level
        active = presence.user_active if presence is not None else None
        if level == "L0":
            return InterruptionDecision("L0", True, False, False, False, None, active)
        if level == "L2":
            allowed = confirmation_granted is True
            return InterruptionDecision(
                "L2",
                allowed,
                False,
                False,
                not allowed,
                None if allowed else "l2_confirmation_required",
                active,
            )
        if presence is not None and (
            presence.screen_locked is True or presence.desktop_unlocked is False
        ):
            return InterruptionDecision(
                "L1", False, False, False, False,
                "screen_locked_visible_action_refused", active,
            )
        collision = active is True
        if origin is ActionOrigin.AUTONOMOUS and collision:
            return InterruptionDecision(
                "L1", False, True, True, False, "user_active_interference", active
            )
        if origin is ActionOrigin.AUTONOMOUS and (active is None or presence is None or presence.screen_locked is None):
            return InterruptionDecision(
                'L1', False, False, True, False, 'presence_unknown', active
            )
        return InterruptionDecision(
            "L1", True, collision, False, False,
            "user_active_interference" if collision else None,
            active,
        )


class VisualRefStale(RuntimeError):
    pass


class VisualGeometryAmbiguous(RuntimeError):
    pass


@dataclass(frozen=True)
class VisualTarget:
    ref: str
    snapshot_id: str
    generation: int
    pid: int
    window_id: int
    capture_dimensions: tuple[int, int]
    source_capture_dimensions: tuple[int, int]
    source_region: tuple[int, int, int, int]
    target_bounds: tuple[int, int, int, int]
    scale_x: float
    scale_y: float
    mapping_confidence: float
    crop_digest: str | None
    issued_at: float
    expires_at: float

    @property
    def window_coordinate(self) -> tuple[int, int]:
        region_x, region_y, _, _ = self.source_region
        x, y, width, height = self.target_bounds
        return (
            int(round(region_x + (x + width / 2) / self.scale_x)),
            int(round(region_y + (y + height / 2) / self.scale_y)),
        )


class VisualRefStore:
    """Short-lived visual handles bound to one driver capture generation."""

    def __init__(self, *, ttl_seconds: float = 3.0, min_mapping_confidence: float = 0.95) -> None:
        if ttl_seconds <= 0:
            raise ValueError("visual ref TTL must be positive")
        self.ttl_seconds = float(ttl_seconds)
        self.min_mapping_confidence = float(min_mapping_confidence)
        self.generation = 1
        self._refs: dict[str, VisualTarget] = {}
        self._serial = 0

    def new_generation(self) -> int:
        self.generation += 1
        self._refs.clear()
        return self.generation

    def issue(
        self,
        *,
        snapshot_id: str,
        pid: int,
        window_id: int,
        capture_dimensions: tuple[int, int],
        source_region: tuple[int, int, int, int],
        target_bounds: tuple[int, int, int, int],
        mapping_confidence: float,
        now: float,
        source_capture_dimensions: tuple[int, int] | None = None,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        crop_digest: str | None = None,
    ) -> VisualTarget:
        capture_width, capture_height = capture_dimensions
        region_x, region_y, region_width, region_height = source_region
        source_width, source_height = source_capture_dimensions or (
            max(capture_width, region_x + region_width),
            max(capture_height, region_y + region_height),
        )
        target_x, target_y, target_width, target_height = target_bounds
        confidence = float(mapping_confidence)
        x_scale = float(scale_x)
        y_scale = float(scale_y)
        if (
            not snapshot_id
            or int(pid) <= 0
            or int(window_id) <= 0
            or capture_width <= 0
            or capture_height <= 0
            or source_width <= 0
            or source_height <= 0
            or region_x < 0
            or region_y < 0
            or region_width <= 0
            or region_height <= 0
            or region_x + region_width > source_width
            or region_y + region_height > source_height
            or target_x < 0
            or target_y < 0
            or target_width <= 0
            or target_height <= 0
            or target_x + target_width > capture_width
            or target_y + target_height > capture_height
            or x_scale <= 0
            or y_scale <= 0
            or confidence < self.min_mapping_confidence
        ):
            raise VisualGeometryAmbiguous("visual geometry or mapping confidence is ambiguous")
        self._serial += 1
        digest = hashlib.sha256(
            f"{snapshot_id}:{self.generation}:{pid}:{window_id}:{self._serial}".encode()
        ).hexdigest()[:12]
        ref = f"v{self.generation:04x}:{digest}"
        target = VisualTarget(
            ref=ref,
            snapshot_id=str(snapshot_id),
            generation=self.generation,
            pid=int(pid),
            window_id=int(window_id),
            capture_dimensions=(int(capture_width), int(capture_height)),
            source_capture_dimensions=(int(source_width), int(source_height)),
            source_region=(int(region_x), int(region_y), int(region_width), int(region_height)),
            target_bounds=(int(target_x), int(target_y), int(target_width), int(target_height)),
            scale_x=x_scale,
            scale_y=y_scale,
            mapping_confidence=confidence,
            crop_digest=str(crop_digest) if crop_digest else None,
            issued_at=float(now),
            expires_at=float(now) + self.ttl_seconds,
        )
        self._refs[ref] = target
        return target

    def resolve(
        self,
        ref: str,
        *,
        snapshot_id: str,
        pid: int,
        window_id: int,
        now: float,
    ) -> VisualTarget:
        target = self._refs.get(str(ref))
        if target is None:
            raise VisualRefStale("unknown or stale visual ref")
        if float(now) > target.expires_at:
            self._refs.pop(str(ref), None)
            raise VisualRefStale("visual ref expired")
        if (
            target.generation != self.generation
            or target.snapshot_id != str(snapshot_id)
            or target.pid != int(pid)
            or target.window_id != int(window_id)
        ):
            raise VisualRefStale("visual ref belongs to a stale snapshot or window")
        return target
    def consume(
        self,
        ref: str,
        *,
        snapshot_id: str,
        pid: int,
        window_id: int,
        now: float,
    ) -> VisualTarget:
        target = self.resolve(
            ref, snapshot_id=snapshot_id, pid=pid, window_id=window_id, now=now
        )
        self._refs.pop(str(ref), None)
        return target


@dataclass(frozen=True)
class FastVisionRequest:
    """Minimal sensor request.  It cannot choose or execute an action."""

    goal: str
    snapshot_id: str
    pid: int
    window_id: int
    region: tuple[int, int, int, int]
    capture_dimensions: tuple[int, int]

    def compact(self) -> dict[str, Any]:
        return {
            "task": "locate_target",
            "goal": self.goal,
            "snapshot_id": self.snapshot_id,
            "pid": self.pid,
            "window_id": self.window_id,
            "region": list(self.region),
            "capture_dimensions": list(self.capture_dimensions),
            "output": "bounds,confidence",
            "selection_authority": "llm",
        }


def classify_web_boundary(
    *,
    external_information: bool,
    local_authenticated_session: bool,
) -> dict[str, Any]:
    """Declare the boundary; Hermes decides when to cross it."""
    if local_authenticated_session:
        route = "walter_operator"
    elif external_information:
        route = "walter_browse"
    else:
        route = "llm_decides"
    return {
        "route": route,
        "authority": "llm",
        "operator_web_engine": False,
    }


class FixedSshMacPresenceProbe:
    """One constant, read-only SSH batch; no model-controlled shell text."""

    REMOTE_COMMAND = (
        "os_version=$(/usr/bin/sw_vers -productVersion 2>/dev/null); "
        "idle_ns=$(/usr/sbin/ioreg -r -c IOHIDSystem -d 1 2>/dev/null | "
        "/usr/bin/sed -n 's/.*\"HIDIdleTime\" = \\([0-9][0-9]*\\).*/\\1/p' | /usr/bin/head -n 1); "
        "front_asn=$(/usr/bin/lsappinfo front 2>/dev/null | /usr/bin/head -n 1); "
        "foreground_app=$(/usr/bin/lsappinfo info -only name \"$front_asn\" 2>/dev/null | "
        "/usr/bin/sed -n 's/.*\"LSDisplayName\"=\"\\([^\"]*\\)\".*/\\1/p'); "
        "console_users=$(/usr/sbin/ioreg -l -w 0 2>/dev/null | "
        "/usr/bin/sed -n '/\"IOConsoleUsers\" =/p' | /usr/bin/head -n 1); "
        "case \"$console_users\" in *CGSSessionScreenIsLocked*=Yes*|*CGSSessionScreenIsLocked*=true*) screen_locked=true;; "
        "*kCGSSessionOnConsoleKey*=Yes*) screen_locked=false;; *) screen_locked=unknown;; esac; "
        "/usr/bin/printf 'os_version=%s\\nidle_ns=%s\\nscreen_locked=%s\\nforeground_app=%s\\n' "
        '"$os_version" "$idle_ns" "$screen_locked" "$foreground_app"'
    )

    def __init__(
        self,
        *,
        config_path: str | Path,
        now: Callable[[], float],
        foreground_window: Callable[[str | None], str | None] | None = None,
        execute: Callable[[list[str], int], str] | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.now = now
        self.foreground_window = foreground_window
        self.execute = execute or self._execute

    def __call__(self) -> UserPresence:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("remote CUA config must be a JSON object")
        timeout = int(config.get("connect_timeout_seconds", 8))
        argv = [
            str(config.get("ssh_path") or "/usr/bin/ssh"),
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", f"ConnectTimeout={timeout}",
            "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={Path(str(config['known_hosts_file'])).expanduser()}",
            "-i", str(Path(str(config["identity_file"])).expanduser()),
            f"{config['username']}@{config['host']}",
            self.REMOTE_COMMAND,
        ]
        output = self.execute(argv, timeout + 4)
        raw: dict[str, Any] = {}
        for line in output.splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"os_version", "idle_ns", "screen_locked", "foreground_app"}:
                raw[key] = value.strip()
        if self.foreground_window is not None:
            raw["foreground_window"] = self.foreground_window(_optional_text(raw.get("foreground_app")))
        known = sum(raw.get(key) not in {None, "", "unknown"} for key in (
            "idle_ns", "screen_locked", "foreground_app", "foreground_window"
        ))
        return UserPresence.from_mapping(
            raw,
            observed_at=float(self.now()),
            source="macos_read_only_ssh",
            confidence=known / 4.0,
        )

    @staticmethod
    def _execute(argv: list[str], timeout: int) -> str:
        return subprocess.run(
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        ).stdout
