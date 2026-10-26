"""walter-context-preflight service: the preflight kept warm in one process (127.0.0.1:8897, systemd unit
walter-context-preflight). A one-shot process pays ~0.4 s per message before the decision model is even called
(Python start, imports, the OpenRouter balance check); here they are paid once and the Router answers stay cached.

    POST /preflight            JSON request (same as the CLI's stdin) → 200 ContextPlan, 422 error row
    POST /preflight?shadow=1   plan recorded in the instance (lot 4 shadow), 204
    GET  /health               {"ok": true, "router_cached": bool}

Loopback only, no token: it reads what the caller sends and answers with a plan; it never reads memory or secrets.
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
        if urlparse(self.path).path != "/health":
            return self._send(404, {"error": "not found"})
        self._send(200, {"ok": True, "router_cached": bool(_router().get("chain"))})

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path != "/preflight":
            return self._send(404, {"error": "not found"})
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_BODY:
            return self._send(413, {"error": "request too large"})
        try:
            d = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(d, dict):
                raise ValueError("a JSON object is expected")
        except ValueError as exc:
            return self._send(400, {"error": f"invalid request: {exc}"[:200]})
        shadow = parse_qs(url.query).get("shadow") == ["1"]
        plan, row = handle(d, shadow)
        if shadow:
            return self._send(204, None)
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
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    return 0
