"""Claude subscription transport; Walter owns every message, tool and model parameter.

LiteLLM translates the caller's OpenAI request and parses Anthropic's actual response.
The official CLI supplies only authenticated transport headers and its billing attribution.
It receives a synthetic, tool-free acknowledgement: real tool calls go only to Walter.
Each invocation owns an authenticated ephemeral loopback bridge and a bounded child process.
No reusable credentials, prompts or responses are logged or stored by this adapter.
"""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import tempfile
import threading
import time

import httpx

PROVIDER = "claude-pro"
GRANT = "claude-subscription"
UPSTREAM = "https://api.anthropic.com/v1/messages"
ATTRIBUTION = re.compile(r"x-anthropic-billing-header: cc_version=[0-9.]+[a-z0-9.-]*; cc_entrypoint=[a-z0-9-]+;\s*")
MAX_REQUEST_BYTES = 16 * 1024 * 1024


class TransportError(RuntimeError):
    """Safe, value-free transport failure."""


def record_usage(config: dict, response) -> None:
    """Metadata-only actual subscription usage; never prompts, outputs or CLI synthetic token counts."""
    usage = getattr(response, "usage", None)
    if not config.get("usage_log") or not usage:
        return
    def value(obj, name):
        return (obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)) or 0
    cached = value(getattr(usage, "prompt_tokens_details", None), "cached_tokens")
    written = value(usage, "cache_creation_input_tokens")
    row = {"at": datetime.now(timezone.utc).isoformat(), "id": response.id, "model": response.model,
           **({"account": config["account"]} if config.get("account") else {}),
           "tokens": {"input": max(0, value(usage, "prompt_tokens") - cached - written), "cache_read": cached,
                      "cache_write": written, "cache_write_1h": 0, "output": value(usage, "completion_tokens")}}
    try:
        path = Path(config["usage_log"])
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(fd, (json.dumps(row) + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        pass  # The vendor's real quota remains authoritative if local telemetry is unavailable.


def owned_payload(payload: dict, native: dict, model: str) -> dict:
    """Allow only native billing attribution; never import CLI messages, tools or settings."""
    if payload.get("model") != model or native.get("model") != model:
        raise TransportError("claude_model_mismatch")
    blocks = [b for b in native.get("system", []) if isinstance(b, dict)
              and str(b.get("text", "")).startswith("x-anthropic-billing-header:")]
    if len(blocks) != 1 or not ATTRIBUTION.fullmatch(blocks[0]["text"]):
        raise TransportError("claude_attribution_changed")
    out = copy.deepcopy(payload)
    system = out.get("system") or []
    if isinstance(system, str):
        system = [{"type": "text", "text": system}]
    if not isinstance(system, list):
        raise TransportError("invalid_system")
    out["system"] = [{"type": "text", "text": blocks[0]["text"]}, *system]
    return out


def acknowledgement(model: str) -> bytes:
    """Terminate the CLI after one transport request, without giving it real model output."""
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_walter_transport", "type": "message", "role": "assistant", "model": model,
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": "OK"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                           "usage": {"output_tokens": 0}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(value)}\n\n" for name, value in events).encode()


class _Server(ThreadingHTTPServer):
    daemon_threads = True


class NativeBridge:
    """One request and one official CLI child; no persistent server or native agent loop."""

    def __init__(self, config: dict, model: str, access_token: str, timeout: float):
        self.config, self.model, self.access_token = config, model, access_token
        self.timeout = max(0.1, float(timeout))
        self.deadline = time.monotonic() + self.timeout
        self.local_token = "sk-ant-oat01-walter-local-" + secrets.token_urlsafe(32)
        self.done, self.closed = threading.Event(), threading.Event()
        self.close_lock = threading.Lock()
        self.claim = threading.Lock()
        self.native_claim = threading.Lock()
        self.request_claimed = self.native_claimed = False
        self.payload = self.caller = self.process = self.response = None
        self.sent_headers = False
        self.error = None
        self.temp = None
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(min(10, bridge.timeout))

            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_error(404)

            def do_POST(self):
                path = self.path.split("?", 1)[0]
                native = path == "/native/v1/messages"
                if path not in {"/walter/v1/messages", "/native/v1/messages"}:
                    self.send_error(404)
                    return
                expected = bridge.access_token if native else bridge.local_token
                supplied = self.headers.get("authorization", "").removeprefix("Bearer ")
                if not hmac.compare_digest(supplied, expected):
                    self.send_error(401)
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= MAX_REQUEST_BYTES:
                        raise TransportError("invalid_request_size")
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict):
                        raise TransportError("invalid_request")
                    if native:
                        bridge.forward(self, payload)
                    else:
                        bridge.receive(self, payload)
                except Exception as exc:
                    bridge.error = type(exc).__name__
                    if not bridge.sent_headers and bridge.caller:
                        bridge.fail(502, "claude_transport_failed")
                    elif bridge.caller is None:
                        self.send_error(400)
                    bridge.done.set()

        self.server = _Server(("127.0.0.1", 0), Handler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)

    @property
    def api_base(self) -> str:
        return f"http://127.0.0.1:{self.port}/walter"

    def start(self):
        self.thread.start()
        return self

    def fail(self, status: int, message: str):
        if self.sent_headers or not self.caller:
            return
        content = json.dumps({"type": "error", "error": {"type": "api_error", "message": message}}).encode()
        self.caller.send_response(status)
        self.caller.send_header("content-type", "application/json")
        self.caller.send_header("content-length", str(len(content)))
        self.caller.end_headers()
        self.sent_headers = True
        self.caller.wfile.write(content)

    def expire(self):
        """Deadline or close before the answer ended. Once headers are sent no error body can follow, so the stream
        must carry the failure: a cut answer is never a success (2026-11-07: Opus answers cut at 60 s were logged ok
        with 2 output tokens and the agent retried the same request in a loop)."""
        if not self.closed.is_set():
            self.error = self.error or "claude_transport_timeout"
        self.fail(504, "claude_transport_timeout")
        self.done.set()

    def receive(self, handler, payload):
        with self.claim:
            if self.request_claimed:
                handler.send_error(409)
                return
            self.request_claimed = True
        if payload.get("model") != self.model:
            handler.send_error(400)
            return
        self.caller, self.payload = handler, payload
        state = Path(self.config["state_dir"])
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.temp = tempfile.TemporaryDirectory(prefix="call-", dir=state)
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "TMPDIR"}}
        env.update(CLAUDE_CODE_OAUTH_TOKEN=self.access_token, CLAUDE_CONFIG_DIR=self.temp.name,
                   ANTHROPIC_BASE_URL=f"http://127.0.0.1:{self.port}/native",
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", DISABLE_AUTOUPDATER="1",
                   CLAUDE_CODE_MAX_RETRIES="0", API_TIMEOUT_MS=str(int(self.timeout * 1000)))
        command = [self.config["cli"], "-p", "Return OK.", "--model", self.model,
                   "--tools", "", "--system-prompt", "Transport acknowledgement only.",
                   "--max-turns", "1", "--no-session-persistence", "--setting-sources", "",
                   "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                   "--disable-slash-commands", "--settings", '{"disableAllHooks":true}',
                   "--output-format", "json"]
        self.process = subprocess.Popen(command, env=env, cwd=self.temp.name,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, start_new_session=True)
        while not self.done.wait(0.05):
            if self.closed.is_set() or time.monotonic() >= self.deadline:
                self.expire()
                break
            if self.process.poll() is not None and not self.native_claimed:
                self.fail(502, "claude_native_start_failed")
                self.done.set()
                break

    def forward(self, native_handler, native):
        with self.native_claim:
            if self.native_claimed or self.payload is None:
                native_handler.send_error(409)
                return
            self.native_claimed = True
        outgoing = owned_payload(self.payload, native, self.model)
        # Keep only legitimate CLI protocol headers. Never forward proxy/host/cookie/account headers.
        allowed = {"user-agent", "anthropic-version", "anthropic-beta", "x-app",
                   "anthropic-dangerous-direct-browser-access"}
        headers = {k: v for k, v in native_handler.headers.items() if k.lower() in allowed}
        headers.update(authorization="Bearer " + self.access_token, **{"content-type": "application/json"})
        remaining = max(0.1, self.deadline - time.monotonic())
        try:
            with httpx.Client(timeout=remaining, trust_env=False) as client:
                with client.stream("POST", UPSTREAM, headers=headers, json=outgoing) as response:
                    self.response = response
                    self.caller.send_response(response.status_code)
                    self.caller.send_header("content-type", response.headers.get("content-type", "application/json"))
                    for name in ("request-id", "retry-after"):
                        if response.headers.get(name):
                            self.caller.send_header(name, response.headers[name])
                    self.caller.send_header("connection", "close")
                    self.caller.end_headers()
                    self.sent_headers = True
                    for chunk in response.iter_bytes():
                        if self.closed.is_set() or time.monotonic() >= self.deadline:
                            raise TransportError("claude_transport_timeout")
                        self.caller.wfile.write(chunk)
                        self.caller.wfile.flush()
                    self.caller.close_connection = True
            # The CLI never sees the model's real answer or tool calls.
            ack = acknowledgement(self.model)
            native_handler.send_response(200)
            native_handler.send_header("content-type", "text/event-stream")
            native_handler.send_header("content-length", str(len(ack)))
            native_handler.end_headers()
            native_handler.wfile.write(ack)
        finally:
            self.done.set()

    def close(self):
        with self.close_lock:
            if self.closed.is_set():
                return
            self.closed.set()
        if self.response is not None:
            try:
                self.response.close()
            except Exception:
                pass  # Still stop the child and listener if a remote socket cannot close cleanly.
        if self.process is not None and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=1)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=1)
                except ProcessLookupError:
                    pass
        self.done.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        if self.temp:
            self.temp.cleanup()


async def completion(config: dict, access_token: str, **kwargs):
    """OpenAI completion, including real streaming/tool calls, over native subscription transport."""
    model = kwargs.pop("model")
    if not re.fullmatch(r"claude-[a-z0-9-]+", model):
        raise TransportError("invalid_claude_model")
    if model not in config.get("verified_models", []):
        raise TransportError("unverified_claude_model")
    import litellm   # only once the model is allowed: a refusal needs no transport library
    timeout = kwargs.pop("timeout", 60)
    timeout = float(timeout) if isinstance(timeout, (int, float)) else 60
    if kwargs.get("stream"):
        kwargs.setdefault("stream_options", {"include_usage": True})
    bridge = NativeBridge(config, model, access_token, timeout).start()
    streaming = bool(kwargs.get("stream"))
    try:
        kwargs.update(model="anthropic/" + model, api_base=bridge.api_base, api_key=bridge.local_token,
                      num_retries=0, fallbacks=[], timeout=timeout)
        response = await litellm.acompletion(**kwargs)
        if not streaming:
            if response.model != model:
                raise TransportError("claude_response_model_mismatch")
            record_usage(config, response)
            return response
    except BaseException:
        await asyncio.shield(asyncio.to_thread(bridge.close))
        raise
    finally:
        if not streaming:
            await asyncio.shield(asyncio.to_thread(bridge.close))

    return BridgeStream(response, bridge, config, model)


class BridgeStream:
    """Closable even before its first token; client cancellation must not leave a native child."""

    def __init__(self, response, bridge, config, model):
        self.response, self.iterator, self.bridge = response, response.__aiter__(), bridge
        self.config, self.model, self.last, self.closed = config, model, None, False
        self.finished = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.closed:
            raise StopAsyncIteration
        try:
            chunk = await self.iterator.__anext__()
            if getattr(chunk, "model", None) and chunk.model != self.model:
                raise TransportError("claude_response_model_mismatch")
            if getattr(chunk, "usage", None):
                self.last = chunk
            if any(getattr(choice, "finish_reason", None) is not None for choice in chunk.choices):
                self.finished = True
            return chunk
        except StopAsyncIteration:
            try:
                if self.bridge.error:
                    raise TransportError("claude_stream_interrupted")
                if not self.finished:
                    raise TransportError("claude_stream_incomplete")
                if self.last is not None:
                    record_usage(self.config, self.last)
            finally:
                await self.aclose()
            raise
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self):
        if self.closed:
            return
        self.closed = True
        try:
            close = getattr(self.response, "aclose", None)
            if close:
                await close()
        finally:
            await asyncio.shield(asyncio.to_thread(self.bridge.close))
