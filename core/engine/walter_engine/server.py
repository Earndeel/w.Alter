"""Walter Engine — its two HTTP faces (2026-11-17).

  Engine API (loopback, agent token): POST /v1, GET /v1/health, GET /v1/events (SSE) — engine-api.v1, unchanged.
  Web interface (tailnet + portal through walter-web-gate): the native UI (ui/), the same API as the owner behind a
  browser sign-in, the instance's panels (devboard) relayed read-only (+ declared actions), deliverables.

Web sign-in, as before the switch (the gate and the browsers keep working): a launch token per process, written to a
root-only file (`login_url_file`), never logged; `GET /?token=<it>` mints a signed cookie bound to the request's
authority (HMAC-SHA256 with a persistent 32-byte secret, 0600), valid `web_cookie_days`; every other request without
a valid cookie gets 401. A Host fence (loopback or `trusted_hosts`) and a same-origin check on Origin stop DNS
rebinding and cross-site requests.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

from . import config
from .api import ApiError, EngineApi, ensure_token, same

log = logging.getLogger("walter_engine.server")
UI = Path(__file__).parent / "ui"
MAX_BODY = 1 << 20
COOKIE_PREFIXES = ("walter-auth-", "dsh-auth-")     # dsh-auth-: cookies minted before the switch (same secret)
WEB_OPS = {"health", "session.open", "session.list", "turn.submit", "turn.queue", "turn.steer", "turn.result",
           "turn.cancel", "approval.list", "approval.answer", "session.history", "session.rename"}
OWNER = {"kind": "owner", "id": "owner"}


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]*", s or "") or len(s) % 4 == 1:
        return None
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except ValueError:
        return None


async def _json(request: Request) -> dict:
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY:
            raise ApiError(413, "too_large")
    try:
        return json.loads(body or b"{}")
    except ValueError:
        raise ApiError(400, "invalid_json") from None


def _sse(it, stop: asyncio.Event):
    async def gen():
        yield b": walter engine events\n\n"
        nxt = None
        try:
            while True:
                nxt = asyncio.ensure_future(it.__anext__())
                done, _ = await asyncio.wait({nxt}, timeout=15)
                if not done:
                    yield b": ping\n\n"
                    while not nxt.done():
                        done, _ = await asyncio.wait({nxt}, timeout=15)
                        if not done:
                            yield b": ping\n\n"
                try:
                    e = nxt.result()
                except StopAsyncIteration:
                    return
                yield f"event: {e['type']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n".encode()
        finally:
            stop.set()
            if nxt is not None and not nxt.done():
                nxt.cancel()
            with contextlib.suppress(Exception):
                await it.aclose()
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# ── Engine API ──
def api_app(api: EngineApi, token: str) -> Starlette:
    def err(e: Exception) -> JSONResponse:
        if isinstance(e, ApiError):
            return JSONResponse({"error": e.code, "detail": str(e.detail)[:300]}, e.status, headers={"Cache-Control": "no-store"})
        log.exception("api: %s", e)
        return JSONResponse({"error": "internal", "detail": str(e)[:300]}, 500)

    def authorised(request: Request) -> bool:
        auth = request.headers.get("authorization") or ""
        return auth.startswith("Bearer ") and same(auth[7:].strip(), token)

    async def health(request: Request):
        if not authorised(request):
            return err(ApiError(401, "unauthorised"))
        return JSONResponse(api.health(), headers={"Cache-Control": "no-store"})

    async def op(request: Request):
        try:
            if not authorised(request):
                raise ApiError(401, "unauthorised")
            body = await _json(request)
            if body.get("op") in ("session.history", "session.rename"):
                raise ApiError(400, "unknown_op")          # web-only additions
            return JSONResponse(await api.op(body), headers={"Cache-Control": "no-store"})
        except Exception as e:  # noqa: BLE001
            return err(e)

    async def events(request: Request):
        try:
            if not authorised(request):
                raise ApiError(401, "unauthorised")
            sid = request.query_params.get("session_id")
            api.row(sid)
            since = request.query_params.get("since_seq")
            stop = asyncio.Event()
            progress = request.query_params.get("progress") in ("1", "true")
            return _sse(api.events(sid, None if since is None else int(since), stop, progress=progress), stop)
        except Exception as e:  # noqa: BLE001
            return err(e)

    async def not_found(request: Request):
        return err(ApiError(404, "not_found"))

    return Starlette(routes=[Route("/v1/health", health, methods=["GET"]), Route("/v1", op, methods=["POST"]),
                             Route("/v1/events", events, methods=["GET"]),
                             Route("/{path:path}", not_found, methods=["GET", "POST", "PUT", "DELETE", "HEAD"])])


# ── web ──
class WebAuth:
    def __init__(self, settings: config.Settings):
        self.s = settings
        d = settings.state / "web"
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        f = d / "cookie.secret"
        try:
            secret = _unb64(f.read_text().strip())
        except FileNotFoundError:
            secret = None
        if not secret or len(secret) != 32:
            secret = secrets.token_bytes(32)
            fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(_b64(secret) + "\n")
        self.secret = secret
        self.launch = _b64(secrets.token_bytes(32))
        self.max_age_ms = int(settings.web_cookie_days) * 86_400_000
        trusted = []
        for h in settings.trusted_hosts or []:
            u = urlsplit(f"http://{h}")
            trusted.append((u.hostname.lower(), u.port))
        self.trusted = trusted

    def write_login_url(self) -> None:
        f = self.s.login_url_file
        f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = f.with_name(f.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(f"http://127.0.0.1:{self.s.web_port}/?token={self.launch}\n")
        os.replace(tmp, f)
        log.info("web sign-in link written to %s", f)

    @staticmethod
    def authority(request: Request) -> str | None:
        host = request.headers.get("host")
        if not host:
            return None
        try:
            u = urlsplit(f"http://{host}")
            if not u.hostname:
                return None
            port = u.port
            h = u.hostname.lower()
            h = f"[{h}]" if ":" in h else h
            return f"{h}:{port}" if port and port != 80 else h
        except ValueError:
            return None

    def fenced(self, request: Request) -> bool:
        """Host is ours (loopback or trusted) and any Origin is same-origin."""
        auth = self.authority(request)
        if not auth:
            return False
        u = urlsplit(f"http://{auth}")
        h, p = (u.hostname or "").lower(), u.port
        loop = h in ("localhost", "127.0.0.1", "::1") or h.startswith("127.")
        if not loop and not any(h == th and (tp is None or tp == p) for th, tp in self.trusted):
            return False
        origin = request.headers.get("origin")
        if origin is None:
            return True
        try:
            return urlsplit(origin).netloc.lower() == auth
        except ValueError:
            return False

    def _sig(self, body: str) -> bytes:
        return hmac.new(self.secret, body.encode(), hashlib.sha256).digest()

    def cookie_name(self, authority: str, prefix: str = COOKIE_PREFIXES[0]) -> str:
        return prefix + _b64(hashlib.sha256(authority.encode()).digest())

    def mint(self, authority: str) -> str:
        now = int(time.time() * 1000)
        exp = now + self.max_age_ms
        body = _b64(json.dumps({"version": 1, "authority": authority, "issuedAt": now, "expiresAt": exp},
                               separators=(",", ":")).encode())
        value = f"v1.{body}.{_b64(self._sig(body))}"
        return (f"{self.cookie_name(authority)}={value}; Max-Age={self.max_age_ms // 1000}; Path=/; "
                f"Expires={time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(exp / 1000))}; HttpOnly; SameSite=Strict")

    def authenticated(self, request: Request) -> bool:
        auth = self.authority(request)
        raw = request.headers.get("cookie")
        if not auth or not raw:
            return False
        for prefix in COOKIE_PREFIXES:
            name = self.cookie_name(auth, prefix)
            for seg in raw.split(";"):
                k, _, v = seg.partition("=")
                if k.strip() != name:
                    continue
                parts = v.strip().split(".")
                if len(parts) != 3 or parts[0] != "v1":
                    continue
                sig = _unb64(parts[2])
                if sig is None or not hmac.compare_digest(sig, self._sig(parts[1])):
                    continue
                try:
                    p = json.loads(_unb64(parts[1]) or b"")
                except ValueError:
                    continue
                now = int(time.time() * 1000)
                if (isinstance(p, dict) and p.get("version") == 1 and p.get("authority") == auth
                        and isinstance(p.get("issuedAt"), int) and isinstance(p.get("expiresAt"), int)
                        and p["issuedAt"] <= now < p["expiresAt"] and p["expiresAt"] - p["issuedAt"] <= self.max_age_ms):
                    return True
        return False


def _unauth(request: Request) -> Response:
    return PlainTextResponse("" if request.method == "HEAD" else "walter web: authentication required; reopen the sign-in link.\n",
                             401, headers={"Cache-Control": "no-store"})


def web_app(api: EngineApi, engine, settings: config.Settings, auth: WebAuth) -> Starlette:
    panels = [p for p in settings.panels if isinstance(p, dict) and p.get("id") and p.get("path") and p.get("upstream")]
    proxy = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=3.0))

    def werr(e: Exception) -> JSONResponse:
        if isinstance(e, ApiError):
            return JSONResponse({"error": {"code": e.code, "message": str(e.detail)[:300]}}, e.status,
                                headers={"Cache-Control": "no-store"})
        log.exception("web: %s", e)
        return JSONResponse({"error": {"code": "internal", "message": "erreur interne"}}, 500)

    def gate(request: Request) -> Response | None:
        if not auth.fenced(request):
            return PlainTextResponse("forbidden", 403)
        if not auth.authenticated(request):
            return _unauth(request)
        return None

    async def index(request: Request):
        if not auth.fenced(request):
            return PlainTextResponse("forbidden", 403)
        tokens = request.query_params.getlist("token")
        if tokens:
            a = auth.authority(request)
            if request.method == "GET" and len(tokens) == 1 and a and same(tokens[0], auth.launch):
                return Response(status_code=303, headers={"Location": "./", "Cache-Control": "no-store",
                                                          "Referrer-Policy": "no-referrer", "Set-Cookie": auth.mint(a)})
            if request.method == "GET" and auth.authenticated(request):
                return Response(status_code=303, headers={"Location": "./", "Cache-Control": "no-store",
                                                          "Referrer-Policy": "no-referrer"})
            return _unauth(request)
        if not auth.authenticated(request):
            return _unauth(request)
        return FileResponse(UI / "index.html", headers={"Cache-Control": "no-store"})

    async def asset(request: Request):
        g = gate(request)
        if g:
            return g
        name = request.path_params["name"]
        p = (UI / name).resolve()
        if p.parent != UI.resolve() or not p.is_file():
            return PlainTextResponse("not found", 404)
        return FileResponse(p, headers={"Cache-Control": "no-cache"})

    async def ui_config(request: Request):
        g = gate(request)
        if g:
            return g
        return JSONResponse({"name": settings.web_name, "tagline": settings.web_tagline,
                             "panels": [{"id": p["id"], "label": p.get("label") or p["id"], "path": p["path"]} for p in panels],
                             "links": [{k: v for k, v in link.items() if k in ("id", "label", "description", "url", "section",
                                                                                 "section_label")} for link in settings.links]},
                            headers={"Cache-Control": "no-store"})

    async def v1(request: Request):
        g = gate(request)
        if g:
            return werr(ApiError(g.status_code, "unauthorised" if g.status_code == 401 else "forbidden"))
        try:
            body = await _json(request)
            body["version"] = 1
            if body.get("op") not in WEB_OPS:
                raise ApiError(400, "unknown_op")
            if body["op"] == "session.open":
                body = {**body, "interface": "web", "principal": OWNER, "mode": "interactive"}
                body.pop("permissions", None)
            if body["op"] == "approval.answer":
                body["principal"] = OWNER
            return JSONResponse(await api.op(body, web=True), headers={"Cache-Control": "no-store"})
        except Exception as e:  # noqa: BLE001
            return werr(e)

    async def events(request: Request):
        g = gate(request)
        if g:
            return g
        try:
            sid = request.query_params.get("session_id")
            api.row(sid)
            since = request.query_params.get("since_seq")
            stop = asyncio.Event()
            return _sse(api.events(sid, None if since in (None, "") else int(since), stop, rich=True), stop)
        except Exception as e:  # noqa: BLE001
            return werr(e)

    async def files(request: Request):
        g = gate(request)
        if g:
            return g
        row = engine.deliverables.get(request.path_params["token"])
        if not row or Path(row["path"]).name != request.path_params["name"] or not Path(row["path"]).is_file():
            return PlainTextResponse("not found", 404)
        mime = mimetypes.guess_type(row["path"])[0] or "application/octet-stream"
        return FileResponse(row["path"], media_type=mime, headers={"Cache-Control": "no-store",
                                                                   "Content-Disposition": f'inline; filename="{Path(row["path"]).name}"'})

    def panel_route(p: dict):
        base = p["upstream"].rstrip("/")
        actions = [a for a in p.get("actions") or [] if isinstance(a, str) and a.startswith("/") and ".." not in a]

        async def relay(request: Request):
            path = request.url.path
            if path == p["path"]:
                q = f"?{request.url.query}" if request.url.query else ""
                return Response(status_code=308, headers={"Location": f"{p['path']}/{q}"})
            g = gate(request)
            if g:
                return g
            rest = path[len(p["path"]):]
            action = request.method == "POST" and any(rest.startswith(a) for a in actions) and ".." not in rest
            if request.method not in ("GET", "HEAD") and not action:
                return PlainTextResponse("read only", 405, headers={"Allow": "GET, HEAD"})
            body = None
            if action:
                try:
                    n = int(request.headers.get("content-length") or "")
                except ValueError:
                    n = -1
                if not 0 <= n <= 65536:
                    return PlainTextResponse("action body too large or without length", 413)
                body = await request.body()
            drop = {"connection", "keep-alive", "proxy-connection", "transfer-encoding", "upgrade", "te", "trailer",
                    "cookie", "authorization", "host", "content-length"}
            headers = {k: v for k, v in request.headers.items() if k.lower() not in drop}
            headers["x-forwarded-prefix"] = p["path"]
            url = base + rest + (f"?{request.url.query}" if request.url.query else "")
            try:
                up = await proxy.request(request.method, url, headers=headers, content=body)
            except httpx.HTTPError:
                return PlainTextResponse("panel unavailable", 502)
            out = {k: v for k, v in up.headers.items() if k.lower() not in ("connection", "keep-alive", "transfer-encoding",
                                                                            "set-cookie", "content-length", "content-encoding")}
            return Response(up.content, up.status_code, headers=out)
        return relay

    routes = [Route("/", index, methods=["GET", "HEAD"]), Route("/ui/config", ui_config, methods=["GET"]),
              Route("/ui/{name}", asset, methods=["GET", "HEAD"]), Route("/favicon.svg", asset, methods=["GET"]),
              Route("/v1", v1, methods=["POST"]), Route("/v1/events", events, methods=["GET"]),
              Route("/files/{token}/{name}", files, methods=["GET", "HEAD"])]
    for p in panels:
        h = panel_route(p)
        routes += [Route(p["path"], h, methods=["GET", "HEAD", "POST"]),
                   Route(p["path"] + "/{rest:path}", h, methods=["GET", "HEAD", "POST"])]

    async def fallback(request: Request):
        g = gate(request)
        return g or PlainTextResponse("not found", 404)
    routes.append(Route("/{path:path}", fallback, methods=["GET", "HEAD", "POST"]))
    app = Starlette(routes=routes)
    app.state.proxy = proxy
    return app


class Quiet(uvicorn.Server):
    """A server whose signals the engine handles (two servers, one process, one orderly stop)."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


def serve_config(app, host: str, port: int) -> uvicorn.Config:
    return uvicorn.Config(app, host=host, port=port, log_level="warning", lifespan="off", server_header=False,
                          date_header=False, proxy_headers=False, timeout_graceful_shutdown=3, access_log=False)


def build(engine, settings: config.Settings) -> tuple[EngineApi, list[Quiet], WebAuth]:
    api = EngineApi(engine, settings)
    token = ensure_token(settings.api_token_file)
    if settings.api_host not in ("127.0.0.1", "::1", "localhost"):
        raise RuntimeError("walter engine api: loopback only")
    auth = WebAuth(settings)
    servers = [Quiet(serve_config(api_app(api, token), settings.api_host, settings.api_port)),
               Quiet(serve_config(web_app(api, engine, settings, auth), settings.web_host, settings.web_port))]
    return api, servers, auth
