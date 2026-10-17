"""Durable W.Alter Computer Use backend boundary.

This plugin intentionally owns policy, not the calling harness' computer_use tool:
the calling harness continues to own approval, action dispatch, session lifecycle,
and multimodal result handling.  The plugin selects an exact native window
and may run one bounded background recovery rung before returning, so targeting
and local control policy can evolve outside the the calling harness checkout.
"""

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
import logging
import os
import re
import stat
import struct
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol

from .types import ActionResult, CaptureResult

logger = logging.getLogger(__name__)


from . import observer as _OBSERVER
from . import runtime as _RUNTIME

_SCREEN_SENTINELS = {"screen", "desktop", "fullscreen", "full screen", "all"}
_NON_APP_PREFIXES = ("@!", "desktop", "gnome-shell")


@dataclass(frozen=True)
class CaptureTarget:
    """Exact native target selected before a capture is delegated."""

    pid: int
    window_id: int
    app_name: str = ""
    title: str = ""



def _element_row(element: Any) -> Dict[str, Any]:
    bounds = getattr(element, "bounds", (0, 0, 0, 0))
    row = {
        "index": int(getattr(element, "index", 0)),
        "role": str(getattr(element, "role", "") or ""),
        "label": str(getattr(element, "label", "") or ""),
        "bounds": list(bounds) if isinstance(bounds, (tuple, list)) else [0, 0, 0, 0],
    }
    token = getattr(element, "element_token", None)
    if isinstance(token, str) and token:
        row["ref"] = token
    return row


def compact_ax_state(capture: CaptureResult, *, max_items: int = 80) -> Dict[str, Any]:
    """Project one live AX snapshot without inventing refs or app recipes."""

    elements = list(capture.elements or [])
    max_items = max(1, min(int(max_items), 200))
    actionable_roles = {
        "axbutton", "axlink", "axtextfield", "axtextarea", "axcheckbox",
        "axradiobutton", "axpopupbutton", "axmenuitem", "axcombobox",
    }
    actionable = []
    for element in elements:
        row = _element_row(element)
        if row["role"].lower() in actionable_roles and row.get("ref"):
            actionable.append(row)
    def geometry_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
        bounds = row["bounds"]
        visible = (
            len(bounds) == 4
            and float(bounds[2] or 0) > 0
            and float(bounds[3] or 0) > 0
        )
        return (
            not visible,
            float(bounds[1] or 0) if visible else 0,
            float(bounds[0] or 0) if visible else 0,
        )

    actionable.sort(key=geometry_key)
    tokens = [row["ref"] for row in actionable]
    snapshot_id = (
        hashlib.sha256("\n".join(tokens).encode("utf-8")).hexdigest()[:20]
        if tokens
        else None
    )
    return {
        "app": capture.app,
        "window": capture.window_title,
        "snapshot_id": snapshot_id,
        "actionable": actionable[:max_items],
        "total_elements": len(elements),
        "reliable_refs": len(tokens),
        "truncated": len(actionable) > max_items,
    }


def _ax_semantic_fingerprint(capture: CaptureResult) -> tuple[tuple[Any, ...], ...]:
    """Describe observable AX state while ignoring snapshot-local refs/indexes."""

    rows = []
    for element in capture.elements or []:
        attributes = getattr(element, "attributes", {}) or {}
        scalar_attributes = tuple(sorted(
            (str(key), value)
            for key, value in attributes.items()
            if isinstance(value, (str, int, float, bool, type(None)))
        ))
        rows.append((
            str(getattr(element, "role", "") or ""),
            str(getattr(element, "label", "") or ""),
            tuple(getattr(element, "bounds", (0, 0, 0, 0))),
            scalar_attributes,
        ))
    return tuple(sorted(rows, key=repr))


def verify_targeted_ax_change(
    before: CaptureResult,
    after: CaptureResult,
) -> Dict[str, Any]:
    """Prove a real targeted AX change without screenshots or app recipes."""

    changed = _ax_semantic_fingerprint(before) != _ax_semantic_fingerprint(after)
    return {
        "verified": changed,
        "source": "targeted_ax_observation",
        "changed": changed,
    }



class CaptureStrategy(Protocol):
    """Policy contract for selecting one live native capture target."""

    name: str

    def select(
        self,
        windows: Iterable[Mapping[str, Any]],
        *,
        app: Optional[str],
    ) -> Optional[CaptureTarget]: ...


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _window_on_screen(window: Mapping[str, Any]) -> bool:
    if window.get("off_screen") is True:
        return False
    if window.get("is_on_screen") is False:
        return False
    return True


def _has_substantive_bounds(window: Mapping[str, Any]) -> bool:
    """Reject explicit tiny/zero surfaces, but keep unknown geometry usable."""
    bounds = window.get("bounds")
    if not isinstance(bounds, Mapping):
        return True
    width = bounds.get("width", bounds.get("w"))
    height = bounds.get("height", bounds.get("h"))
    if isinstance(width, bool) or isinstance(height, bool):
        return True
    try:
        width_f = float(width)
        height_f = float(height)
    except (TypeError, ValueError):
        return True
    if width_f <= 0 or height_f <= 0:
        return False
    return width_f >= 200 and height_f >= 100


def _window_area(window: Mapping[str, Any]) -> Optional[float]:
    """Return known positive surface area, or ``None`` for legacy rows."""

    bounds = window.get("bounds")
    if not isinstance(bounds, Mapping):
        return None
    width = bounds.get("width", bounds.get("w"))
    height = bounds.get("height", bounds.get("h"))
    if isinstance(width, bool) or isinstance(height, bool):
        return None
    try:
        width_f = float(width)
        height_f = float(height)
    except (TypeError, ValueError):
        return None
    return max(width_f, 0) * max(height_f, 0)


def _window_text(window: Mapping[str, Any]) -> str:
    return " ".join(
        str(window.get(key) or "")
        for key in ("app_name", "bundle_id", "bundleId", "name", "title")
    ).strip()


class SafeWindowStrategy:
    """Conservative native-window target policy.

    ``list_windows()`` order is retained among surfaces whose area is comparable
    to the application's largest candidate. This drops menu/toolbar strips while
    preserving z-order between real windows, and retains legacy ordering when
    geometry is unavailable.
    """

    name = "safe-window"

    def select(
        self,
        windows: Iterable[Mapping[str, Any]],
        *,
        app: Optional[str],
    ) -> Optional[CaptureTarget]:
        requested = (app or "").strip().lower()
        candidates = []
        for window in windows:
            if not isinstance(window, Mapping) or not _window_on_screen(window):
                continue
            haystack = _window_text(window).lower()
            if not requested and any(
                haystack.startswith(prefix) for prefix in _NON_APP_PREFIXES
            ):
                continue
            if requested and requested not in haystack:
                continue
            if not _has_substantive_bounds(window):
                continue
            pid = _positive_int(window.get("pid"))
            window_id = _positive_int(window.get("window_id"))
            if pid is None or window_id is None:
                continue
            candidates.append(
                (
                    CaptureTarget(
                        pid=pid,
                        window_id=window_id,
                        app_name=str(window.get("app_name") or ""),
                        title=str(window.get("title") or ""),
                    ),
                    _window_area(window),
                )
            )
        if not candidates:
            return None
        known_areas = [area for _, area in candidates if area is not None]
        if not known_areas:
            return candidates[0][0]
        comparable_floor = max(known_areas) * 0.5
        for target, area in candidates:
            if area is None or area >= comparable_floor:
                return target
        return candidates[0][0]


_STRATEGIES: Dict[str, CaptureStrategy] = {
    SafeWindowStrategy.name: SafeWindowStrategy(),
}


def register_capture_strategy(name: str, strategy: CaptureStrategy) -> None:
    """Add a named capture strategy without touching the calling harness core."""
    normalized = str(name or "").strip().lower()
    if not normalized:
        raise ValueError("capture strategy name cannot be empty")
    if not callable(getattr(strategy, "select", None)):
        raise TypeError("capture strategy must provide select()")
    if normalized in _STRATEGIES and _STRATEGIES[normalized] is not strategy:
        raise ValueError(f"capture strategy {normalized!r} is already registered")
    _STRATEGIES[normalized] = strategy


def _configured_strategy_name(config=None) -> str:
    try:
        computer_use = (config or {}).get("computer_use") or {}
        value = computer_use.get("capture_strategy")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    except Exception:
        logger.debug("Walter computer-use strategy lookup failed", exc_info=True)
    return SafeWindowStrategy.name


def _configured_driver_command(config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Resolve a trusted plugin-configured cua-driver compatibility shim."""

    loaded = config or {}
    computer_use = (loaded or {}).get("computer_use") or {}
    walter = computer_use.get("walter") or {}
    raw = walter.get("driver_command") if isinstance(walter, Mapping) else None
    if raw in (None, ""):
        return None
    if not isinstance(raw, str) or not raw.startswith("/") or "\x00" in raw:
        raise ValueError("computer_use.walter.driver_command must be an absolute path")
    path = Path(raw)
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"configured W.Alter driver does not exist: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise PermissionError("configured W.Alter driver must be a single-link regular file")
    if info.st_uid not in {os.getuid(), 0}:
        raise PermissionError("configured W.Alter driver owner is not trusted")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise PermissionError("configured W.Alter driver is writable by group or others")
    if not os.access(path, os.X_OK):
        raise PermissionError("configured W.Alter driver is not executable")
    return str(path)


def _configured_observer_enabled(config: Optional[Dict[str, Any]] = None) -> bool:
    loaded = config or {}
    computer_use = (loaded or {}).get("computer_use") or {}
    walter = computer_use.get("walter") or {}
    observer = walter.get("observer") if isinstance(walter, Mapping) else None
    if not isinstance(observer, Mapping):
        return False
    return observer.get("enabled") is True


def _configured_strategy(config=None) -> CaptureStrategy:
    name = _configured_strategy_name(config)
    strategy = _STRATEGIES.get(name)
    if strategy is None:
        raise RuntimeError(
            f"Unknown W.Alter computer-use capture strategy {name!r}; "
            f"available strategies: {', '.join(sorted(_STRATEGIES))}"
        )
    return strategy


def _image_dimensions(raw: bytes) -> tuple[int, int]:
    if raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) >= 24:
        return struct.unpack(">II", raw[16:24])
    if raw.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(raw):
            if raw[index] != 0xFF:
                index += 1
                continue
            marker = raw[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(raw):
                break
            segment_length = struct.unpack(">H", raw[index : index + 2])[0]
            if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(
                range(0xC9, 0xCC)
            ) | set(range(0xCD, 0xD0)):
                if index + 7 <= len(raw):
                    height, width = struct.unpack(">HH", raw[index + 3 : index + 7])
                    return width, height
                break
            index += max(segment_length, 2)
    return 0, 0


def _mark_capture_integrity(
    capture: CaptureResult, strategy_name: str
) -> CaptureResult:
    """Fail closed on an explicitly empty image from an older host backend."""
    if not hasattr(capture, "capture_valid"):
        capture.capture_valid = None
    if not hasattr(capture, "capture_error"):
        capture.capture_error = None
    current_valid = capture.capture_valid
    if current_valid is not False and capture.png_b64:
        try:
            raw = base64.b64decode(capture.png_b64, validate=False)
            width, height = _image_dimensions(raw)
            if not raw or width <= 0 or height <= 0:
                capture.capture_valid = False
                capture.capture_error = {
                    "code": "invalid_capture_pixels",
                    "message": "The capture returned no verifiable image dimensions.",
                }
        except Exception:
            capture.capture_valid = False
            capture.capture_error = {
                "code": "invalid_capture_pixels",
                "message": "The capture image could not be decoded.",
            }
    coverage = getattr(capture, "capture_coverage", None)
    if not isinstance(coverage, dict):
        coverage = {}
        capture.capture_coverage = coverage
    coverage.setdefault("walter_strategy", strategy_name)
    return capture


class WalterPolicyMixin:
    """Cua backend with W.Alter-owned targeting and bounded local recovery."""

    _action_result = ActionResult
    _capture_result = CaptureResult

    def __init__(
        self,
        permission_mode: str = "standard",
        *,
        observer_enabled: Optional[bool] = None,
        config: Optional[Dict[str, Any]] = None,
        vision_sensor=None,
        transport=None,
    ) -> None:
        self.config = dict(config or {})
        self._vision_sensor = vision_sensor
        if transport is None:
            super().__init__(permission_mode=permission_mode)
        else:
            super().__init__(permission_mode=permission_mode, transport=transport)
        enabled = (
            _configured_observer_enabled(self.config)
            if observer_enabled is None
            else bool(observer_enabled)
        )
        self._walter_observer = _OBSERVER.ObserverRuntime() if enabled else None
        self._walter_observer_critical_ms = deque(maxlen=256)
        self._walter_ref_guard_state = "unmanaged"
        self._walter_expected_refs: Dict[int, str] = {}
        self._visual_refs = _RUNTIME.VisualRefStore(ttl_seconds=3.0)
        self._visual_snapshot_id: Optional[str] = None
        self._window_screenshot_scales: Dict[tuple[int, int], tuple[float, float]] = {}
        self._window_backing_scales: Dict[tuple[int, int], float] = {}
        self._window_normalized_output_scales: Dict[tuple[int, int], tuple[float, float]] = {}
        self._window_logical_dimensions: Dict[tuple[int, int], tuple[int, int]] = {}
        self._walter_observation_guard: Optional[Dict[str, Any]] = None
        self._walter_progress_epoch = 0
        self._walter_last_ax_fingerprint: Optional[tuple[Any, ...]] = None
        self._walter_stalled_action: Optional[Dict[str, Any]] = None
        presence_config = Path(os.environ.get(
            "WALTER_REMOTE_CUA_CONFIG",
            "/root/.config/walter-device-node/remote-cua.json",
        ))
        presence_probe = _RUNTIME.FixedSshMacPresenceProbe(
            config_path=presence_config,
            now=time.time,
            foreground_window=self._foreground_window_title,
        )
        self._walter_origin = _RUNTIME.ActionOrigin.FOREGROUND_USER
        self.presence = _RUNTIME.UserPresenceCache(
            probe=presence_probe,
            ttl_seconds=15.0,
        )

    def _foreground_window_title(self, app: Optional[str]) -> Optional[str]:
        """Reuse current driver inventory; no new probe beyond list_windows."""
        try:
            windows = self.list_windows()
        except Exception:
            return None
        target = SafeWindowStrategy().select(windows, app=app)
        return target.title or None if target is not None else None

    def arm_native_refs(self, capture: CaptureResult) -> None:
        """Bind the next AX action to exactly the snapshot shown to the calling harness."""

        self._walter_exposed_capture = capture
        self._walter_expected_refs = {
            element.index: element.element_token
            for element in (capture.elements or [])
            if element.element_token
        }
        self._walter_ref_guard_state = "armed"

    def _guard_native_ref(
        self,
        element: Optional[int],
        *,
        action: str = "click",
    ) -> Optional[ActionResult]:
        guard_state = getattr(self, "_walter_ref_guard_state", "unmanaged")
        if element is None or guard_state == "unmanaged":
            return None
        if guard_state != "armed":
            return self._annotate_active_result(self._action_result(
                ok=False,
                action=action,
                effect="unverifiable",
                code="stale_element_token",
                message="The AX snapshot exposed to the calling harness was already consumed.",
            ))
        expected = self._walter_expected_refs.get(element)
        current = getattr(self, "_snapshot_tokens", {}).get(element)
        if not expected or current != expected:
            self._walter_ref_guard_state = "consumed"
            return self._annotate_active_result(self._action_result(
                ok=False,
                action=action,
                effect="unverifiable",
                code="stale_element_token",
                message="The native ref no longer belongs to the AX snapshot exposed to the calling harness.",
            ))
        self._walter_ref_guard_state = "consumed"
        return None

    @staticmethod
    def _annotate_active_result(result: ActionResult) -> ActionResult:
        """Attach compact atomic effect evidence to one action."""

        code = str(result.code or "").lower()
        message = str(result.message or "").lower()
        stale = (
            "stale" in code
            or "stale" in message
            or "superseded snapshot" in message
        )
        confirmed = result.verified is True or result.effect == "confirmed"
        failure_reason = None
        if stale:
            failure_reason = "stale_ref"
        elif not confirmed:
            failure_reason = result.code or result.effect or "verification_unavailable"
        result.meta = dict(result.meta)
        result.meta["walter_operator"] = {
            "success": confirmed,
            "effect": result.effect,
            "verified": bool(result.verified is True),
            "verification_source": "driver" if confirmed else None,
            "new_snapshot": None,
            "failure_reason": failure_reason,
            "stale": stale,
            "needs_confirmation": False,
            "evidence_changed": confirmed,
            "automatic_retry_performed": False,
        }
        if confirmed:
            result.meta["walter_operator"]["verification"] = "driver_confirmed"
        return result

    def _duplicate_guard_result(self, action: str, code: str, message: str) -> ActionResult:
        result = self._annotate_active_result(self._action_result(
            ok=False,
            action=action,
            effect="suspected_noop",
            code=code,
            message=message,
        ))
        operator = result.meta["walter_operator"]
        operator["evidence_changed"] = False
        operator["blocked_reason"] = code
        return result

    def _unsafe_input_target(self, action: str) -> Optional[ActionResult]:
        target = re.sub(
            r"[^a-z0-9]+", "", str(getattr(self, "_last_app", "")).lower()
        )
        if target in {"cuadriver", "comtrycuadriver"}:
            return self._duplicate_guard_result(
                action,
                "unsafe_input_target",
                "The safe-window is capture infrastructure, not an input target. "
                "Select the real native app/window before sending input.",
            )
        return None

    def _action_signature(self, action: str, payload: Any) -> tuple[Any, ...]:
        return (
            action,
            getattr(self, "_active_pid", None),
            getattr(self, "_active_window_id", None),
            repr(payload),
        )

    def _stalled_action_refusal(
        self, signature: tuple[Any, ...]
    ) -> Optional[ActionResult]:
        stalled = getattr(self, "_walter_stalled_action", None)
        if (
            isinstance(stalled, Mapping)
            and stalled.get("signature") == signature
            and stalled.get("evidence_epoch")
            == getattr(self, "_walter_progress_epoch", 0)
        ):
            return self._duplicate_guard_result(
                str(signature[0]),
                "duplicate_action_guard",
                "Blocked an identical action because no new evidence was observed.",
            )
        return None

    def _remember_action_outcome(
        self, signature: tuple[Any, ...], result: ActionResult
    ) -> ActionResult:
        confirmed = result.verified is True or result.effect == "confirmed"
        if confirmed:
            self._walter_progress_epoch = getattr(self, "_walter_progress_epoch", 0) + 1
            self._walter_stalled_action = None
        elif result.effect in {"unverifiable", "suspected_noop"} or not result.ok:
            self._walter_stalled_action = {
                "signature": signature,
                "evidence_epoch": getattr(self, "_walter_progress_epoch", 0),
            }
        return result

    @staticmethod
    def _capture_request_key(
        mode: str,
        app: Optional[str],
        pid: Optional[int],
        window_id: Optional[int],
    ) -> tuple[Any, ...]:
        return (str(mode), str(app or ""), pid, window_id)

    def _blocked_duplicate_capture(
        self, request_key: tuple[Any, ...]
    ) -> Optional[CaptureResult]:
        guard = getattr(self, "_walter_observation_guard", None)
        if not isinstance(guard, Mapping):
            return None
        if guard.get("request_key") != request_key or int(guard.get("count", 0)) < 2:
            return None
        cached = guard.get("capture")
        if not isinstance(cached, CaptureResult):
            return None
        assert isinstance(cached, CaptureResult)
        blocked: CaptureResult = deepcopy(cached)
        error = dict(blocked.capture_error or {})
        error["retry_blocked"] = True
        error["message"] = (
            "Duplicate observation blocked: the same pixel failure produced no new evidence."
        )
        blocked.capture_error = error
        coverage = dict(blocked.capture_coverage or {})
        coverage.update({
            "duplicate_observation_guard": "blocked",
            "evidence_changed": False,
            "available_evidence": "native_or_ax" if blocked.elements else "none",
        })
        blocked.capture_coverage = coverage
        return blocked

    def _record_capture_guard(
        self, request_key: tuple[Any, ...], capture: CaptureResult
    ) -> None:
        fingerprint = (
            capture.capture_valid,
            str((capture.capture_error or {}).get("code") or ""),
            _ax_semantic_fingerprint(capture),
        )
        previous = getattr(self, "_walter_observation_guard", None)
        count = 1
        if (
            isinstance(previous, Mapping)
            and previous.get("request_key") == request_key
            and previous.get("fingerprint") == fingerprint
        ):
            count = int(previous.get("count", 0)) + 1
        self._walter_observation_guard = {
            "request_key": request_key,
            "fingerprint": fingerprint,
            "count": count,
            "capture": deepcopy(capture),
        }
        ax_fingerprint = fingerprint[2]
        old_ax = getattr(self, "_walter_last_ax_fingerprint", None)
        if old_ax is not None and old_ax != ax_fingerprint:
            self._walter_progress_epoch = getattr(self, "_walter_progress_epoch", 0) + 1
            self._walter_stalled_action = None
        self._walter_last_ax_fingerprint = ax_fingerprint

    def _publish_capture(self, capture: CaptureResult) -> None:
        runtime = getattr(self, "_walter_observer", None)
        if runtime is None:
            return
        started = time.perf_counter_ns()
        try:
            target = {
                "pid": getattr(self, "_active_pid", None),
                "window_id": getattr(self, "_active_window_id", None),
                "app": getattr(self, "_last_app", None),
            }
            event = runtime.capture_event(
                capture,
                session_id=getattr(self, "_session_id", None),
                target=target,
            )
            runtime.bus.publish(event)
        except Exception:
            logger.debug("Walter observer capture fan-out failed", exc_info=True)
        finally:
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            getattr(self, "_walter_observer_critical_ms", []).append(elapsed)

    def _policy_decision(self, effects: Any) -> tuple[Any, Any]:
        if effects.level == "L0":
            presence = None
        else:
            try:
                presence = self.presence.resolve(now=time.time())
            except Exception:
                presence = _RUNTIME.UserPresence.unknown(observed_at=time.time())
        decision = _RUNTIME.InterruptionPolicy().evaluate(
            effects,
            presence=presence,
            origin=getattr(
                self, "_walter_origin", _RUNTIME.ActionOrigin.FOREGROUND_USER
            ),
        )
        return presence, decision

    def _policy_refusal(self, action: str, effects: Any) -> tuple[Any, Optional[ActionResult]]:
        presence, decision = self._policy_decision(effects)
        if decision.allowed:
            return (presence, None)
        result = self._action_result(
            ok=False,
            action=action,
            code=decision.reason or "interruption_policy_refused",
            effect="unverifiable",
            message=decision.reason or "Action refused by interruption policy.",
        )
        return (presence, self._attach_action_policy(result, presence, decision))

    def _attach_action_policy(
        self,
        result: ActionResult,
        presence: Any,
        decision: Any,
    ) -> ActionResult:
        result = self._annotate_active_result(result)
        operator = result.meta["walter_operator"]
        operator["interruption"] = decision.compact()
        if presence is not None:
            operator["user_presence"] = presence.compact()
        return result

    def _l0_action(self, result: ActionResult) -> ActionResult:
        presence, decision = self._policy_decision(_RUNTIME.ActionEffects(read_only=True))
        return self._attach_action_policy(result, presence, decision)

    @staticmethod
    def capability_offers(
        *,
        ax_available: bool,
        pixels_available: bool,
        target_ref: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Compact advisory offers only; the calling harness retains selection authority."""
        offers: List[Dict[str, Any]] = []
        if ax_available:
            offers.append({
                "action": "ax_click",
                "target": target_ref,
                "confidence": 0.98,
                "interruption": "L1",
                "estimated_latency": "low",
                "verification_cost": "low",
            })
        offers.append({
            "action": "keyboard",
            "confidence": 0.70,
            "interruption": "L1",
            "estimated_latency": "low",
            "verification_cost": "medium",
        })
        if pixels_available:
            offers.append({
                "action": "vision_target",
                "confidence": 0.65,
                "interruption": "L1",
                "estimated_latency": "medium",
                "verification_cost": "medium",
            })
        return offers

    def _ensure_window_zoom_geometry(
        self, pid: int, window_id: int
    ) -> tuple[tuple[float, float], tuple[int, int]]:
        """Resolve zoom's source geometry for one exact window, without foregrounding it.

        Walter regions use window-local logical points. cua-driver zoom crops
        the window's backing screenshot pixels. A pixel-bearing
        get_window_state exposes the authoritative Retina backing scale;
        screenshot_width/height describe its separately normalized output and
        must not be reused as zoom source geometry.
        """
        key = (int(pid), int(window_id))
        scales = getattr(self, "_window_screenshot_scales", None)
        dimensions = getattr(self, "_window_logical_dimensions", None)
        if scales is None:
            scales = self._window_screenshot_scales = {}
        if dimensions is None:
            dimensions = self._window_logical_dimensions = {}

        logical_dimensions = dimensions.get(key)
        if logical_dimensions is None:
            for window in self.list_windows():
                if int(window.get("pid") or 0) != key[0] or int(window.get("window_id") or 0) != key[1]:
                    continue
                bounds = window.get("bounds") or {}
                width = int(round(float(bounds.get("width") or 0)))
                height = int(round(float(bounds.get("height") or 0)))
                if width > 0 and height > 0:
                    logical_dimensions = dimensions[key] = (width, height)
                break
        if logical_dimensions is None:
            raise _RUNTIME.VisualGeometryAmbiguous(
                "exact window logical dimensions are unavailable; targeted crop is unsafe"
            )

        screenshot_scales = scales.get(key)
        if not screenshot_scales or min(screenshot_scales) <= 0.0:
            out = self._session.call_tool("get_window_state", {
                "pid": key[0],
                "window_id": key[1],
                "include_screenshot": True,
                "session": getattr(self, "_session_id", None),
            })
            payload = self._driver_payload(out)
            frame_valid = payload.get("screenshot_frame_valid")
            try:
                backing_scale = float(payload.get("screenshot_scale") or 0.0)
                screenshot_width = int(payload.get("screenshot_width") or 0)
                screenshot_height = int(payload.get("screenshot_height") or 0)
            except (TypeError, ValueError):
                backing_scale = 0.0
                screenshot_width = screenshot_height = 0
            logical_width, logical_height = logical_dimensions
            screenshot_scales = (backing_scale, backing_scale)
            normalized_output_scales = (
                screenshot_width / logical_width if logical_width > 0 else 0.0,
                screenshot_height / logical_height if logical_height > 0 else 0.0,
            )
            if (
                out.get("isError") is True
                or frame_valid is False
                or min(screenshot_scales) <= 0.0
                or min(normalized_output_scales) <= 0.0
                or not (out.get("images") or payload.get("screenshot_png_b64"))
            ):
                raise _RUNTIME.VisualGeometryAmbiguous(
                    "window screenshot geometry is unavailable; targeted crop is unsafe"
                )
            scales[key] = screenshot_scales
            backing_scales = getattr(self, "_window_backing_scales", None)
            if backing_scales is None:
                backing_scales = self._window_backing_scales = {}
            backing_scales[key] = backing_scale
            normalized_scales = getattr(self, "_window_normalized_output_scales", None)
            if normalized_scales is None:
                normalized_scales = self._window_normalized_output_scales = {}
            normalized_scales[key] = normalized_output_scales
        return screenshot_scales, logical_dimensions

    def observe(
        self,
        *,
        level: str = "relevant",
        app: Optional[str] = None,
        pid: Optional[int] = None,
        window_id: Optional[int] = None,
        region: Optional[tuple[int, int, int, int]] = None,
    ) -> CaptureResult:
        normalized = str(level).strip().lower()
        if normalized not in {"minimal", "relevant", "detailed", "pixels"}:
            raise ValueError("observation level must be minimal|relevant|detailed|pixels")
        if normalized != "pixels":
            return self.capture(mode="ax", app=app, pid=pid, window_id=window_id)
        if region is None:
            return self.capture(mode="vision", app=app, pid=pid, window_id=window_id)
        if pid is not None and window_id is not None:
            self._active_pid, self._active_window_id = int(pid), int(window_id)
        elif self._active_pid is None or self._active_window_id is None:
            target = SafeWindowStrategy().select(self.list_windows(), app=app)
            if target is None:
                return self._capture_result(mode="vision", width=0, height=0, app=app or "")
            self._active_pid, self._active_window_id = target.pid, target.window_id
        x, y, width, height = region
        if width <= 0 or height <= 0 or x < 0 or y < 0:
            raise ValueError("pixel observation region must have non-negative origin and positive size")
        visual_refs = getattr(self, "_visual_refs", None)
        if visual_refs is not None:
            visual_refs.new_generation()
            self._visual_snapshot_id = None
            self._visual_crop_binding = None
        key = (int(self._active_pid), int(self._active_window_id))
        (screenshot_scale_x, screenshot_scale_y), source_dimensions = (
            self._ensure_window_zoom_geometry(*key)
        )
        source_width, source_height = map(int, source_dimensions)
        if x + width > source_width or y + height > source_height:
            raise _RUNTIME.VisualGeometryAmbiguous(
                "targeted crop exceeds the exact window geometry"
            )
        # Walter regions are stable window-local logical points. cua-driver
        # zoom expects screenshot pixels and pads 20% of the requested inner
        # rectangle on EACH side before applying its output-only 500px cap.
        # Inverting that padding (inner = desired 5/7, inset = desired 1/7)
        # makes the driver's padded source rectangle equal the Walter region.
        desired_x1 = float(x) * screenshot_scale_x
        desired_y1 = float(y) * screenshot_scale_y
        desired_width = float(width) * screenshot_scale_x
        desired_height = float(height) * screenshot_scale_y
        driver_x1 = desired_x1 + desired_width / 7.0
        driver_y1 = desired_y1 + desired_height / 7.0
        driver_x2 = desired_x1 + desired_width * 6.0 / 7.0
        driver_y2 = desired_y1 + desired_height * 6.0 / 7.0
        out = self._session.call_tool("zoom", {
            "pid": int(self._active_pid),
            "window_id": int(self._active_window_id),
            "x1": driver_x1,
            "y1": driver_y1,
            "x2": driver_x2,
            "y2": driver_y2,
        })
        png_b64 = None
        images = out.get("images")
        if isinstance(images, list) and images:
            png_b64 = images[0]
        payload = self._driver_payload(out)
        png_b64 = png_b64 or payload.get("screenshot_png_b64") or payload.get("image_b64")
        image_mime_type = None
        if png_b64:
            try:
                raw_prefix = base64.b64decode(png_b64[:32] + "===", validate=False)
                image_mime_type = "image/jpeg" if raw_prefix.startswith(b"\xff\xd8") else "image/png"
            except Exception:
                image_mime_type = None
        capture = self._capture_result(
            mode="vision",
            width=int(payload.get("width") or width),
            height=int(payload.get("height") or height),
            png_b64=png_b64,
            app=app or getattr(self, "_last_app", "") or "",
            image_mime_type=image_mime_type,
            capture_valid=bool(png_b64 and image_mime_type),
        )
        if png_b64:
            returned_width, returned_height = capture.width, capture.height
            payload_source_width = _positive_int(
                payload.get("source_width")
                or payload.get("capture_width")
                or payload.get("window_width")
            )
            payload_source_height = _positive_int(
                payload.get("source_height")
                or payload.get("capture_height")
                or payload.get("window_height")
            )
            source_known = bool(
                source_width and source_height
                and x + width <= source_width
                and y + height <= source_height
            )
            output_source_width = desired_width
            output_source_height = desired_height
            output_scale_x = returned_width / output_source_width if output_source_width > 0 else 0.0
            output_scale_y = returned_height / output_source_height if output_source_height > 0 else 0.0
            mapping_scale_x = returned_width / width if width > 0 else 0.0
            mapping_scale_y = returned_height / height if height > 0 else 0.0
            geometry_ambiguous = not (
                returned_width > 0 and returned_height > 0
                and output_scale_x > 0 and output_scale_y > 0
                and mapping_scale_x > 0 and mapping_scale_y > 0
                and source_known
            )
            mapping_confidence = (
                0.99 if not geometry_ambiguous and abs(mapping_scale_x - 1.0) <= 0.001 else
                0.97 if not geometry_ambiguous else 0.0
            )
            self._last_capture_geometry = {
                "pid": self._active_pid,
                "window_id": self._active_window_id,
                # Core coordinate guards validate the eventual window-local
                # visual-ref click against these logical source bounds.
                "width": source_width,
                "height": source_height,
                "coordinate_space": "window_logical_points",
                "driver_coordinate_space": "window_screenshot_pixels",
                "source_region": [x, y, width, height],
                "source_dimensions": [source_width, source_height],
                "screenshot_scale_x": screenshot_scale_x,
                "screenshot_scale_y": screenshot_scale_y,
                "backing_scale": getattr(self, "_window_backing_scales", {}).get(key),
                "normalized_output_scales": list(
                    getattr(self, "_window_normalized_output_scales", {}).get(key, ())
                ),
                "driver_requested_region": [
                    driver_x1, driver_y1, driver_x2 - driver_x1, driver_y2 - driver_y1
                ],
                "driver_padded_source_region": [
                    desired_x1, desired_y1, desired_width, desired_height
                ],
                "output_dimensions": [returned_width, returned_height],
                "output_scale_x": output_scale_x,
                "output_scale_y": output_scale_y,
                # Back-compat for VisualRefStore: these map returned crop
                # pixels directly into Walter's logical source region.
                "requested_region": [x, y, width, height],
                "returned_dimensions": [returned_width, returned_height],
                "source_capture_dimensions": [source_width, source_height],
                "scale_x": mapping_scale_x,
                "scale_y": mapping_scale_y,
                "mapping_confidence": mapping_confidence,
                "geometry_ambiguous": geometry_ambiguous,
                "source": "window_screenshot_scale+driver_zoom_contract",
                "driver_metadata": {
                    "source_width": payload_source_width,
                    "source_height": payload_source_height,
                },
            }
        return capture

    @staticmethod
    def _vision_bounds(payload: Mapping[str, Any]) -> tuple[tuple[int, int, int, int], float, str]:
        bounds = payload.get("bounds")
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            raise _RUNTIME.VisualGeometryAmbiguous("vision sensor returned no target bounds")
        try:
            normalized = tuple(int(round(float(value))) for value in bounds)
            confidence = float(payload.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise _RUNTIME.VisualGeometryAmbiguous("vision sensor geometry is invalid") from exc
        if confidence < 0.95:
            raise _RUNTIME.VisualGeometryAmbiguous("vision sensor confidence is insufficient")
        return normalized, confidence, str(payload.get("description") or "").strip()

    def _call_targeted_vision_sensor(
        self, request: Any, capture: CaptureResult
    ) -> Dict[str, Any]:
        """Locate one target in one crop; never select or execute an action."""
        if not capture.png_b64:
            raise _RUNTIME.VisualGeometryAmbiguous("targeted crop contains no pixels")
        if self._vision_sensor is None:
            raise RuntimeError("targeted vision sensor is not configured for this client")
        fence = getattr(self, "_walter_result_fence", None)
        if callable(fence):
            fence()  # Reject a capture invalidated before any auxiliary model sees it.
        return self._vision_sensor(request, capture)

    def vision_target(
        self,
        *,
        goal: str,
        snapshot_id: str,
        pid: int,
        window_id: int,
        region: tuple[int, int, int, int],
        source_capture_dimensions: tuple[int, int],
        app: Optional[str] = None,
        candidate_window_bounds: Optional[tuple[int, int, int, int]] = None,
    ) -> Dict[str, Any]:
        """Consume one targeted crop as a sensor and expose a ref back to the calling harness."""
        started = time.perf_counter()
        if not str(goal).strip() or not str(snapshot_id).strip():
            raise ValueError("vision_target requires goal and snapshot_id")
        source_width, source_height = map(int, source_capture_dimensions)
        if source_width > 0 and source_height > 0:
            self._window_logical_dimensions[(int(pid), int(window_id))] = (
                source_width, source_height
            )
        crop = self.observe(
            level="pixels", app=app, pid=int(pid), window_id=int(window_id), region=region
        )
        geometry = dict(getattr(self, "_last_capture_geometry", None) or {})
        region_x, region_y, region_width, region_height = map(int, region)
        returned_width, returned_height = crop.width, crop.height
        scale_x = returned_width / region_width if region_width > 0 else 0.0
        scale_y = returned_height / region_height if region_height > 0 else 0.0
        geometry.update({
            "pid": int(pid),
            "window_id": int(window_id),
            "requested_region": [region_x, region_y, region_width, region_height],
            "returned_dimensions": [returned_width, returned_height],
            "source_capture_dimensions": [source_width, source_height],
            "scale_x": scale_x,
            "scale_y": scale_y,
        })
        geometry_ambiguous = not (
            crop.png_b64 and crop.capture_valid is not False
            and source_width > 0 and source_height > 0
            and region_x >= 0 and region_y >= 0
            and region_width > 0 and region_height > 0
            and region_x + region_width <= source_width
            and region_y + region_height <= source_height
            and returned_width > 0 and returned_height > 0
            and scale_x > 0 and scale_y > 0
        )
        mapping_confidence = (
            0.99 if not geometry_ambiguous and abs(scale_x - 1.0) <= 0.001 else
            0.97 if not geometry_ambiguous else 0.0
        )
        geometry.update({
            "mapping_confidence": mapping_confidence,
            "geometry_ambiguous": geometry_ambiguous,
            "source": "driver_zoom_plus_source_geometry",
        })
        self._last_capture_geometry = geometry
        if geometry_ambiguous:
            return {
                "status": "geometry_ambiguous",
                "vision_calls": 0,
                "targeted_crop": True,
                "full_screenshot": False,
                "geometry": geometry,
            }
        request = _RUNTIME.FastVisionRequest(
            goal=str(goal).strip(), snapshot_id=str(snapshot_id), pid=int(pid),
            window_id=int(window_id), region=tuple(map(int, region)),
            capture_dimensions=(returned_width, returned_height),
        )
        sensor = self._call_targeted_vision_sensor(request, crop)
        bounds_raw = sensor.get("bounds") if isinstance(sensor, Mapping) else None
        try:
            if not isinstance(bounds_raw, (list, tuple)) or len(bounds_raw) != 4:
                raise ValueError
            bounds = tuple(int(round(float(value))) for value in bounds_raw)
            sensor_confidence = float(sensor.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise _RUNTIME.VisualGeometryAmbiguous("vision sensor geometry is invalid") from exc
        description = str(sensor.get("description") or "").strip()
        cross_modal_agreement = False
        if candidate_window_bounds is not None:
            candidate_x, candidate_y, candidate_w, candidate_h = map(int, candidate_window_bounds)
            expected = (
                (candidate_x - region_x) * scale_x,
                (candidate_y - region_y) * scale_y,
                candidate_w * scale_x,
                candidate_h * scale_y,
            )
            bx, by, bw, bh = bounds
            ex, ey, ew, eh = expected
            intersection_w = max(0.0, min(bx + bw, ex + ew) - max(bx, ex))
            intersection_h = max(0.0, min(by + bh, ey + eh) - max(by, ey))
            intersection = intersection_w * intersection_h
            union = max(1.0, bw * bh + ew * eh - intersection)
            cross_modal_agreement = intersection / union >= 0.45
        if sensor_confidence < 0.95 and not (
            sensor_confidence >= 0.80 and cross_modal_agreement
        ):
            raise _RUNTIME.VisualGeometryAmbiguous("vision sensor confidence is insufficient")
        crop_digest = hashlib.sha256(crop.png_b64.encode()).hexdigest()
        crop_binding = (
            str(snapshot_id), int(pid), int(window_id), tuple(map(int, region)),
            (source_width, source_height), (returned_width, returned_height),
            round(scale_x, 6), round(scale_y, 6), crop_digest,
        )
        if getattr(self, "_visual_crop_binding", None) != crop_binding:
            self._visual_refs.new_generation()
            self._visual_snapshot_id = str(snapshot_id)
            self._visual_crop_binding = crop_binding
        issued_now = time.time()
        self._vision_ref_now = issued_now
        target = self._visual_refs.issue(
            snapshot_id=str(snapshot_id), pid=int(pid), window_id=int(window_id),
            capture_dimensions=(returned_width, returned_height),
            source_capture_dimensions=(source_width, source_height),
            source_region=tuple(map(int, region)), target_bounds=bounds,
            scale_x=scale_x, scale_y=scale_y,
            mapping_confidence=min(
                mapping_confidence, 0.99 if cross_modal_agreement else sensor_confidence
            ),
            crop_digest=crop_digest, now=issued_now,
        )
        return {
            "status": "vision_target_ready",
            "visual_ref": target.ref,
            "coordinate": list(target.window_coordinate),
            "description": description,
            "geometry": geometry,
            "vision_calls": 1,
            "targeted_crop": True,
            "full_screenshot": False,
            "blind_click": False,
            "cross_modal_agreement": cross_modal_agreement,
            "sensor_confidence": sensor_confidence,
            "mapping_confidence": min(mapping_confidence, 0.99 if cross_modal_agreement else sensor_confidence),
            "operator_latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def click_visual_ref(
        self,
        ref: str,
        *,
        snapshot_id: str,
        pid: int,
        window_id: int,
        now: Optional[float] = None,
    ) -> ActionResult:
        """Consume one visual ref and execute exactly one LLM-selected click."""
        try:
            target = self._visual_refs.consume(
                str(ref), snapshot_id=str(snapshot_id), pid=int(pid),
                window_id=int(window_id), now=time.time() if now is None else float(now),
            )
        except _RUNTIME.VisualRefStale as exc:
            return self._annotate_active_result(self._action_result(
                ok=False, action="click_visual_ref", effect="unverifiable",
                code="stale_visual_ref", message=str(exc),
            ))
        except _RUNTIME.VisualGeometryAmbiguous as exc:
            return self._annotate_active_result(self._action_result(
                ok=False, action="click_visual_ref", effect="unverifiable",
                code="visual_geometry_ambiguous", message=str(exc),
            ))
        effects = _RUNTIME.ActionEffects(visible_ui=True, pointer=True)
        presence, refusal = self._policy_refusal("click_visual_ref", effects)
        if refusal is not None:
            return refusal
        decision = self._policy_decision(effects)[1]
        logical_x, logical_y = target.window_coordinate
        action_scales = getattr(self, "_window_normalized_output_scales", {}).get(
            (int(pid), int(window_id))
        )
        if not action_scales or min(action_scales) <= 0.0:
            return self._annotate_active_result(self._action_result(
                ok=False, action="click_visual_ref", effect="unverifiable",
                code="visual_action_geometry_unavailable",
                message="window action screenshot geometry is unavailable",
            ))
        action_x = int(round(logical_x * action_scales[0]))
        action_y = int(round(logical_y * action_scales[1]))
        result = super().click(
            element=None, x=action_x, y=action_y, button="left", click_count=1,
            modifiers=None, delivery_mode="background", bring_to_front=False,
        )
        result.action = "click_visual_ref"
        result = self._attach_action_policy(result, presence, decision)
        result.meta["walter_operator"]["visual_ref"] = target.ref
        result.meta["walter_operator"]["blind_click"] = False
        result.meta["walter_operator"]["targeted_verification_required"] = True
        self._pending_visual_verification = target
        return result

    def targeted_verify_visual(
        self,
        *,
        snapshot_id: str,
        pid: int,
        window_id: int,
    ) -> Dict[str, Any]:
        """Verify one visual action using the exact bound crop, without another vision call."""
        target = getattr(self, "_pending_visual_verification", None)
        if (
            target is None
            or target.snapshot_id != str(snapshot_id)
            or target.pid != int(pid)
            or target.window_id != int(window_id)
            or not target.crop_digest
        ):
            return {
                "status": "stale_visual_ref",
                "verified": False,
                "vision_calls": 0,
                "targeted_crop": True,
            }
        capture = self.observe(
            level="pixels", app=None, pid=int(pid), window_id=int(window_id),
            region=target.source_region,
        )
        digest = (
            hashlib.sha256(capture.png_b64.encode()).hexdigest()
            if capture.png_b64 and capture.capture_valid is not False else None
        )
        verified = bool(digest and digest != target.crop_digest)
        self._pending_visual_verification = None
        return {
            "status": "verified" if verified else "unverifiable",
            "verified": verified,
            "verification_source": "targeted_crop_digest",
            "vision_calls": 0,
            "targeted_crop": True,
            "full_screenshot": False,
        }

    def clipboard_read(self, *, include_text: bool = False) -> Dict[str, Any]:
        out = self._session.call_tool("clipboard_read", {
            "session": self._session_id,
            "include_text": bool(include_text),
        })
        return self._driver_payload(out)

    def clipboard_write(
        self,
        *,
        text: Optional[str] = None,
        file_path: Optional[str] = None,
        image_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        supplied = [value is not None for value in (text, file_path, image_path)]
        if sum(supplied) != 1:
            raise ValueError("clipboard_write requires exactly one of text, file_path, image_path")
        args: Dict[str, Any] = {"session": self._session_id}
        if text is not None:
            args["text"] = text
        elif file_path is not None:
            args["file_path"] = file_path
        else:
            args["image_path"] = image_path
        out = self._session.call_tool("clipboard_write", args)
        payload = self._driver_payload(out)
        return payload or {"status": "written"}

    def wait(self, seconds: float) -> ActionResult:
        return self._l0_action(super().wait(seconds))

    def list_apps(self) -> List[Dict[str, Any]]:
        return super().list_apps()

    def _remember_window_dimensions(self, windows: Any) -> None:
        dimensions = getattr(self, "_window_logical_dimensions", None)
        if dimensions is None:
            dimensions = self._window_logical_dimensions = {}
        if not isinstance(windows, (list, tuple)):
            return
        for window in windows:
            try:
                key = (int(window.get("pid") or 0), int(window.get("window_id") or 0))
                bounds = window.get("bounds") or {}
                width = int(round(float(bounds.get("width") or 0)))
                height = int(round(float(bounds.get("height") or 0)))
            except (AttributeError, TypeError, ValueError):
                continue
            if min(key) > 0 and width > 0 and height > 0:
                dimensions[key] = (width, height)

    def list_windows(self) -> List[Dict[str, Any]]:
        windows = super().list_windows()
        self._remember_window_dimensions(windows)
        return windows

    def focus_app(self, app: str, raise_window: bool = False) -> ActionResult:
        effects = _RUNTIME.ActionEffects(
            visible_ui=bool(raise_window),
            focus_change=bool(raise_window),
        ) if raise_window else _RUNTIME.ActionEffects(read_only=True)
        presence, refusal = self._policy_refusal("focus_app", effects)
        if refusal is not None:
            return refusal
        decision = self._policy_decision(effects)[1]
        result = super().focus_app(app, raise_window=raise_window)
        return self._attach_action_policy(result, presence, decision)

    def type_text(
        self,
        text: str,
        *,
        delivery_mode: Optional[str] = None,
        bring_to_front: bool = False,
    ) -> ActionResult:
        unsafe = self._unsafe_input_target("type_text")
        if unsafe is not None:
            return unsafe
        signature = self._action_signature(
            "type_text", (text, delivery_mode, bring_to_front)
        )
        stalled = self._stalled_action_refusal(signature)
        if stalled is not None:
            return stalled
        effects = _RUNTIME.ActionEffects(
            visible_ui=True, keyboard=True, focus_change=bool(bring_to_front)
        )
        presence, refusal = self._policy_refusal("type_text", effects)
        if refusal is not None:
            return refusal
        decision = self._policy_decision(effects)[1]
        result = super().type_text(
            text,
            delivery_mode=delivery_mode,
            bring_to_front=bring_to_front,
        )
        return self._remember_action_outcome(
            signature, self._attach_action_policy(result, presence, decision)
        )

    def key(
        self,
        keys: str,
        *,
        delivery_mode: Optional[str] = None,
        bring_to_front: bool = False,
    ) -> ActionResult:
        unsafe = self._unsafe_input_target("key")
        if unsafe is not None:
            return unsafe
        signature = self._action_signature("key", (keys, delivery_mode, bring_to_front))
        stalled = self._stalled_action_refusal(signature)
        if stalled is not None:
            return stalled
        normalized = str(keys).casefold().replace(" ", "")
        if normalized in {"cmd+q", "command+q", "alt+f4"}:
            _, refusal = self._policy_refusal(
                "key", _RUNTIME.ActionEffects(closes_unsaved_work=True)
            )
            assert refusal is not None
            return refusal
        effects = _RUNTIME.ActionEffects(
            visible_ui=True, keyboard=True, focus_change=bool(bring_to_front)
        )
        presence, refusal = self._policy_refusal("key", effects)
        if refusal is not None:
            return refusal
        decision = self._policy_decision(effects)[1]
        result = super().key(
            keys, delivery_mode=delivery_mode, bring_to_front=bring_to_front
        )
        return self._remember_action_outcome(
            signature, self._attach_action_policy(result, presence, decision)
        )

    def drag(self, **kwargs: Any) -> ActionResult:
        from_element = kwargs.get("from_element")
        to_element = kwargs.get("to_element")
        guarded_element = from_element if from_element is not None else to_element
        guard = self._guard_native_ref(guarded_element, action="drag")
        if guard is not None:
            return guard
        effects = _RUNTIME.ActionEffects(visible_ui=True, pointer=True)
        presence, refusal = self._policy_refusal("drag", effects)
        if refusal is not None:
            return refusal
        decision = self._policy_decision(effects)[1]
        return self._attach_action_policy(super().drag(**kwargs), presence, decision)

    def scroll(self, **kwargs: Any) -> ActionResult:
        guard = self._guard_native_ref(kwargs.get("element"), action="scroll")
        if guard is not None:
            return guard
        effects = _RUNTIME.ActionEffects(visible_ui=True, pointer=True)
        presence, refusal = self._policy_refusal("scroll", effects)
        if refusal is not None:
            return refusal
        decision = self._policy_decision(effects)[1]
        return self._attach_action_policy(super().scroll(**kwargs), presence, decision)

    def set_value(self, value: str, element: Optional[int] = None) -> ActionResult:
        guard = self._guard_native_ref(element, action="set_value")
        if guard is not None:
            return guard
        effects = _RUNTIME.ActionEffects(visible_ui=True, keyboard=True)
        presence, refusal = self._policy_refusal("set_value", effects)
        if refusal is not None:
            return refusal
        decision = self._policy_decision(effects)[1]
        return self._attach_action_policy(
            super().set_value(value, element), presence, decision
        )

    def move_cursor(self, x: int, y: int) -> ActionResult:
        effects = _RUNTIME.ActionEffects(visible_ui=True, pointer=True)
        presence, refusal = self._policy_refusal("move_cursor", effects)
        if refusal is not None:
            return refusal
        decision = self._policy_decision(effects)[1]
        return self._attach_action_policy(super().move_cursor(x, y), presence, decision)

    def _publish_action(self, action: ActionResult) -> None:
        runtime = getattr(self, "_walter_observer", None)
        if runtime is None:
            return
        started = time.perf_counter_ns()
        try:
            event = runtime.action_event(
                action,
                session_id=getattr(self, "_session_id", None),
            )
            runtime.bus.publish(event)
        except Exception:
            logger.debug("Walter observer action fan-out failed", exc_info=True)
        finally:
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            getattr(self, "_walter_observer_critical_ms", []).append(elapsed)

    def _action(
        self,
        name: str,
        args: Dict[str, Any],
        *,
        inject_session: bool = True,
    ) -> ActionResult:
        result = self._annotate_active_result(
            super()._action(name, args, inject_session=inject_session)
        )
        self._publish_action(result)
        return result

    def launch_app(
        self,
        *,
        bundle_id: Optional[str] = None,
        name: Optional[str] = None,
        urls: Optional[List[str]] = None,
        additional_arguments: Optional[List[str]] = None,
        creates_new_application_instance: bool = False,
    ) -> Dict[str, Any]:
        """Invoke the native driver app lifecycle without a shell fallback."""
        if not bundle_id and not name and not urls:
            raise ValueError(
                "launch_app requires a bundle_id or name (or a non-empty urls list)"
            )
        args: Dict[str, Any] = {"session": self._session_id}
        if bundle_id:
            args["bundle_id"] = bundle_id
        if name:
            args["name"] = name
        if urls:
            args["urls"] = list(urls)
        if additional_arguments:
            args["additional_arguments"] = list(additional_arguments)
        if creates_new_application_instance:
            args["creates_new_application_instance"] = True
        out = self._session.call_tool("launch_app", args)
        payload = self._driver_payload(out)
        self._remember_window_dimensions(payload.get("windows"))
        if out.get("isError") is True:
            raise RuntimeError(
                "cua-driver launch_app failed: "
                + self._session._logical_error_text(out)
            )
        return payload or {"data": out.get("data", "")}

    @staticmethod
    def _driver_payload(out: Mapping[str, Any]) -> Dict[str, Any]:
        structured = out.get("structuredContent")
        if isinstance(structured, Mapping):
            return dict(structured)
        data = out.get("data")
        if isinstance(data, Mapping):
            return dict(data)
        content = out.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, Mapping):
                    continue
                text = block.get("text")
                if not isinstance(text, str):
                    continue
                try:
                    parsed = json.loads(text)
                except (TypeError, ValueError):
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return {}

    def open_url(self, *, url: str, app: Optional[str] = None) -> Dict[str, Any]:
        """Open one validated URL through native launch_app."""
        if not isinstance(url, str) or not url.strip():
            raise ValueError("open_url requires a non-empty URL")
        normalized = url.strip()
        if normalized.lower() != "about:blank":
            try:
                parsed = urlsplit(normalized)
                valid_http_url = (
                    parsed.scheme.lower() in {"http", "https"}
                    and bool(parsed.netloc)
                    and parsed.hostname is not None
                    and not any(char.isspace() for char in normalized)
                )
            except ValueError:
                valid_http_url = False
            if not valid_http_url:
                raise ValueError(
                    "open_url accepts only http(s) URLs with a host or about:blank"
                )
        launch = self.launch_app(name=app, urls=[normalized])
        return {
            "ok": True,
            "action": "open_url",
            "url": normalized,
            "app": app,
            "launch": launch,
        }

    def verify_state(
        self,
        *,
        pid: int,
        window_id: int,
        expect: List[Dict[str, Any]],
        timeout_ms: int = 0,
        stable_samples: int = 1,
    ) -> Dict[str, Any]:
        """Run the driver's bounded screenshot-free postcondition verifier."""
        out = self._session.call_tool("verify_state", {
            "pid": int(pid),
            "window_id": int(window_id),
            "expect": list(expect),
            "timeout_ms": max(0, min(int(timeout_ms), 10_000)),
            "stable_samples": max(1, min(int(stable_samples), 5)),
            "include_screenshot": False,
            "session": self._session_id,
        })
        payload = self._driver_payload(out)
        if out.get("isError") is True:
            return {
                "ok": False,
                "action": "verify_state",
                "error": self._session._logical_error_text(out),
            }
        return payload or {"ok": False, "action": "verify_state", "evidence": "unavailable"}

    def _remember_element_centers(self, capture: CaptureResult) -> None:
        """Retain only safe pixel fallbacks from the latest observation."""

        centers = {}
        for element in capture.elements:
            x, y, width, height = element.bounds
            if width <= 0 or height <= 0:
                continue
            center = (int(x + width / 2), int(y + height / 2))
            if center[0] < 0 or center[1] < 0:
                continue
            centers[element.index] = center
        self._walter_element_centers = centers

    def _finish_capture(
        self,
        capture: CaptureResult,
        strategy_name: str,
        request_key: Optional[tuple[Any, ...]] = None,
    ) -> CaptureResult:
        # A capture creates a new observation generation.  Refs become usable
        # again only when that exact result is explicitly exposed via
        # arm_native_refs(); identical driver tokens do not make old model
        # context current.
        if getattr(self, "_walter_ref_guard_state", "unmanaged") == "armed":
            self._walter_ref_guard_state = "superseded"
        marked = _mark_capture_integrity(capture, strategy_name)
        if request_key is not None:
            self._record_capture_guard(request_key, marked)
        self._remember_element_centers(marked)
        self._publish_capture(marked)
        self._walter_latest_capture = marked
        return marked

    def capture(
        self,
        mode: str = "som",
        app: Optional[str] = None,
        pid: Optional[int] = None,
        window_id: Optional[int] = None,
    ) -> CaptureResult:
        request_key = self._capture_request_key(mode, app, pid, window_id)
        if (
            pid is not None
            or window_id is not None
            or (app and app.strip().lower() in _SCREEN_SENTINELS)
        ):
            blocked = self._blocked_duplicate_capture(request_key)
            if blocked is not None:
                return blocked
            return self._finish_capture(
                super().capture(mode=mode, app=app, pid=pid, window_id=window_id),
                _configured_strategy_name(self.config),
                request_key,
            )

        strategy = _configured_strategy(self.config)
        windows = self.list_windows()
        target = strategy.select(windows, app=app)
        if target is None:
            self._clear_active_target()
            self._walter_ref_guard_state = "superseded"
            self._walter_expected_refs = {}
            self._visual_refs.new_generation()
            self._last_capture_geometry = None
            capture = self._capture_result(
                mode=mode,
                width=0,
                height=0,
                app=app or "",
                window_title=(
                    f"<no live window matched app={app!r}>"
                    if app
                    else "<no live capture target is available>"
                ),
            )
            self._remember_element_centers(capture)
            self._publish_capture(capture)
            return capture

        resolved_key = self._capture_request_key(
            mode, target.app_name or app, target.pid, target.window_id
        )
        blocked = self._blocked_duplicate_capture(resolved_key)
        if blocked is not None:
            return blocked
        capture = super().capture(
            mode=mode,
            app=target.app_name or app,
            pid=target.pid,
            window_id=target.window_id,
        )
        return self._finish_capture(capture, strategy.name, resolved_key)

    def stop(self) -> None:
        try:
            super().stop()
        finally:
            runtime = getattr(self, "_walter_observer", None)
            if runtime is not None:
                try:
                    runtime.close()
                except Exception:
                    logger.debug("Walter observer shutdown failed", exc_info=True)

    def observer_snapshot(self) -> Dict[str, Any]:
        runtime = getattr(self, "_walter_observer", None)
        if runtime is None:
            return {"enabled": False}
        snapshot = runtime.snapshot()
        snapshot["enabled"] = True
        snapshot["critical_path_latency_ms"] = list(
            getattr(self, "_walter_observer_critical_ms", ())
        )
        return snapshot

    def click(
        self,
        *,
        element: Optional[int] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        click_count: int = 1,
        modifiers: Optional[List[str]] = None,
        delivery_mode: Optional[str] = None,
        bring_to_front: bool = False,
    ) -> ActionResult:
        """Run one safe local recovery rung without another model turn.

        Only a structured ``suspected_noop`` with ``recommended=px`` may
        retry, and only from an element captured in the latest observation.
        Foreground and page escalation remain with the calling harness because they have
        distinct approval and trust requirements.
        """

        refusal = self._guard_native_ref(element)
        if refusal is not None:
            return refusal
        effects = _RUNTIME.ActionEffects(
            visible_ui=True,
            pointer=True,
            focus_change=bool(bring_to_front),
        )
        presence, policy_refusal = self._policy_refusal("click", effects)
        if policy_refusal is not None:
            return policy_refusal
        decision = self._policy_decision(effects)[1]

        initial = super().click(
            element=element,
            x=x,
            y=y,
            button=button,
            click_count=click_count,
            modifiers=modifiers,
            delivery_mode=delivery_mode,
            bring_to_front=bring_to_front,
        )
        initial = self._attach_action_policy(initial, presence, decision)
        escalation = initial.escalation or {}
        center = getattr(self, "_walter_element_centers", {}).get(element)
        may_retry = (
            initial.effect == "suspected_noop"
            and escalation.get("recommended") == "px"
            and element is not None
            and x is None
            and y is None
            and delivery_mode in (None, "background")
            and not bring_to_front
            and center is not None
        )
        if not may_retry:
            return initial

        recovered = super().click(
            element=None,
            x=center[0],
            y=center[1],
            button=button,
            click_count=click_count,
            modifiers=modifiers,
            delivery_mode="background",
            bring_to_front=False,
        )
        recovered = self._annotate_active_result(recovered)
        recovered.meta = dict(recovered.meta)
        recovered.meta["walter_loop"] = {
            "attempts": 2,
            "local_retries": 1,
            "transitions": ["element", "pixel"],
            "stop_reason": (
                "confirmed"
                if recovered.verified is True or recovered.effect == "confirmed"
                else recovered.effect or recovered.code or "driver_verdict"
            ),
        }
        return recovered


def _action_result_facts(result: ActionResult) -> Dict[str, Any]:
    return {
        "ok": result.ok,
        "action": result.action,
        "effect": result.effect,
        "verified": result.verified,
        "code": result.code,
        "message": result.message,
        "meta": result.meta,
    }


def _compact_device_context(backend: Any) -> Dict[str, Any]:
    presence = None
    resolver = getattr(backend, "presence", None)
    if resolver is not None:
        try:
            presence = resolver.resolve(now=time.time()).compact()
        except Exception:
            presence = None
    return {
        "device": os.getenv("WALTER_DEVICE_ID", "main-mac"),
        "platform": "macOS",
        "transport": "tailscale+openssh" if _configured_driver_command(getattr(backend, "config", {})) else "local",
        "ax": "available",
        "pixels": "available",
        "background_input": "available",
        "presence": presence,
    }


def _l1_gate(backend: Any, action: str) -> tuple[Any, Any, Optional[Dict[str, Any]]]:
    effects = _RUNTIME.ActionEffects(visible_ui=True)
    presence, refusal = backend._policy_refusal(action, effects)
    if refusal is not None:
        return presence, None, _action_result_facts(refusal)
    decision = backend._policy_decision(effects)[1]
    return presence, decision, None


def _post_launch_observation(
    backend: Any,
    launch: Mapping[str, Any],
    *,
    app: Optional[str],
    attempts: int = 3,
) -> Dict[str, Any]:
    windows = launch.get("windows") if isinstance(launch.get("windows"), list) else []
    target = SafeWindowStrategy().select(windows, app=app)
    observations = 0
    for _ in range(max(0, min(int(attempts), 3))):
        if target is not None:
            break
        backend.wait(0.5)
        raw_windows = backend.list_windows()
        windows = raw_windows if isinstance(raw_windows, list) else []
        observations += 1
        target = SafeWindowStrategy().select(windows, app=app)
    post_state = None
    if target is not None:
        capture = backend.capture(
            mode="ax",
            app=target.app_name or app,
            pid=target.pid,
            window_id=target.window_id,
        )
        backend.arm_native_refs(capture)
        post_state = compact_ax_state(capture)
    launch_state = launch.get("launch_state") if isinstance(launch.get("launch_state"), Mapping) else {}
    return {
        "process_running": bool(launch.get("pid") or launch_state.get("process_running")),
        "pid": _positive_int(launch.get("pid")),
        "window_ready": target is not None,
        "readiness_observations": observations,
        "windows": [
            {
                "pid": item.get("pid"),
                "window_id": item.get("window_id"),
                "app": item.get("app_name") or item.get("app"),
                "title": item.get("title"),
            }
            for item in windows[:5]
            if isinstance(item, Mapping)
        ],
        "post_state": post_state,
        "freshness": {"observed_at": time.time(), "source": "native+AX"},
    }


def _handle_launch_app_action(backend: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    presence, decision, refusal = _l1_gate(backend, "launch_app")
    if refusal is not None:
        return refusal
    app = str(args.get("app") or "").strip() or None
    bundle_id = str(args.get("bundle_id") or "").strip() or None
    urls = args.get("urls")
    if not isinstance(urls, list):
        urls = None
    launch = backend.launch_app(
        bundle_id=bundle_id,
        name=app,
        urls=[str(value) for value in urls] if urls else None,
        additional_arguments=(
            [str(value) for value in args.get("additional_arguments")]
            if isinstance(args.get("additional_arguments"), list) else None
        ),
        creates_new_application_instance=bool(args.get("creates_new_application_instance", False)),
    )
    return {
        "ok": True,
        "action": "launch_app",
        "requested": {"app": app, "bundle_id": bundle_id, "urls": urls or []},
        "launch": launch,
        "post_action": _post_launch_observation(backend, launch, app=app),
        "device_context": _compact_device_context(backend),
        "user_presence": presence.compact() if presence is not None else None,
        "interruption": decision.compact() if decision is not None else None,
    }


def _handle_open_url_action(backend: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    presence, decision, refusal = _l1_gate(backend, "open_url")
    if refusal is not None:
        return refusal
    url = str(args.get("url") or "").strip()
    app = str(args.get("app") or "").strip() or None
    opened = backend.open_url(url=url, app=app)
    launch = opened.get("launch") if isinstance(opened.get("launch"), Mapping) else {}
    return {
        "ok": True,
        "action": "open_url",
        "url": url,
        "app": app,
        "launch": launch,
        "post_action": _post_launch_observation(backend, launch, app=app),
        "device_context": _compact_device_context(backend),
        "user_presence": presence.compact() if presence is not None else None,
        "interruption": decision.compact() if decision is not None else None,
    }


def _handle_device_context_action(backend: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "action": "device_context", "device_context": _compact_device_context(backend)}


def _handle_vision_target_action(backend: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    return backend.vision_target(
        goal=str(args.get("visual_query") or ""),
        snapshot_id=str(args.get("snapshot_id") or ""),
        pid=int(args["pid"]),
        window_id=int(args["window_id"]),
        region=tuple(map(int, args["region"])),
        source_capture_dimensions=tuple(map(int, args["source_capture_dimensions"])),
        app=str(args.get("app") or "") or None,
        candidate_window_bounds=(
            tuple(map(int, args["candidate_window_bounds"]))
            if args.get("candidate_window_bounds") is not None else None
        ),
    )


def _handle_click_visual_ref_action(backend: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    return _action_result_facts(backend.click_visual_ref(
        str(args.get("visual_ref") or ""),
        snapshot_id=str(args.get("snapshot_id") or ""),
        pid=int(args["pid"]),
        window_id=int(args["window_id"]),
    ))


def _handle_targeted_verify_action(backend: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    return backend.targeted_verify_visual(
        snapshot_id=str(args.get("snapshot_id") or ""),
        pid=int(args["pid"]),
        window_id=int(args["window_id"]),
    )

