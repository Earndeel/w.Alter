"""Walter Engine — model calls through walter-llm (2026-11-17).

The engine never talks to a provider: every call goes to walter-llm (:8894, OpenAI-compatible), which owns the
choice of model (Walter Router poste / the run's plan), fallbacks, costs, privacy and budgets. The engine sends the
open run of the turn (`X-Walter-Run-Id`: walter-llm refuses a call without an open, cloud-allowed run) under its own
agent token (`engine`, a local token in the instance bootstrap), streams the answer and assembles text, reasoning
and tool calls. A transport failure or a 429/5xx before the first token is retried (bounded); after the first token
the call is not replayed (the journal would show a half answer twice).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from . import config

log = logging.getLogger("walter_engine.llm")


class LLMError(RuntimeError):
    def __init__(self, code: str, status: int | None = None, detail: str = ""):
        super().__init__(f"{code}{f' ({status})' if status else ''}{': ' + detail if detail else ''}")
        self.code, self.status, self.detail = code, status, detail


@dataclass
class Answer:
    text: str = ""
    reasoning: str = ""
    tool_calls: list = field(default_factory=list)      # [{id, name, arguments}]
    finish: str | None = None
    usage: dict = field(default_factory=dict)
    model: str | None = None
    route: str | None = None
    first_token_ms: int | None = None
    total_ms: int | None = None


class Client:
    def __init__(self, settings: config.Settings):
        self.s = settings
        self._token: str | None = None
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=5.0, read=300.0))

    def token(self) -> str:
        if self._token is None:
            tok = config.env_value(self.s.llm_env_file, "WALTER_LLM_TOKEN")
            if not tok:
                raise LLMError("no_engine_token", detail=str(self.s.llm_env_file))
            self._token = tok
        return self._token

    async def close(self) -> None:
        await self.http.aclose()

    async def postes(self) -> set[str] | None:
        """The Router postes the gateway serves (`/v1/models`), cached 10 min; None when it cannot say (never blocks a
        call: the gateway stays the judge). Lot 3e: a sub-agent asked on an invented poste failed after ~9 s."""
        hit = getattr(self, "_postes", None)
        if hit and time.monotonic() - hit[0] < 600:
            return hit[1]
        try:
            r = await self.http.get(f"{config.LLM_URL}/v1/models", headers={"Authorization": f"Bearer {self.token()}"},
                                    timeout=5.0)
            names = {str(m.get("id")) for m in (r.json().get("data") or [])} if r.status_code == 200 else None
        except Exception:  # noqa: BLE001
            names = None
        if names:
            self._postes = (time.monotonic(), names)
        return names

    async def chat(self, *, messages: list[dict], tools: list[dict] | None, model: str, run_id: str | None,
                   task_id: str | None = None, on_delta=None, max_tokens: int | None = None,
                   cancel: asyncio.Event | None = None, extra: dict | None = None) -> Answer:
        body: dict = {"model": model, "messages": messages, "stream": True, "stream_options": {"include_usage": True}}
        if extra:                                  # e.g. reasoning_effort for a sub-agent: walter-llm maps it per provider
            body.update({k: v for k, v in extra.items() if k not in ("model", "messages", "stream", "tools")})
        if tools:
            body["tools"] = tools
            body["parallel_tool_calls"] = True
        if max_tokens:
            body["max_tokens"] = max_tokens
        headers = {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"}
        if run_id:
            headers["X-Walter-Run-Id"] = run_id
        if task_id:
            headers["X-Walter-Task-Id"] = task_id
        attempt = 0
        while True:
            attempt += 1
            started = False
            try:
                return await self._stream(body, headers, on_delta, cancel, lambda: started)
            except _Started as s:
                raise s.error from None
            except LLMError as e:
                retry = e.code in ("transport",) or (e.status in (429, 500, 502, 503, 504))
                if not retry or attempt >= 3:
                    raise
                await asyncio.sleep(1.5 * attempt)

    async def _stream(self, body, headers, on_delta, cancel, _started) -> Answer:
        t0 = time.monotonic()
        ans = Answer()
        calls: dict[int, dict] = {}
        got_any = False
        try:
            async with self.http.stream("POST", f"{config.LLM_URL}/v1/chat/completions", json=body, headers=headers) as r:
                ans.route = r.headers.get("X-Walter-Route")
                if r.status_code != 200:
                    raw = (await r.aread())[:600].decode("utf-8", "replace")
                    try:
                        detail = str(json.loads(raw).get("detail") or "")[:200]
                    except ValueError:
                        detail = ""
                    raise LLMError("http", r.status_code, detail)
                async for line in r.aiter_lines():
                    if cancel is not None and cancel.is_set():
                        raise asyncio.CancelledError()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    if chunk.get("error"):
                        err = chunk["error"]
                        detail = str(err.get("message") if isinstance(err, dict) else err)[:200]
                        if got_any:
                            raise _Started(LLMError("stream_error", None, detail))
                        raise LLMError("stream_error", None, detail)
                    if chunk.get("model"):
                        ans.model = chunk["model"]
                    if chunk.get("usage"):
                        ans.usage = chunk["usage"]
                    for ch in chunk.get("choices") or []:
                        delta = ch.get("delta") or ch.get("message") or {}
                        txt = delta.get("content")
                        if txt:
                            if ans.first_token_ms is None:
                                ans.first_token_ms = int((time.monotonic() - t0) * 1000)
                            got_any = True
                            ans.text += txt
                            if on_delta is not None:
                                try:
                                    on_delta(txt)
                                except Exception:  # noqa: BLE001
                                    pass
                        rs = delta.get("reasoning_content") or delta.get("reasoning")
                        if isinstance(rs, str) and rs:
                            got_any = True
                            ans.reasoning += rs
                        for tc in delta.get("tool_calls") or []:
                            got_any = True
                            if ans.first_token_ms is None:
                                ans.first_token_ms = int((time.monotonic() - t0) * 1000)
                            i = tc.get("index", len(calls))
                            c = calls.setdefault(i, {"id": None, "name": "", "arguments": ""})
                            if tc.get("id"):
                                c["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                c["name"] += fn["name"]
                            if fn.get("arguments"):
                                c["arguments"] += fn["arguments"] if isinstance(fn["arguments"], str) else json.dumps(fn["arguments"])
                        if ch.get("finish_reason"):
                            ans.finish = ch["finish_reason"]
        except (httpx.TransportError, httpx.TimeoutException) as e:
            if got_any:
                raise _Started(LLMError("transport_mid_stream", None, type(e).__name__)) from None
            raise LLMError("transport", None, type(e).__name__) from None
        except LLMError as e:
            if got_any:
                raise _Started(e) from None
            raise
        n = 0
        for i in sorted(calls):
            c = calls[i]
            n += 1
            if not c["name"]:
                continue
            ans.tool_calls.append({"id": c["id"] or f"call_{int(time.time()*1000)}_{n}", "name": c["name"],
                                   "arguments": c["arguments"] or "{}"})
        ans.total_ms = int((time.monotonic() - t0) * 1000)
        return ans


class _Started(Exception):
    """An error after the first streamed token: never retried."""

    def __init__(self, error: LLMError):
        super().__init__(str(error))
        self.error = error
