"""Antigravity subscription transport (Google AI Pro / Ultra): the official Antigravity CLI, text only.

Google treats any third-party client on Antigravity's OAuth login as a terms violation (accounts suspended in 2026):
this adapter never reads, copies or replays the CLI's token. It runs the official `agy` in print mode, in an empty
private directory, with every tool denied (files, commands, web pages, MCP), and returns its text. The CLI adds its
own agent instructions (~7k input tokens per call, counted on the subscription quota).

No tools, images or audio: such a request fails before any call, so the gateway moves on to the next route.
The CLI keeps each conversation and summaries of past ones on disk; they are deleted after the call, so no prompt
outlives it and no call sees an earlier one. Nothing here logs prompts, answers or credentials.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path

PROVIDER = "antigravity"
# every tool family the CLI has (antigravity.google/docs/permissions): deny wins over any allow rule
DENY_ALL = {"permissions": {"deny": ["read_file(*)", "write_file(*)", "read_url(*)", "execute_url(*)", "command(*)",
                                     "mcp(*)", "unsandboxed(*)"]}}
EFFORTS = ("low", "medium", "high")
EFFORT_OF = {"none": "low", "non-reasoning": "low", "minimal": "low", "low": "low", "medium": "medium",
             "high": "high", "xhigh": "high", "max": "high"}
NO_TOOLS = ("Answer directly in text from your own knowledge. You have no tools: do not try to read or write files, "
            "run commands or open pages.")
QUOTA = re.compile(r"quota|rate.?limit|resource.?exhausted|429|too many requests", re.I)


class TransportError(RuntimeError):
    """Safe, value-free transport failure (the gateway logs its type and moves to the next route)."""


class QuotaExhausted(TransportError):
    """The subscription's shared Gemini window is spent (or the non-Gemini fixed limit)."""


def base_id(cli_id: str) -> str:
    """Router offer key of a CLI model id: the reasoning level is a route parameter, not a model
    (gemini-3.8-flash-high -> gemini-3.8-flash, claude-opus-4-6-thinking -> claude-opus-4-6)."""
    return re.sub(r"-(low|medium|high)$", "", re.sub(r"-thinking$", "", cli_id))


def cli_model(model: str, effort: str | None, verified: list[str]) -> str:
    """The verified CLI id for a router model + reasoning level (the closest level the account offers)."""
    if model in verified:
        return model
    want = EFFORT_OF.get(effort or "", "high")
    candidates = [v for v in verified if base_id(v) == model]
    if not candidates:
        raise TransportError("model_not_verified")
    for level in (want, *sorted(EFFORTS, key=lambda e: abs(EFFORTS.index(e) - EFFORTS.index(want)))):
        if f"{model}-{level}" in candidates:
            return f"{model}-{level}"
    return candidates[0]


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "text":
                raise TransportError("multimodal_unsupported")
            parts.append(part.get("text") or "")
        return "\n".join(parts)
    if content is None:
        return ""
    raise TransportError("unsupported_content")


def prompt_of(messages: list[dict], response_format: dict | None = None) -> str:
    """One prompt from OpenAI chat messages: instructions, then the conversation, then the message to answer."""
    system, turns = [], []
    for m in messages:
        if m.get("tool_calls") or m.get("role") in ("tool", "function"):
            raise TransportError("tools_unsupported")
        text = _text(m.get("content"))
        if m.get("role") in ("system", "developer"):
            system.append(text)
        else:
            turns.append((m.get("role") or "user", text))
    if not turns or turns[-1][0] != "user":
        raise TransportError("no_user_message")
    out = [NO_TOOLS]
    if response_format and response_format.get("type") == "json_object":
        out.append("Answer with one valid JSON object only, no text around it and no code fence.")
    if system:
        out.append("<instructions>\n" + "\n\n".join(system) + "\n</instructions>")
    if len(turns) > 1:
        out.append("<conversation>\n" + "\n\n".join(f"[{role}]\n{text}" for role, text in turns[:-1])
                   + "\n</conversation>\nAnswer the last message below, continuing this conversation.")
    out.append(turns[-1][1])
    return "\n\n".join(out)


def _paths(config: dict) -> tuple[Path, Path]:
    home = Path(config["home"])
    return home, home / ".gemini" / "antigravity-cli"


def _forget(state: Path, conversation: str | None) -> None:
    """Delete what the CLI kept of this call; summaries of past calls only when no other call is running."""
    if conversation and re.fullmatch(r"[0-9a-f-]{36}", conversation):
        for p in (state / "conversations" / f"{conversation}.db", state / "annotations" / f"{conversation}.pbtxt",
                  state / "presence" / f"{conversation}.lock"):
            p.unlink(missing_ok=True)
        shutil.rmtree(state / "brain" / conversation, ignore_errors=True)
    lock = open(state / ".walter-calls.lock", "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)   # fails while another call holds its shared lock
    except OSError:
        lock.close()
        return
    try:
        for name in ("conversation_summaries.db", "conversation_summaries.db-wal", "conversation_summaries.db-shm",
                     "jetbox_summaries_proto.pb", "cache/last_conversations.json"):
            (state / name).unlink(missing_ok=True)
        for sub in ("implicit", "conversations", "brain", "annotations", "presence"):
            for p in (state / sub).glob("*"):
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def _command(config: dict, model: str, schema: dict | None, timeout: float) -> list[str]:
    cmd = [config["cli"], "--input-format", "stream-json", "--output-format", "stream-json", "--model", model,
           "--sandbox", "--disable-slash-commands", "--settings", json.dumps(DENY_ALL),
           "--print-timeout", f"{max(1, int(timeout))}s"]
    if schema:
        cmd += ["--json-schema", json.dumps(schema)]
    return cmd + ["-p="]   # print mode last: `-p` would take the next flag as its prompt


def _usage(u: dict | None):
    from litellm.types.utils import Usage
    u = u or {}
    return Usage(prompt_tokens=int(u.get("input_tokens") or 0),
                 completion_tokens=int(u.get("output_tokens") or 0) + int(u.get("thinking_tokens") or 0),
                 total_tokens=int(u.get("total_tokens") or 0))


def _failure(result: dict, stderr: str) -> TransportError:
    detail = f"{result.get('error') or ''} {stderr[-2000:]}"
    return QuotaExhausted("quota") if QUOTA.search(detail) else TransportError(
        "cli_" + str(result.get("status") or "failed").lower())


async def completion(config: dict, *, model: str, messages: list, stream: bool = False, timeout=None,
                     reasoning_effort: str | None = None, response_format: dict | None = None, tools=None, **_):
    """OpenAI-shaped answer (ModelResponse, or an async iterator of chunks when streaming) from one CLI call."""
    from litellm.types.utils import ModelResponse, ModelResponseStream
    if tools:
        raise TransportError("tools_unsupported")
    schema = None
    if response_format and response_format.get("type") == "json_schema":
        schema = (response_format.get("json_schema") or {}).get("schema")
    prompt = prompt_of(messages, response_format)
    cli_id = cli_model(model, reasoning_effort, list(config.get("verified_models") or []))
    limit = float(timeout or config.get("timeout") or 300)
    home, state = _paths(config)
    calls = home / "calls"
    calls.mkdir(parents=True, exist_ok=True, mode=0o700)
    workdir = tempfile.mkdtemp(dir=calls)
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}   # no inherited key or gateway setting
    lock = open(state / ".walter-calls.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_SH)
    proc = await asyncio.create_subprocess_exec(
        *_command(config, cli_id, schema, limit), cwd=workdir, env=env, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=16 * 1024 * 1024)
    proc.stdin.write((json.dumps({"event": "user", "message": {"content": prompt}}) + "\n").encode())
    await proc.stdin.drain()
    proc.stdin.close()
    rid, created = f"chatcmpl-agy-{uuid.uuid4().hex}", int(time.time())
    deadline = time.monotonic() + limit + 15
    state_box: dict = {"conversation": None, "result": None, "stderr": None}

    def kill():
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    async def events():
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=max(1, deadline - time.monotonic()))
            if not line:
                return
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            body = ev.get("step_update") or ev.get("result") or {}
            state_box["conversation"] = body.get("conversation_id") or state_box["conversation"]
            if ev.get("event") == "result":
                state_box["result"] = ev["result"]
            yield ev

    async def finish():
        """Once per call: reap the CLI, release the lock, delete its workdir and what it kept of the call."""
        if state_box["stderr"] is not None:
            return state_box["stderr"]
        state_box["stderr"] = ""
        try:
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                kill()
                await proc.wait()
            state_box["stderr"] = (await proc.stderr.read()).decode(errors="replace")
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
            shutil.rmtree(workdir, ignore_errors=True)
            await asyncio.to_thread(_forget, state, state_box["conversation"])
        return state_box["stderr"]

    def answer(result: dict) -> str:
        if schema and result.get("structured_output") is not None:
            return json.dumps(result["structured_output"], ensure_ascii=False)
        text = result.get("response") or ""
        if response_format and response_format.get("type") == "json_object":
            t = text.strip()
            t = t[t.find("{"):t.rfind("}") + 1] if "{" in t else t
            json.loads(t)   # ValueError = no JSON object: next route
            return t
        return text

    if not stream:
        try:
            async for _ in events():
                pass
        except BaseException:
            kill()
            await finish()
            raise
        stderr = await finish()
        result = state_box["result"] or {}
        if result.get("status") != "SUCCESS" or not (result.get("response") or result.get("structured_output")):
            raise _failure(result, stderr)
        return ModelResponse(id=rid, created=created, model=model, usage=_usage(result.get("usage")),
                             choices=[{"index": 0, "finish_reason": "stop",
                                       "message": {"role": "assistant", "content": answer(result)}}])

    async def chunks():
        sent = False
        try:
            if schema or (response_format and response_format.get("type") == "json_object"):
                async for _ in events():   # a checked JSON answer is sent whole
                    pass
            else:
                async for ev in events():
                    delta = (ev.get("step_update") or {}).get("text_delta")
                    if delta and (ev["step_update"].get("step_type") == "agent_response"):
                        yield ModelResponseStream(id=rid, created=created, model=model, choices=[
                            {"index": 0, "delta": {"role": "assistant", "content": delta}}])
                        sent = True
            result = state_box["result"] or {}
            stderr = await finish()
            if result.get("status") != "SUCCESS" or not (result.get("response") or result.get("structured_output")):
                raise _failure(result, stderr)
            if not sent:
                yield ModelResponseStream(id=rid, created=created, model=model, choices=[
                    {"index": 0, "delta": {"role": "assistant", "content": answer(result)}}])
            yield ModelResponseStream(id=rid, created=created, model=model, usage=_usage(result.get("usage")),
                                      choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}])
        finally:
            kill()
            await finish()

    return chunks()
