"""One JSON request on stdin, one JSON response on stdout; no persistent service.

Ports provide normalized OpenAI messages; no runtime imports or implicit model
calls are made. Invalid input fails with a nonzero exit and no message content in
the diagnostic. A short subprocess also gives hosts cancellation ownership.
"""
from __future__ import annotations

import json
import sys

from .compress import checkpoint


def dispatch(request: dict) -> dict:
    if request.get("version") != 1:
        raise ValueError("unsupported protocol version")
    if request.get("op") == "capability":
        if request.get("module") not in ("router", "all"):
            raise ValueError("unsupported capability module")
        from .capabilities import compose, router_note
        if request.get("module") == "all":
            return compose(request.get("available_tools"), request.get("form") or "full", request.get("m1"))
        return router_note(request.get("available_tools"))
    messages = request.get("messages")
    if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
        raise ValueError("messages must be a list of objects")
    op = request.get("op")
    if op == "summarize":
        return checkpoint.summarize(messages, model=str(request.get("model") or ""),
                                    budget_tokens=int(request.get("budget_tokens") or 0))
    if op == "window":
        from .compress import window
        plan = request.get("plan")
        live = request.get("live_turn")
        return window.decide(messages, model=str(request.get("model") or ""),
                             budget_tokens=int(request.get("budget_tokens") or 0),
                             measured_tokens=int(request.get("measured_tokens") or 0),
                             now_ms=int(request.get("now_ms") or 0), plan=plan if isinstance(plan, dict) else None,
                             live_turn=int(live) if live is not None else None,
                             checkpoint_tokens=int(request.get("checkpoint_tokens") or 0),
                             force=bool(request.get("force")))
    if op == "plan":
        return checkpoint.plan(messages, model=str(request.get("model") or ""),
                               measured_tokens=int(request.get("measured_tokens") or 0),
                               budget_tokens=int(request.get("budget_tokens") or 0),
                               force=bool(request.get("force")))
    raise ValueError("unsupported operation")


def main() -> int:
    try:
        result = dispatch(json.load(sys.stdin))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"error": "walter-context bridge failed", "type": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
