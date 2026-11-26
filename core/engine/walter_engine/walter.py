"""Walter Engine — the doors of the other modules, as the engine uses them (2026-11-17).

The engine owns execution; it reaches every other responsibility through that module's declared interface and
never reimplements it: Memory's gateway (Run Plane runs, bus events, disclosure check), Context's preflight (the
turn's plan and context pack; the living working state; targeted reassessments), Skills (exposure per message),
Context's compaction bridge (`python -m walter_context.bridge`), Walter Router (`walter-router route` to validate a
named model). Every call is bounded and fails open where the engine can go on (context, skills), closed where it
cannot (an owner turn without a run would be refused by walter-llm).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import httpx

from . import config

log = logging.getLogger("walter_engine.walter")


class Doors:
    def __init__(self, settings: config.Settings):
        self.s = settings
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=3.0))
        self._memory_token = None
        self._context_root: Path | None = None

    async def close(self) -> None:
        await self.http.aclose()

    # ── Memory gateway ──
    def memory_token(self) -> str | None:
        if self._memory_token is None:
            self._memory_token = os.environ.get("WALTER_MEMORY_GATEWAY_TOKEN") or config.env_value(
                self.s.memory_env_file, "WALTER_MEMORY_GATEWAY_TOKEN") or ""
        return self._memory_token or None

    async def _mem(self, path: str, body: dict, timeout: float = 8.0) -> dict:
        tok = self.memory_token()
        r = await self.http.post(f"{config.MEMORY_URL}{path}", json=body, timeout=timeout,
                                 headers={"Authorization": f"Bearer {tok}"} if tok else {})
        r.raise_for_status()
        return r.json()

    async def owner_rules(self) -> dict:
        """The owner's universal consignes in force (Memory, owner 2026-11-26): the stable block of the socle."""
        return await self._mem("/v1/owner-rules", {}, timeout=2.5)

    async def run_start(self, body: dict) -> dict:
        return await self._mem("/v1/runs/start", body, timeout=6.0)

    async def run_end(self, run_id: str, session_key: str, status: str, outcome: dict | None = None) -> None:
        try:
            await self._mem("/v1/runs/end", {"run_id": run_id, "session_id": session_key, "status": status,
                                             **({"outcome": outcome} if outcome else {})}, timeout=8.0)
        except Exception as e:  # noqa: BLE001 — the run is closed by the sweeper otherwise
            log.warning("runs/end %s failed: %s", run_id, type(e).__name__)

    async def emit(self, type_: str, subject: str, payload: dict, dedupe_key: str | None = None) -> None:
        try:
            await self._mem("/v1/bus/emit", {"type": type_, "source": config.RUNTIME, "subject": subject,
                                             "payload": payload, **({"dedupe_key": dedupe_key} if dedupe_key else {})})
        except Exception as e:  # noqa: BLE001 — the bus is an observation
            log.info("bus emit %s failed: %s", type_, type(e).__name__)

    async def disclosure(self, tool: str, args: dict) -> dict:
        return await self._mem("/v1/disclosure/check", {"tool": tool, "args": args}, timeout=15.0)

    # ── Context ──
    async def preflight(self, body: dict, timeout_s: float) -> dict:
        tok = self.memory_token()
        r = await self.http.post(f"{config.PREFLIGHT_URL}/preflight?inject=1", json=body, timeout=timeout_s,
                                 headers={"Authorization": f"Bearer {tok}"} if tok else {})
        r.raise_for_status()
        return r.json()

    async def context_legacy(self, body: dict) -> str:
        try:
            out = await self._mem("/v1/context", body, timeout=6.0)
            return out.get("text") or out.get("context") or ""
        except Exception:  # noqa: BLE001
            return ""

    async def state_event(self, session_key: str, kind: str, payload: dict, *, thread_id: str | None = None,
                          run_id: str | None = None) -> None:
        """The living working state (Context): an event of the session. Fire and forget, bounded."""
        tok = self.memory_token()
        try:
            await self.http.post(f"{config.PREFLIGHT_URL}/v1/state/event", timeout=1.5,
                                 headers={"Authorization": f"Bearer {tok}"} if tok else {},
                                 json={"session_id": session_key, "kind": kind, "payload": payload,
                                       **({"thread_id": thread_id} if thread_id else {}),
                                       **({"run_id": run_id} if run_id else {})})
        except Exception:  # noqa: BLE001 — an older Context without the living state: nothing lost for the turn
            pass

    async def state(self, session_key: str) -> dict:
        tok = self.memory_token()
        try:
            r = await self.http.get(f"{config.PREFLIGHT_URL}/v1/state", params={"session_id": session_key}, timeout=2.0,
                                    headers={"Authorization": f"Bearer {tok}"} if tok else {})
            return r.json() if r.status_code == 200 else {}
        except Exception:  # noqa: BLE001
            return {}

    async def reassess(self, body: dict) -> dict:
        tok = self.memory_token()
        try:
            r = await self.http.post(f"{config.PREFLIGHT_URL}/v1/reassess", json=body, timeout=4.0,
                                     headers={"Authorization": f"Bearer {tok}"} if tok else {})
            return r.json() if r.status_code == 200 else {"asked": False, "reason": f"http {r.status_code}"}
        except Exception as e:  # noqa: BLE001
            return {"asked": False, "reason": f"unavailable: {type(e).__name__}"}

    def context_root(self) -> Path | None:
        if self._context_root is None:
            self._context_root = config.module_root("context")   # `walter path context`; None = no bridge
        return self._context_root

    async def bridge(self, request: dict, timeout_s: float = 30.0) -> dict:
        """walter-context's compaction bridge: one JSON in, one JSON out, in a bounded subprocess."""
        root = self.context_root()
        if root is None:
            raise RuntimeError("walter-context unavailable: `walter path context` gave no root")
        proc = await asyncio.create_subprocess_exec(
            "walter-python", "-m", "walter_context.bridge", cwd=str(root), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env={**os.environ, "PYTHONPATH": str(root)})
        try:
            out, _ = await asyncio.wait_for(proc.communicate(json.dumps({"version": 1, **request}).encode()), timeout_s)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            proc.kill()
            raise
        if proc.returncode != 0:
            raise RuntimeError(f"walter-context bridge exited {proc.returncode}")
        res = json.loads(out or b"{}")
        if res.get("version") != 1 or res.get("engine") != "walter-context":
            raise RuntimeError("walter-context bridge: protocol mismatch")
        return res

    # ── Skills ──
    async def skills(self, message: str, session_key: str) -> str:
        try:
            r = await self.http.post(f"{config.SKILLS_URL}/v1/expose", timeout=4.0, json={
                "kind": "message", "message": message, "context": "", "session_id": session_key,
                "runtime": config.RUNTIME, "first_turn": False})
            return (r.json() or {}).get("text") or "" if r.status_code == 200 else ""
        except Exception:  # noqa: BLE001
            return ""

    # ── Router ──
    async def validate_model(self, model: dict) -> dict:
        args = ["walter-router", "route", "-", "--model", model["id"]]
        if model.get("provider"):
            args += ["--provider", model["provider"]]
        try:
            proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.DEVNULL,
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await asyncio.wait_for(proc.communicate(), 20)
            d = json.loads(out or b"null")
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"router_unavailable: {type(e).__name__}"}
        if not d or d.get("mode") == "none" or d.get("error") or not (d.get("execution") or []):
            return {"ok": False, "error": str((d or {}).get("error") or "no route for this model")[:200]}
        return {"ok": True, "model_id": d.get("model_id")}
