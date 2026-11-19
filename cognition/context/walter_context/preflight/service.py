"""walter-context-preflight service: the preflight kept warm in one process (127.0.0.1:8897, systemd unit
walter-context-preflight). A one-shot process pays ~0.4 s per message before the decision model is even called
(Python start, imports, the OpenRouter balance check); here they are paid once and the Router answers stay cached.

    POST /preflight            JSON request (same as the CLI's stdin) → 200 ContextPlan, 422 error row
    POST /preflight?shadow=1   plan recorded in the instance (lot 4 shadow), 204
    POST /preflight?inject=1   {plan, text (the pack to inject), pack (its summary), degraded}, recorded too; production
                               path of the engine's native intake. degraded = the decision failed and the plan is the
                               prudent default (SOCLE A2): the engine records it on its run
    GET  /health               {"ok": true, "router_cached": bool}

Living state (2026-11-17, walter_context.state / reassess; same loopback-only, no-token scheme):
    POST /v1/state/event       {session_id, thread_id?, run_id?, kind, at?, payload} → {"ok": true, "version": n}; queued
                               and applied in batches (answers in well under 20 ms); 400 unknown kind / bad body
    GET  /v1/state?session_id=…[&thread_id=…]   {version, updated_at, state, text}: `text` = French block ≤ 2500 chars
    POST /v1/reassess          {session_id, run_id?, trigger: {kind, …}, facts?} → {asked, reason, decision_state,
                               decisions, text}: a targeted decision on the new state, memoised, never a full preflight

Loopback only, no token. Since step D (26/10) it reads Walter Memory's subject views (candidates, cards) and, in
shadow mode, assembles the context pack the plan asks for (views, cloud-safe memory context, recent exchanges) and
records it in the instance; it never reads secrets and returns only a plan.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import _router
from .__main__ import handle

HOST = "127.0.0.1"
PORT = int(os.environ.get("WALTER_CONTEXT_PREFLIGHT_PORT") or 8897)
MAX_BODY = 256 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "walter-context-preflight"

    def _send(self, code: int, body: dict | None) -> None:
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
        self.send_response(code)
        if data:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/v1/state":
            return self._get_state(parse_qs(url.query))
        if url.path != "/health":
            return self._send(404, {"error": "not found"})
        self._send(200, {"ok": True, "router_cached": bool(_router().get("chain"))})

    def _get_state(self, q: dict) -> None:
        from ..state import manager, render
        sid = (q.get("session_id") or [""])[0]
        if not sid:
            return self._send(400, {"error": "session_id is required"})
        try:
            st = manager().get(sid, (q.get("thread_id") or [None])[0])
            self._send(200, {"version": st["version"], "updated_at": st["updated_at"], "state": st, "text": render(st)})
        except Exception as exc:  # noqa: BLE001 — a state read never takes the service down
            self._send(500, {"error": f"{type(exc).__name__}: {str(exc)[:160]}"})

    def _body(self) -> dict | None:
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_BODY:
            self._send(413, {"error": "request too large"})
            return None
        try:
            d = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(d, dict):
                raise ValueError("a JSON object is expected")
            return d
        except ValueError as exc:
            self._send(400, {"error": f"invalid request: {exc}"[:200]})
            return None

    def _post_state(self, path: str) -> None:
        d = self._body()
        if d is None:
            return
        from ..state import UnknownEvent, manager
        try:
            if path == "/v1/state/event":
                ev = {k: d[k] for k in ("session_id", "thread_id", "run_id", "kind", "at", "payload") if k in d}
                return self._send(200, {"ok": True, "version": manager().submit(ev)})
            from ..reassess import reassess
            self._send(200, reassess(d))
        except (UnknownEvent, ValueError) as exc:
            self._send(400, {"error": str(exc)[:200]})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": f"{type(exc).__name__}: {str(exc)[:160]}"})

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path in ("/v1/state/event", "/v1/reassess"):
            return self._post_state(url.path)
        if url.path != "/preflight":
            return self._send(404, {"error": "not found"})
        d = self._body()
        if d is None:
            return
        shadow = parse_qs(url.query).get("shadow") == ["1"]
        inject = parse_qs(url.query).get("inject") == ["1"]      # real injection trials (owner, 2026-10-27/28)
        plan, row = handle(d, shadow, want_pack=inject)
        if shadow:
            return self._send(204, None)
        if inject:
            return self._send(200, {"plan": plan, "text": row.get("pack_text"), "pack": row.get("pack"),
                                    "degraded": bool(row.get("degraded")), "error": row.get("error")})
        self._send(200, plan) if plan is not None else self._send(422, row)

    def log_message(self, *args) -> None:       # message text never reaches the journal
        pass


def serve() -> int:
    _router()                                   # Router answers loaded (or fetched) before the first message
    try:
        from walter_memory import llm
        llm.account_balance()                   # warm the 5-minute balance cache and the imports
    except Exception:  # noqa: BLE001 — checked again on the first call
        pass
    import signal
    import threading

    def _stop(*_):                              # queued state events are applied before the process leaves
        try:
            from ..state import manager
            manager().flush()
        finally:
            os._exit(0)
    signal.signal(signal.SIGTERM, _stop)
    threading.Thread(target=_warm, name="preflight-warm", daemon=True).start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    return 0


def _warm() -> None:
    """One plan and one pack at start, so the first owner message does not pay for what a fresh process loads
    (embeddings, Memory views, retrieval, connections): measured 7.0 s cold against 1.5 s warm on 12/11/2026, the
    host's whole preflight budget — the first turn after every restart was answered on a degraded context.
    Nothing is recorded or signalled; a failure here changes nothing (the first message pays, as before)."""
    try:
        handle({"message": "Démarrage du service : où en sont les sujets en cours et que reste-t-il à faire ?",
                "runtime": "warmup", "privacy_class": "cloud_allowed"}, shadow=False, want_pack=True, warm=True)
    except Exception:  # noqa: BLE001
        pass
    try:                                    # the situation digest's projections (a cold big project: ~1 s, warm ~60 ms)
        from . import DIGEST
        if DIGEST["enabled"]:
            from walter_memory import digest
            digest.warm()
    except Exception:  # noqa: BLE001
        pass
