"""Backstop of Walter's one execution policy in the MCP server, for every client (lot E3).

The engine decides allow/ask/deny before it calls a Walter tool (plugins/policy); Claude Code and Codex ask through
their own permission prompts. Whatever the caller, a call the policy refuses (`deny`: secret files, secret-revealing
commands, a door's forbidden class, the generic `walter_call` judged as what it opens) is refused here too — so no
client, old or new, reaches a capability by another path. `ask` is the caller's to put to Monsieur; this server has
no answerer, so it never turns an ask into an allow on its own and never blocks one either.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from . import policy as _policy

log = logging.getLogger("walter.security")


def interface_of(p: dict, client: str) -> str:
    kind = p.get("mcp_clients", {}).get(client, "api")
    return {"engine": "web", "dev": "dev", "telegram": "telegram"}.get(kind, kind)


def _journal(row: dict) -> None:
    root = os.environ.get("WALTER_INSTANCE_ROOT") or _policy._instance_root()
    if not root:
        return
    try:
        d = Path(root, "state", "core", "security")
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        f = d / f"mcp-{time.strftime('%Y-%m-%d', time.gmtime())}.jsonl"
        with open(os.open(f, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a") as out:
            out.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **row}) + "\n")
    except OSError:
        pass


def check(p: dict, client: str, name: str, arguments: dict | None) -> dict:
    return _policy.decide(p, tool=f"mcp__walter__{name}", args=arguments or {}, interface=interface_of(p, client),
                          home=os.environ.get("HOME", "/root"))


def install(mcp, client: str) -> None:
    """Wrap the server's tool dispatch: a refused call never reaches its tool."""
    from mcp.server.fastmcp.exceptions import ToolError
    try:
        p = _policy.load()
    except Exception as e:  # noqa: BLE001 — without the policy, refuse what could act (fail closed), keep reading
        log.warning("walter policy unreadable (%s): only read tools stay open", e)
        p = None
    manager = mcp._tool_manager
    original = manager.call_tool

    async def guarded(name, arguments, context=None, convert_result=False):
        if p is None:
            out = {"decision": "deny", "rule": "fallback", "class": "unknown", "tool": name,
                   "reason": "politique Walter illisible : seules les lectures restent ouvertes"}
            if name.startswith(("memory_", "logs_", "skills_", "skill_read", "module_", "walter_health", "walter_profile")):
                out["decision"] = "allow"
        else:
            out = check(p, client, name, arguments)
        if out["decision"] == "deny":
            _journal({"client": client, "tool": out["tool"], "class": out["class"], "rule": out["rule"]})
            raise ToolError(out["reason"])
        return await original(name, arguments, context=context, convert_result=convert_result)

    manager.call_tool = guarded
