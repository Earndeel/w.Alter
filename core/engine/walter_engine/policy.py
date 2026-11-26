"""Walter Engine — Walter's policy before every call (2026-11-17).

One decision before every tool call of every agent of the engine — the owner's agent, its sub-agents and the calls
its Python kernel makes — from Walter's one policy (`core/security/policy.json`, the rules the MCP server applies to
every other client; `walter_security.policy.decide`). The most restrictive wins:
  never (secret files, secret-revealing commands, delegation depth) → deny, journaled;
  the class of the tool under the preset of the session's door (a sub-agent never above its parent: preset `child`);
  `check` (outgoing messages) → Memory's disclosure check: block ⇒ deny, ask ⇒ ask, failure ⇒ ask.
`ask` goes to the engine's approvals: the client of the root session's door answers (web dialog, Telegram buttons,
an API client); an unattended session or a command door has nobody to ask, so an `ask` is a refusal (fail closed).
The model's judgement never widens any of this: the policy is code and data, not a prompt.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

from . import config

log = logging.getLogger("walter_engine.policy")

if str(config.CORE_ROOT / "security") not in sys.path:
    sys.path.insert(0, str(config.CORE_ROOT / "security"))
from walter_security import policy as wpolicy  # noqa: E402

# the door (Engine API interface) → the policy's interface name (policy.json `interfaces`)
IFACE = {"web": "web", "telegram": "telegram", "api": "api", "command": "command", "mcp": "api", "schedule": "api",
         "webhook": "api", "lab": "api", "test": "test", "dev": "dev"}
FALLBACK = {"decision": "ask", "rule": "fallback", "reason": "politique Walter illisible : accord requis", "class": "unknown"}


class Policy:
    def __init__(self, settings: config.Settings, doors):
        self.s = settings
        self.doors = doors
        self.dir = config.instance_root() / "state" / "core" / "security"
        self.home = os.environ.get("HOME", "/root")
        self._p = None
        self._mtime = None

    def _load(self):
        try:
            path = Path(wpolicy.POLICY)
            m = path.stat().st_mtime
            if self._p is None or m != self._mtime:
                self._p, self._mtime = wpolicy.load(path), m
        except Exception as e:  # noqa: BLE001 — unreadable policy: everything asks (closed without an answerer)
            log.warning("policy unreadable: %s", e)
            self._p = None
        return self._p

    def record(self, row: dict) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            p = self.dir / f"policy-{time.strftime('%Y-%m-%d', time.gmtime())}.jsonl"
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as fh:
                fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runtime": config.RUNTIME,
                                     **row}, ensure_ascii=False) + "\n")
        except OSError:
            pass

    @staticmethod
    def machine_interface(p: dict | None, door: str, principal: dict | None) -> str | None:
        """A delegation by a declared machine caller (policy `machine_interfaces`, by id prefix: `guardian-` = the
        module guardians, 2026-11-20) is judged under that caller's interface instead of the generic `api`."""
        if not p or door != "mcp" or (principal or {}).get("kind") != "machine":
            return None
        pid = str((principal or {}).get("id") or "")
        for prefix, iface in (p.get("machine_interfaces") or {}).items():
            if not prefix.startswith("_") and pid.startswith(prefix) and iface in (p.get("interfaces") or {}):
                return iface
        return None

    @staticmethod
    def test_interface(p: dict | None, door: str, principal: dict | None) -> str | None:
        """A test account declared in policy `test_interfaces` (by id prefix: `bench-` = the payload bench,
        2026-11-23) is judged under that interface instead of `test`: the bench measures the autonomous Walter."""
        if not p or door != "test" or (principal or {}).get("kind") != "test":
            return None
        pid = str((principal or {}).get("id") or "")
        for prefix, iface in (p.get("test_interfaces") or {}).items():
            if not prefix.startswith("_") and pid.startswith(prefix) and iface in (p.get("interfaces") or {}):
                return iface
        return None

    async def judge(self, *, tool: str, args: dict, door: str, depth: int, principal: dict | None = None) -> dict:
        p = self._load()
        iface = (self.machine_interface(p, door, principal) or self.test_interface(p, door, principal)
                 or IFACE.get(door, "api"))
        if p is None:
            out = {**FALLBACK, "tool": tool}
        else:
            out = wpolicy.decide(p, tool=tool, args=args, interface=iface, depth=depth, home=self.home)
        if out["decision"] == "check":
            inner = args.get("arguments") if tool == "mcp__walter__walter_call" and isinstance(args.get("arguments"), dict) else args
            try:
                res = await self.doors.disclosure(out["tool"], inner or {})
                action = res.get("action")
                out = {**out, "decision": {"allow": "allow", "ask": "ask", "block": "deny"}.get(action, "ask"),
                       "rule": f"disclosure.{action}", "reason": res.get("reason") or out.get("reason")}
            except Exception:  # noqa: BLE001
                out = {**out, "decision": "ask", "rule": "disclosure.unavailable",
                       "reason": "contrôle de divulgation indisponible : accord de Monsieur requis"}
        out = {**out, "iface": iface, "depth": depth}
        if out["decision"] != "allow":
            self.record({"decision": out["decision"], "stage": "pre-execute", "tool": out.get("tool"), "class": out.get("class"),
                         "rule": out.get("rule"), "iface": iface, "depth": depth})
        return out
