"""Walter Operator Lot 2.2 passive live observation bus.

This module has no device, network, browser, LLM, or persistence capability.
It only freezes already-returned V1 facts, enqueues them without waiting, and
computes aggregate telemetry on a daemon worker.
"""

from __future__ import annotations

import hashlib
import json
import math
import queue
import threading
import time
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Callable


class Detail(StrEnum):
    MINIMAL = "minimal"
    RELEVANT = "relevant"
    DETAILED = "detailed"


@dataclass(frozen=True)
class PublishResult:
    accepted: bool
    enqueue_latency_ms: float
    dropped: bool = False
    error: bool = False


@dataclass(frozen=True)
class BusMetrics:
    offered: int
    enqueued: int
    processed: int
    dropped: int
    consumer_errors: int
    publisher_errors: int
    enqueue_latency_ms: tuple[float, ...]
    queue_wait_latency_ms: tuple[float, ...]
    processing_latency_ms: tuple[float, ...]


def _plain(value: Any, *, exclude_pixels: bool = False) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            name = str(key)
            if exclude_pixels and name in {"png_b64", "screenshot_png_b64", "images"}:
                continue
            out[name] = _plain(item, exclude_pixels=exclude_pixels)
        return out
    if isinstance(value, (list, tuple)):
        return [_plain(item, exclude_pixels=exclude_pixels) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"unsupported observer value: {type(value).__name__}")


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _ref_integrity(source: Sequence[str], emitted: Sequence[str]) -> dict[str, Any]:
    source_tokens = tuple(str(token) for token in source)
    emitted_tokens = tuple(str(token) for token in emitted)
    source_counts = Counter(source_tokens)
    emitted_counts = Counter(emitted_tokens)
    preserved = sum((source_counts & emitted_counts).values())
    lost = sum((source_counts - emitted_counts).values())
    unexpected = sum((emitted_counts - source_counts).values())
    exact = source_tokens == emitted_tokens
    mutated = unexpected + (1 if not exact and lost == unexpected == 0 else 0)

    def digest(tokens: tuple[str, ...]) -> str:
        encoded = json.dumps(tokens, ensure_ascii=False, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    return {
        "input": len(source_tokens),
        "emitted": len(emitted_tokens),
        "preserved": preserved,
        "lost": lost,
        "mutated": mutated,
        "exact_sequence": exact,
        "source_sequence_sha256": digest(source_tokens),
        "emitted_sequence_sha256": digest(emitted_tokens),
    }


def frozen_capture_event(
    capture: Any,
    *,
    sequence: int,
    session_id: str | None,
    target: Mapping[str, Any],
) -> Any:
    elements = []
    source_tokens = []
    for element in tuple(getattr(capture, "elements", ()) or ()):
        token = getattr(element, "element_token", None)
        if isinstance(token, str):
            source_tokens.append(token)
        elements.append({
            "index": int(getattr(element, "index", 0)),
            "role": str(getattr(element, "role", "") or ""),
            "label": str(getattr(element, "label", "") or ""),
            "bounds": tuple(getattr(element, "bounds", (0, 0, 0, 0))),
            "element_token": token,
            "attributes": _plain(getattr(element, "attributes", {}) or {}, exclude_pixels=True),
        })
    emitted_tokens = tuple(
        row["element_token"]
        for row in elements
        if isinstance(row.get("element_token"), str)
    )
    event = {
        "kind": "computer_use.observation.v2",
        "operation": "capture",
        "sequence": int(sequence),
        "timestamp": time.time(),
        "session_id": session_id,
        "generation": None,
        "target": _plain(target, exclude_pixels=True),
        "capture": {
            "mode": str(getattr(capture, "mode", "") or ""),
            "width": int(getattr(capture, "width", 0) or 0),
            "height": int(getattr(capture, "height", 0) or 0),
            "app": str(getattr(capture, "app", "") or ""),
            "window_title": str(getattr(capture, "window_title", "") or ""),
            "png_bytes_len": int(getattr(capture, "png_bytes_len", 0) or 0),
            "image_mime_type": getattr(capture, "image_mime_type", None),
            "capture_valid": getattr(capture, "capture_valid", None),
            "capture_error": _plain(getattr(capture, "capture_error", None), exclude_pixels=True),
            "capture_coverage": _plain(getattr(capture, "capture_coverage", None), exclude_pixels=True),
        },
        "elements": elements,
        "ref_integrity": _ref_integrity(source_tokens, emitted_tokens),
        "presence": {
            "screen_locked": None,
            "desktop_unlocked": None,
            "foreground_app": None,
            "idle_duration": None,
            "recent_keyboard_activity": None,
            "recent_pointer_activity": None,
            "user_active": None,
        },
        "provenance": {
            "verbatim": True,
            "source": "WalterCuaBackend.capture return boundary",
            "coordinate_space": "native_bounds",
        },
    }
    return _freeze(event)


def frozen_action_event(
    action: Any,
    *,
    sequence: int,
    session_id: str | None,
) -> Any:
    return _freeze({
        "kind": "computer_use.observation.v2",
        "operation": str(getattr(action, "action", "unknown") or "unknown"),
        "sequence": int(sequence),
        "timestamp": time.time(),
        "session_id": session_id,
        "result": {
            "ok": bool(getattr(action, "ok", False)),
            "effect": getattr(action, "effect", None),
            "verified": getattr(action, "verified", None),
            "code": getattr(action, "code", None),
            "path": getattr(action, "path", None),
            "delivery_mode": getattr(action, "delivery_mode", None),
            "degraded": getattr(action, "degraded", None),
            "escalation": _plain(getattr(action, "escalation", None), exclude_pixels=True),
        },
        "provenance": {
            "verbatim": True,
            "source": "WalterCuaBackend._action return boundary",
        },
    })


class NativeRefRegistry:
    def __init__(self) -> None:
        self._current: frozenset[str] = frozenset()
        self._stale: frozenset[str] = frozenset()

    @property
    def current(self) -> frozenset[str]:
        return self._current

    def observe(self, tokens: Sequence[str]) -> int:
        next_tokens = frozenset(str(token) for token in tokens if isinstance(token, str) and token)
        self._stale = self._current - next_tokens
        self._current = next_tokens
        return len(self._stale)

    def status(self, token: str) -> str:
        if token in self._current:
            return "current"
        if token in self._stale:
            return "stale"
        return "unknown"


def _serialized(value: Any) -> str:
    return json.dumps(_thaw(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compact_capture(event: Mapping[str, Any], *, detail: Detail, max_elements: int = 20) -> dict[str, Any]:
    raw = _thaw(event)
    rows = list(raw.get("elements") or [])
    cap = raw.get("capture") or {}
    minimal = {
        "operation": "capture",
        "sequence": raw.get("sequence"),
        "capture": {
            "mode": cap.get("mode"),
            "width": cap.get("width"),
            "height": cap.get("height"),
            "capture_valid": cap.get("capture_valid"),
        },
        "element_count": len(rows),
        "native_ref_count": sum(isinstance(row.get("element_token"), str) for row in rows),
        "generation": raw.get("generation"),
    }
    if detail is Detail.MINIMAL:
        compact = minimal
        disclosed = 0
    else:
        limit = len(rows) if detail is Detail.DETAILED else max(1, int(max_elements))
        compact = dict(minimal)
        compact["elements"] = rows[:limit]
        disclosed = sum(isinstance(row.get("element_token"), str) for row in rows[:limit])
    raw_chars = len(_serialized(event))
    compact_chars = len(json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    reduction = 0.0 if raw_chars == 0 else ((raw_chars - compact_chars) / raw_chars) * 100.0
    integrity = event.get("ref_integrity") or {}
    input_refs = int(integrity.get("input", 0))
    return {
        "observation": compact,
        "metrics": {
            "raw_chars": raw_chars,
            "compact_chars": compact_chars,
            "raw_estimated_tokens": math.ceil(raw_chars / 4),
            "compact_estimated_tokens": math.ceil(compact_chars / 4),
            "reduction_percent": reduction,
            "native_refs_input": input_refs,
            "native_refs_preserved": int(integrity.get("preserved", 0)),
            "native_refs_disclosed": disclosed,
            "refs_lost": int(integrity.get("lost", 0)),
            "refs_mutated": int(integrity.get("mutated", 0)),
            "ref_sequence_exact": bool(integrity.get("exact_sequence", False)),
            "information_loss_elements": max(0, len(rows) - (len(compact.get("elements") or []))),
        },
    }


class LiveObservationBus:
    def __init__(
        self,
        consumer: Callable[[Any], None],
        *,
        capacity: int = 128,
        metric_capacity: int = 256,
    ) -> None:
        self._consumer = consumer
        self._queue: queue.Queue[tuple[int, Any]] = queue.Queue(maxsize=max(1, int(capacity)))
        self._lock = threading.Lock()
        self._offered = self._enqueued = self._processed = self._dropped = 0
        self._consumer_errors = self._publisher_errors = 0
        sample_limit = max(1, int(metric_capacity))
        self._enqueue: deque[float] = deque(maxlen=sample_limit)
        self._wait: deque[float] = deque(maxlen=sample_limit)
        self._processing: deque[float] = deque(maxlen=sample_limit)
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="walter-observation-bus", daemon=True)
        self._thread.start()

    def publish(self, event: Mapping[str, Any]) -> PublishResult:
        started = time.perf_counter_ns()
        with self._lock:
            self._offered += 1
        try:
            # Boundary builders already return a recursively frozen event.
            # Preserve that object instead of deep-copying the full AX tree a
            # second time on V1's critical path. Third-party mappings still
            # take the defensive copy/freeze route.
            frozen = (
                event
                if isinstance(event, MappingProxyType)
                else _freeze(_plain(event, exclude_pixels=True))
            )
            queued = time.perf_counter_ns()
            self._queue.put_nowait((queued, frozen))
            accepted, dropped, error = True, False, False
            with self._lock:
                self._enqueued += 1
        except queue.Full:
            accepted, dropped, error = False, True, False
            with self._lock:
                self._dropped += 1
        except Exception:
            accepted, dropped, error = False, False, True
            with self._lock:
                self._publisher_errors += 1
        latency = (time.perf_counter_ns() - started) / 1_000_000
        with self._lock:
            self._enqueue.append(latency)
        return PublishResult(accepted, latency, dropped=dropped, error=error)

    def _run(self) -> None:
        while True:
            if self._closed and self._queue.unfinished_tasks == 0:
                return
            try:
                item = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                queued, event = item
                processing_started = time.perf_counter_ns()
                wait_ms = (processing_started - queued) / 1_000_000
                try:
                    self._consumer(event)
                except Exception:
                    with self._lock:
                        self._consumer_errors += 1
                elapsed = (time.perf_counter_ns() - processing_started) / 1_000_000
                with self._lock:
                    self._processed += 1
                    self._wait.append(wait_ms)
                    self._processing.append(elapsed)
            finally:
                self._queue.task_done()

    def flush(self, *, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._queue.all_tasks_done.wait(timeout=remaining)
            return True

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._thread.join(timeout=0.1)

    def metrics(self) -> BusMetrics:
        with self._lock:
            return BusMetrics(
                self._offered,
                self._enqueued,
                self._processed,
                self._dropped,
                self._consumer_errors,
                self._publisher_errors,
                tuple(self._enqueue),
                tuple(self._wait),
                tuple(self._processing),
            )


class ObservationLedger:
    def __init__(self, *, metric_capacity: int = 256) -> None:
        self._lock = threading.Lock()
        self._operations: Counter[str] = Counter()
        self._levels: Counter[str] = Counter()
        self._presence_known: Counter[str] = Counter()
        self._presence_unknown: Counter[str] = Counter()
        self._compactions: deque[dict[str, Any]] = deque(maxlen=max(1, int(metric_capacity)))
        self._native_refs_input = 0
        self._native_refs_preserved = 0
        self._refs_lost = 0
        self._refs_mutated = 0
        self._ref_sequence_failures = 0
        self._refs = NativeRefRegistry()
        self._stale_checked = 0

    def consume(self, event: Mapping[str, Any]) -> None:
        operation = str(event.get("operation") or "unknown")
        compaction = None
        presence = None
        stale_checked = 0
        if operation == "capture":
            started = time.perf_counter_ns()
            compaction = compact_capture(event, detail=Detail.RELEVANT)
            compaction["metrics"]["compaction_latency_ms"] = (
                time.perf_counter_ns() - started
            ) / 1_000_000
            rows = tuple(event.get("elements") or ())
            tokens = tuple(
                str(row.get("element_token"))
                for row in rows
                if isinstance(row, Mapping) and isinstance(row.get("element_token"), str)
            )
            stale_checked = self._refs.observe(tokens)
            presence = event.get("presence") or {}
        level = self._classify(operation)
        with self._lock:
            self._operations[operation] += 1
            self._levels[level] += 1
            if compaction is not None:
                self._compactions.append(compaction["metrics"])
                self._native_refs_input += compaction["metrics"]["native_refs_input"]
                self._native_refs_preserved += compaction["metrics"]["native_refs_preserved"]
                self._refs_lost += compaction["metrics"]["refs_lost"]
                self._refs_mutated += compaction["metrics"]["refs_mutated"]
                self._ref_sequence_failures += int(
                    not compaction["metrics"]["ref_sequence_exact"]
                )
                self._stale_checked += stale_checked
            if presence is not None:
                for key in (
                    "screen_locked",
                    "desktop_unlocked",
                    "foreground_app",
                    "idle_duration",
                    "recent_keyboard_activity",
                    "recent_pointer_activity",
                    "user_active",
                ):
                    (self._presence_unknown if presence.get(key) is None else self._presence_known)[key] += 1

    @staticmethod
    def _classify(operation: str) -> str:
        if operation == "capture" or operation.startswith("list_") or operation in {"wait", "verify_state"}:
            return "L0"
        if operation in {"kill_app"}:
            return "L2"
        if operation in {"click", "drag", "scroll", "type", "type_text", "key", "set_value", "focus_app", "launch_app", "open_url", "bring_to_front"}:
            return "L1"
        return "unknown"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            refs = self._native_refs_input
            return {
                "operations": dict(sorted(self._operations.items())),
                "levels": {level: self._levels.get(level, 0) for level in ("L0", "L1", "L2", "unknown")},
                "compactions": list(self._compactions),
                "native_refs_input": refs,
                "native_refs_preserved": self._native_refs_preserved,
                "refs_lost": self._refs_lost,
                "refs_mutated": self._refs_mutated,
                "ref_sequence_failures": self._ref_sequence_failures,
                "stale_refs_checked": self._stale_checked,
                "presence_known": dict(sorted(self._presence_known.items())),
                "presence_unknown": dict(sorted(self._presence_unknown.items())),
            }


class ObserverRuntime:
    def __init__(
        self,
        *,
        capacity: int = 128,
        metric_capacity: int = 256,
        consumer: Callable[[Any], None] | None = None,
    ) -> None:
        self.ledger = ObservationLedger(metric_capacity=metric_capacity)
        self.bus = LiveObservationBus(
            consumer or self.ledger.consume,
            capacity=capacity,
            metric_capacity=metric_capacity,
        )
        self._sequence = 0
        self._lock = threading.Lock()

    def next_sequence(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    def capture_event(self, capture: Any, *, session_id: str | None, target: Mapping[str, Any]) -> Any:
        return frozen_capture_event(
            capture,
            sequence=self.next_sequence(),
            session_id=session_id,
            target=target,
        )

    def action_event(self, action: Any, *, session_id: str | None) -> Any:
        return frozen_action_event(action, sequence=self.next_sequence(), session_id=session_id)

    def snapshot(self) -> dict[str, Any]:
        return {"bus": asdict(self.bus.metrics()), "ledger": self.ledger.snapshot()}

    def close(self) -> None:
        self.bus.close()


__all__ = [
    "BusMetrics",
    "Detail",
    "LiveObservationBus",
    "NativeRefRegistry",
    "ObservationLedger",
    "ObserverRuntime",
    "PublishResult",
    "_ref_integrity",
    "compact_capture",
    "frozen_action_event",
    "frozen_capture_event",
]
