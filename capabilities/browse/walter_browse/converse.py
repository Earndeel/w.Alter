"""Public client of conversational capabilities (Browse owns recipes and web interactions).

In-process and stdlib only: callers (the Walter Router gateway, tests, runtimes) import this
module instead of launching a process. Recipes live in the Browse registry (ProfileIndex,
``implementation.kind == "conversation"``); see runtime/conversation.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_RUNTIME = str(Path(__file__).resolve().parents[1] / "runtime")


def _runtime():
    if _RUNTIME not in sys.path:
        sys.path.append(_RUNTIME)       # appended: never shadows the caller's own modules
    import conversation
    return conversation


def converse(host: str | None, capability: str, message: str, **options: Any) -> dict[str, Any]:
    """Send ``message`` in a conversation; returns the normalized result (ok, status, reply, conversation,
    request_id, url, mode, recipe_version, transport, timings, error). Never raises for service errors."""
    return _runtime().send(host, capability, message, **options)


def cancel(host: str, capability: str, **options: Any) -> bool:
    return _runtime().cancel(host, capability, **options)


def close(host: str, capability: str, **options: Any) -> bool:
    return _runtime().close(host, capability, **options)
