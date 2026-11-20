"""Walter Engine — the Walter MCP server as a tool source (2026-11-17).

One stdio client to `core/server.py` (client tag `engine`: the server's backstop judges it under the engine's door,
it denies what the policy denies and leaves asks to the engine). The server lists EVERY tool (`WALTER_TOOLSET=all`):
the engine offers the model the core toolset of `core/config/toolsets.toml` (`[clients.engine]`, else `[clients.dsh]`)
and keeps the others reachable — by `walter_call` for the model, by name from Python (`await tools.memory_events()`).
The child is restarted on the next call if it dies; every call is bounded (10 min, as before).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tomllib
from pathlib import Path

from . import Exec, Result, Tool, obj
from .. import config

log = logging.getLogger("walter_engine.mcp")
PREFIX = "mcp__walter__"
CALL_TIMEOUT_S = 600.0


def _core_toolset() -> list[str] | None:
    try:
        conf = tomllib.loads((config.CORE_ROOT / "config" / "toolsets.toml").read_text())
    except (OSError, ValueError):
        return None
    own = (conf.get("clients") or {}).get("engine") or (conf.get("clients") or {}).get("dsh") or {}
    name = own.get("toolset")
    tools = (conf.get("toolsets") or {}).get(name) if name else None
    return list(tools) if isinstance(tools, list) else None


class McpClient:
    def __init__(self, settings: config.Settings, registry):
        self.s = settings
        self.registry = registry
        self.proc: asyncio.subprocess.Process | None = None
        self.pending: dict[int, asyncio.Future] = {}
        self.ids = 0
        self.instructions = ""
        self.lock = asyncio.Lock()
        self.reader: asyncio.Task | None = None
        self.stderr_tail = ""
        self.tools: list[dict] = []

    async def start(self) -> None:
        async with self.lock:
            if self.proc and self.proc.returncode is None:
                return
            python = os.environ.get("WALTER_MCP_PYTHON", str(config.CORE_ROOT / "venv" / "bin" / "python"))
            if not Path(python).exists():
                python = "/opt/walter-core/venv/bin/python"
            env = {**os.environ, "WALTER_CLIENT_TAG": "engine", "WALTER_TOOLSET": "all", "WALTER_MODULE_LAYER": "m0"}
            self.proc = await asyncio.create_subprocess_exec(
                python, str(config.CORE_ROOT / "server.py"), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env, limit=64 * 2**20)
            self.reader = asyncio.get_running_loop().create_task(self._read(self.proc))
            asyncio.get_running_loop().create_task(self._drain(self.proc))
            init = await self._request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                      "clientInfo": {"name": "walter-engine", "version": "1"}}, 60)
            self.instructions = str((init or {}).get("instructions") or "")
            await self._notify("notifications/initialized", {})
            tools, cursor = [], None
            while True:
                page = await self._request("tools/list", {"cursor": cursor} if cursor else {}, 60)
                tools += page.get("tools") or []
                cursor = page.get("nextCursor")
                if not cursor:
                    break
            self.tools = tools
            self._register(tools)
            log.info("walter MCP: %d tools", len(tools))

    def _register(self, tools: list[dict]) -> None:
        self.registry.remove_source("mcp:walter")
        listed = set(_core_toolset() or [t["name"] for t in tools])
        hidden_names = []
        for t in tools:
            name = t.get("name")
            if not name or name == "walter_call":
                continue
            hidden = name not in listed
            if hidden:
                hidden_names.append(name)
            schema = t.get("inputSchema") or {"type": "object", "properties": {}}
            self.registry.add(Tool(PREFIX + name, str(t.get("description") or "")[:4000], schema,
                                   self._runner(name), parallel=_read_only(name), source="mcp:walter", hidden=hidden))
        if hidden_names:
            names = ", ".join(sorted(hidden_names))
            self.registry.add(Tool(
                PREFIX + "walter_call",
                "Reach a Walter tool that is not listed directly: walter_call() lists them, "
                "walter_call(tool=NAME, describe=true) gives its parameters, walter_call(tool=NAME, arguments={…}) runs it "
                f"(same rules as a direct call). Available: {names}.",
                obj({"tool": {"type": "string"}, "arguments": {"type": "object"}, "describe": {"type": "boolean"}}),
                self._generic, parallel=False, source="mcp:walter"))

    def _runner(self, name: str):
        async def run(args: dict, ex: Exec) -> Result:
            return await self.call(name, args, ex)
        return run

    async def _generic(self, args: dict, ex: Exec) -> Result:
        tool = str(args.get("tool") or "")
        if not tool:
            rows = [{"name": t.name.removeprefix(PREFIX), "description": t.description.split("\n")[0][:200]}
                    for t in self.registry.tools.values() if t.source == "mcp:walter" and t.hidden]
            return Result(json.dumps(rows, ensure_ascii=False), value=rows)
        t = self.registry.tools.get(PREFIX + tool)
        if not t:
            return Result(f"no Walter tool named {tool}", True)
        if args.get("describe") is True:
            d = {"name": tool, "description": t.description, "parameters": t.parameters}
            return Result(json.dumps(d, ensure_ascii=False), value=d)
        return await self.call(tool, args.get("arguments") or {}, ex)

    async def call(self, name: str, args: dict, ex: Exec) -> Result:
        if not self.proc or self.proc.returncode is not None:
            await self.start()
        a = ex.agent       # the run of the turn: a task the tool creates belongs to it (its channel), as for shell_env
        rid = getattr(a, "run_id", None) or (a.root().run_id if hasattr(a, "root") else None)
        meta = {k: v for k, v in (("walter_run_id", rid), ("walter_session_id", getattr(a, "key", None))) if v}
        req = self._request("tools/call", {"name": name, "arguments": args, **({"_meta": meta} if meta else {})},
                            CALL_TIMEOUT_S)
        task = asyncio.ensure_future(req)
        stop = asyncio.ensure_future(ex.cancel.wait())
        try:
            done, _ = await asyncio.wait({task, stop}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()
        if task not in done:
            task.cancel()
            return Result("[interrupted]", True)
        try:
            res = task.result()
        except asyncio.TimeoutError:
            return Result(f"{name}: no answer within {int(CALL_TIMEOUT_S)} s", True)
        except McpError as e:
            return Result(f"{name}: {e}", True)
        parts = []
        for c in res.get("content") or []:
            if c.get("type") == "text":
                parts.append(c.get("text") or "")
            elif c.get("type") == "image":
                parts.append(f"[image {c.get('mimeType')}]")
            else:
                parts.append(json.dumps(c, ensure_ascii=False)[:2000])
        text = "\n".join(parts)
        value = res.get("structuredContent")
        if value is None:
            try:
                value = json.loads(text)
            except ValueError:
                value = text
        if isinstance(value, dict) and set(value) == {"result"}:
            value = value["result"]
        return Result(text or "(no output)", bool(res.get("isError")), value=value)

    # ── JSON-RPC over stdio ──
    async def _request(self, method: str, params: dict, timeout: float):
        self.ids += 1
        rid = self.ids
        fut = asyncio.get_running_loop().create_future()
        self.pending[rid] = fut
        try:
            await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            return await asyncio.wait_for(fut, timeout)
        finally:
            self.pending.pop(rid, None)

    async def _notify(self, method: str, params: dict) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _send(self, msg: dict) -> None:
        if not self.proc or not self.proc.stdin:
            raise McpError("walter MCP server is not running")
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        await self.proc.stdin.drain()

    async def _read(self, proc) -> None:
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if "id" in msg and ("result" in msg or "error" in msg):
                    fut = self.pending.get(msg["id"])
                    if fut and not fut.done():
                        if "error" in msg:
                            err = msg["error"] or {}
                            fut.set_exception(McpError(str(err.get("message") or err)[:2000]))
                        else:
                            fut.set_result(msg["result"])
                elif "id" in msg and "method" in msg:      # a server request (ping, roots): answered empty
                    await self._send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
        finally:
            for fut in self.pending.values():
                if not fut.done():
                    fut.set_exception(McpError(f"walter MCP server stopped{': ' + self.stderr_tail[-300:] if self.stderr_tail else ''}"))

    async def _drain(self, proc) -> None:
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            self.stderr_tail = (self.stderr_tail + line.decode("utf-8", "replace"))[-4000:]

    async def close(self) -> None:
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.stdin.close()
                await asyncio.wait_for(self.proc.wait(), 5)
            except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                self.proc.kill()


class McpError(RuntimeError):
    pass


_READ_PREFIXES = ("memory_context", "memory_recall", "memory_search", "memory_events", "memory_reflect", "memory_view",
                  "person_lookup", "logs_", "vault_search", "vault_get", "skills_", "skill_read", "walter_profile",
                  "walter_health", "walter_modules", "module_", "secret_search", "secret_reference", "walter_route",
                  "walter_decide", "browser_sites", "walter_plans", "tasks_list", "beeper_read")


def _read_only(name: str) -> bool:
    return name.startswith(_READ_PREFIXES)
