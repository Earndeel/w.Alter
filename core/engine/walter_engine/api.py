"""Walter Engine API v1 — the canonical door of the native engine (2026-11-17; contract engine-api.v1.json, unchanged).

The same contract the DSH-hosted door served since lot E4 (Telegram, the web, Walter modules, tests use it as is):
POST /v1 {version: 1, op, …}, GET /v1/health, GET /v1/events?session_id=&since_seq= (SSE), loopback only, an agent
token in a header compared in constant time. It owns no loop: it maps a door's conversation `<door>/<account>/<conv>`
to ONE engine session (bindings.json, the table the DSH door kept — imported sessions keep their ids) and asks the
engine to submit, follow, interrupt, answer.

Identity (Core, 2026-11-17): who speaks is resolved by the engine from the instance's account registry, never from
what a client claims — a test account (`e2e`) is a `test` principal on every door, its conversations are filed on the
Run Plane's `test` channel (never the owner's objectives), an `owner` claim for an account the instance does not list
is refused. Rows written before this rule are re-resolved when they are read.

Additions for the native web interface (same door, owner only): `session.history` (a page of client events),
`session.rename`.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from pathlib import Path

from . import config, identity

DOORS = ["web", "telegram", "api", "mcp", "command", "schedule", "webhook", "lab"]
SESSION_ID = re.compile(r"^(web|telegram|api|mcp|command|schedule|webhook|lab)/[A-Za-z0-9._:@/-]{1,200}$")
PART = re.compile(r"^[A-Za-z0-9._:@-]{1,100}$")
MODEL_ID = re.compile(r"^[A-Za-z0-9._:/-]{1,120}$")
LEVELS = ("L1", "L2", "L3")
PRESET_OF = {"web": "web-owner", "telegram": "telegram-owner", "api": "api", "command": "command", "mcp": "api",
             "schedule": "api", "webhook": "api", "lab": "api"}
KEY_PREFIXES = ("dsh/vm/", "walter/vm/")
MAX_WAIT_MS = 30 * 60_000


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.status, self.code, self.detail = status, code, detail or code


def ensure_token(path: Path) -> str:
    """The token clients present; created once (0600), never logged, never in a URL."""
    try:
        t = path.read_text().strip()
        if len(t) >= 32:
            return t
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    t = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(t + "\n")
    return t


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(str(a).encode(), str(b).encode())


def mission(d: dict) -> str:
    parts = ["[Délégation Walter] Tu exécutes une sous-tâche pour un autre agent. Tu ne vois pas sa conversation : "
             "tout ce qu'il faut est ci-dessous. Réponds par le résultat lui-même, vérifiable, sans préambule.", "",
             f"Objectif : {d['goal'].strip()}"]
    if d.get("context"):
        parts += ["", f"Contexte fourni : {str(d['context']).strip()}"]
    if d.get("constraints"):
        parts += ["", f"Contraintes : {json.dumps(d['constraints'], ensure_ascii=False)}"]
    if d.get("output_contract"):
        parts += ["", f"Forme de la réponse (JSON conforme à ce schéma) : {json.dumps(d['output_contract'], ensure_ascii=False)}"]
    return "\n".join(parts)


def session_id_of(door: str, account: str, conversation: str) -> str:
    if door not in DOORS:
        raise ValueError(f"unknown interface {door}")
    if not PART.match(str(account or "")):
        raise ValueError("principal id must match [A-Za-z0-9._:@-]{1,100}")
    if not PART.match(str(conversation or "")):
        raise ValueError("conversation must match [A-Za-z0-9._:@-]{1,100}")
    sid = f"{door}/{account}/{conversation}"
    if not SESSION_ID.match(sid):
        raise ValueError("invalid session id")
    return sid


def effective_door(iface: str, mode: str) -> str:
    return "command" if mode == "command" else iface


# ── what a client sees of a session (pure functions over the journal, live and after a restart alike) ──
def turn_status(reason) -> str:
    kind = reason if isinstance(reason, str) else (reason or {}).get("kind")
    return {"completed": "ok", "forked": "ok", "max-tokens": "ok", "aborted": "cancelled", "blocked": "budget_exhausted",
            "error": "error", "interrupted": "interrupted"}.get(kind, "unknown_outcome" if kind else "ok")


def reason_of(reason):
    return reason if isinstance(reason, str) else (reason or {}).get("kind")


def error_of(reason):
    if isinstance(reason, dict) and reason.get("kind") == "error" and (reason.get("error") or {}).get("code"):
        return str(reason["error"]["code"])[:60]
    return None


def _preview(v, n: int) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    s = " ".join((s or "").split())
    return s[:n] + "…" if len(s) > n else s


def to_client_event(ev: dict, *, rich: bool = False) -> dict | None:
    """One journal event → one client event (or None). `rich` adds what the web interface shows (previews, notices,
    deliverables, titles); the API stream keeps the contract's vocabulary."""
    d = ev.get("data") or {}
    base = {"seq": ev.get("seq"), "at": ev.get("time")}
    t = ev.get("type")
    if t == "turn/start":
        return {**base, "type": "turn.started", "turn": d.get("turn")}
    if t == "turn/end":
        return {**base, "type": "turn.ended", "turn": d.get("turn"), "status": turn_status(d.get("reason")),
                "reason": reason_of(d.get("reason"))}
    if t == "user/message":
        src = d.get("source") or {}
        if src.get("kind") != "user":
            if rich and src.get("kind") in ("tool-jobs", "subagent-settled", "engine-restart", "walter-budget"):
                return {**base, "type": "notice", "text": (d.get("text") or "")[:600]}
            return None
        return {**base, "type": "message.user", "request_id": src.get("rpcId"), "text": d.get("text") or "",
                **({"source": "steer"} if rich and src.get("steer") else {})}
    if t == "assistant/message":
        text = d.get("text") or ""
        if not text:
            return None
        return {**base, "type": "message.assistant", "turn": d.get("turn"), "step": d.get("step"), "text": text,
                **({"model": d.get("model")} if rich and d.get("model") else {})}
    if t == "tool/call":
        if d.get("nested") and not rich:
            return None
        return {**base, "type": "tool.called", "turn": d.get("turn"), "name": d.get("name"), "call_id": d.get("callId"),
                **({"args_preview": _preview(d.get("arguments") or "", 300)} if rich else {})}
    if t == "tool/result":
        if d.get("nested") and not rich:
            return None
        return {**base, "type": "tool.result", "turn": d.get("turn"), "ok": not d.get("isError"), "call_id": d.get("callId"),
                **({"preview": _preview(d.get("content") or "", 2000)} if rich else {})}
    if rich and t == "deliverable":
        return {**base, "type": "deliverable", "url": d.get("url"), "title": d.get("title")}
    if rich and t == "session/title":
        return {**base, "type": "session.title", "title": d.get("title")}
    return None


class TurnWatch:
    """Follows one request through the journal: the turn that received the message carrying `request_id` (its rpcId),
    its last answer, its tools, its end. Feed events in seq order; `done` once that turn has ended."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.turn = self.current = None
        self.pending_start = False
        self.text, self.tools, self.done, self.reason, self.end_seq, self.error = "", [], False, None, None, None
        self.last = 0

    def feed(self, ev: dict) -> "TurnWatch":
        if self.done or not ev or ev.get("seq", 0) <= self.last:
            return self
        self.last = ev.get("seq", 0)
        d, t = ev.get("data") or {}, ev.get("type")
        if t == "turn/start":
            self.current = d.get("turn")
            if self.pending_start:
                self.turn, self.pending_start = d.get("turn"), False
        elif t == "turn/end" and self.current == d.get("turn"):
            if self.turn == d.get("turn"):
                self.done, self.reason, self.end_seq = True, reason_of(d.get("reason")), ev.get("seq")
                self.error = error_of(d.get("reason"))
            self.current = None
        elif t == "user/message" and self.turn is None and (d.get("source") or {}).get("rpcId") == self.request_id:
            if self.current is not None:
                self.turn = self.current
            else:
                self.pending_start = True
        elif self.turn is not None and d.get("turn") == self.turn:
            if t == "assistant/message" and d.get("text"):
                self.text = d["text"]
            elif t == "tool/call" and not d.get("nested"):
                self.tools.append(d.get("name"))
        return self

    def result(self) -> dict:
        return {"done": self.done, "turn": self.turn, "status": turn_status(self.reason) if self.done else "running",
                "reason": self.reason, **({"error": self.error} if self.error else {}), "text": self.text,
                "tools": self.tools, "seq": self.end_seq}


class Bindings:
    """`<door>/<account>/<conversation>` → engine session (the DSH door's table, same file format)."""

    def __init__(self, path: Path):
        self.path = path
        self.rows: dict[str, dict] = {}

    def load(self) -> "Bindings":
        try:
            self.rows = json.loads(self.path.read_text()).get("sessions") or {}
        except FileNotFoundError:
            self.rows = {}
        self._kernels = {r.get("kernel"): r for r in self.rows.values()}
        return self

    def get(self, sid: str) -> dict | None:
        return self.rows.get(sid)

    def by_kernel(self, kernel: str) -> dict | None:
        return self._kernels.get(kernel)

    def list(self, iface: str | None = None, account: str | None = None) -> list[dict]:
        return [r for r in self.rows.values() if (not iface or r.get("interface") == iface)
                and (not account or (r.get("principal") or {}).get("id") == account)]

    def set(self, row: dict) -> dict:
        self.rows[row["session_id"]] = row
        self._kernels[row["kernel"]] = row
        self.save()
        return row

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_name(f"{self.path.name}.tmp-{os.getpid()}")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps({"version": 1, "sessions": self.rows}, indent=1, ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)


def principal_of(row: dict) -> dict:
    """A row's principal as the instance knows it now (rows written before the identity rule are re-resolved)."""
    p = row.get("principal") or {}
    try:
        return identity.resolve(p)
    except identity.IdentityError:
        # an owner claim for an account the instance does not list: never the owner (fail towards machine)
        return {"kind": "machine", "id": str(p.get("id") or "unknown"), "claimed": p.get("kind")}


class EngineApi:
    def __init__(self, engine, settings: config.Settings):
        self.e = engine
        self.s = settings
        self.bindings = Bindings(settings.api_state / "bindings.json").load()
        self.accepted: dict[str, float] = {}
        self.listeners: set = set()          # callables(engine_session_id, event) for SSE approval notices
        engine.binder = self._bind
        engine.approval_listeners.add(lambda sid, ev: self._emit(sid, ev))

    # ── the doors' word on a session ──
    def _bind(self, agent) -> None:
        row = self.bindings.by_kernel(agent.sid)
        if row is None:
            return
        p = principal_of(row)
        parent = row.get("parent") or {}
        agent.meta.update({
            "door": row.get("door") or "web", "principal": p, "unattended": bool(row.get("unattended")),
            "parent_run_id": parent.get("run_id"), "model": row.get("model"), "level": row.get("level"),
            "interface": row.get("door"), "engine_session": row["session_id"],
            "delegation_depth": (int(parent.get("depth") or 0) + 1) if row.get("unattended") and parent else 0})

    def _set(self, row: dict) -> dict:
        row = self.bindings.set(row)
        a = self.e.agents.get(row["kernel"])
        if a is not None:
            self._bind(a)
        return row

    def journal(self, kind: str, row: dict) -> None:
        try:
            self.s.api_state.mkdir(parents=True, exist_ok=True, mode=0o700)
            p = self.s.api_state / f"api-{time.strftime('%Y-%m-%d', time.gmtime())}.jsonl"
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as fh:
                fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": kind,
                                     "runtime": config.RUNTIME, **row}, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def row(self, sid) -> dict:
        if not SESSION_ID.match(str(sid or "")):
            raise ApiError(400, "invalid_session_id")
        r = self.bindings.get(sid)
        if not r:
            raise ApiError(404, "unknown_session", "session.open first")
        return r

    def agent(self, row: dict):
        a = self.e.load(row["kernel"])
        if a is None:
            raise ApiError(404, "unknown_walter_session", f"the engine has no session {row['kernel']}")
        return a

    def view(self, row: dict, *, title: bool = False) -> dict:
        a = self.e.agents.get(row["kernel"])
        key = a.key if a is not None else self._key_of(row["kernel"])
        out = {"session_id": row["session_id"], "interface": row.get("interface"), "door": row.get("door"),
               "mode": row.get("mode"), "principal": row.get("principal"), "walter_session": key,
               "created_at": row.get("created_at"), **({"level": row["level"]} if row.get("level") else {})}
        if title:
            a = a or self.e.load(row["kernel"])
            out["title"] = (a.session.title() if a else None) or ""
            out["busy"] = bool(a and a.busy)
        return out

    def _key_of(self, kernel: str) -> str:
        try:
            with open(self.e.store.path(kernel), encoding="utf-8") as fh:
                return json.loads(fh.readline()).get("walter_key") or config.KEY_PREFIX + kernel
        except (OSError, ValueError):
            return config.KEY_PREFIX + kernel

    # ── ops ──
    async def op(self, body: dict, *, web: bool = False) -> dict:
        if not isinstance(body, dict) or body.get("version") != 1:
            raise ApiError(400, "version", "version must be 1")
        op = body.get("op")
        if op == "health":
            return self.health()
        if op == "session.open":
            return await self.open(body)
        if op == "session.list":
            rows = self.bindings.list(body.get("interface"), body.get("account"))
            views = [self.view(r, title=web) for r in rows]
            if web:
                views.sort(key=lambda v: v.get("created_at") or "", reverse=True)
            return {"sessions": views}
        if op == "turn.submit":
            return await self.submit(body, "queue", keyed=True)
        if op == "turn.queue":
            return await self.submit(body, "queue")
        if op == "turn.steer":
            return await self.submit(body, "steer")
        if op == "turn.result":
            return await self.result(body)
        if op == "turn.cancel":
            return self.cancel(body)
        if op == "approval.list":
            return {"approvals": [p["view"] for p in self.e.approvals.values()
                                  if not body.get("session_id") or p["view"]["session_id"] == body["session_id"]]}
        if op == "approval.answer":
            return self.answer(body)
        if op == "delegate":
            return await self.delegate(body)
        if op == "session.history":
            return self.history(body)
        if op == "session.rename":
            return self.rename(body)
        raise ApiError(400, "unknown_op")

    def health(self) -> dict:
        return {"ok": True, "version": 1, "sessions": len(self.bindings.rows), "pending_approvals": len(self.e.approvals),
                "engine": "walter", "mcp_tools": len(self.e.mcp.tools),
                "resumes_interrupted": bool(self.e.s.resume_interrupted)}   # a door says « je reprends », not « redis-moi »

    async def open(self, body: dict) -> dict:
        iface, conversation, principal = body.get("interface"), body.get("conversation"), body.get("principal")
        mode, permissions, cont, level = body.get("mode") or "interactive", body.get("permissions"), \
            body.get("continue_session"), body.get("level")
        if iface not in DOORS:
            raise ApiError(400, "invalid_interface")
        if not isinstance(principal, dict) or principal.get("kind") not in identity.KINDS:
            raise ApiError(400, "invalid_principal")
        if mode not in ("interactive", "command"):
            raise ApiError(400, "invalid_mode")
        try:
            resolved = identity.resolve(principal)
        except identity.IdentityError as e:
            raise ApiError(403 if e.code == "unknown_owner_account" else 400, e.code, str(e)) from None
        try:
            sid = session_id_of(iface, principal.get("id"), conversation)
        except ValueError as e:
            raise ApiError(400, "invalid_session_id", str(e)) from None
        door = effective_door(iface, mode)
        if permissions and permissions != PRESET_OF[door] and permissions != "command":
            raise ApiError(403, "permissions_wider_than_door", f"door {door} allows at most {PRESET_OF[door]}")
        final_door = "command" if permissions == "command" else door
        if level is not None and level not in LEVELS:
            raise ApiError(400, "invalid_level", "level L1|L2|L3")
        if level is not None and resolved["kind"] not in ("owner", "test"):
            raise ApiError(403, "owner_only")
        known = self.bindings.get(sid)
        if known:
            if known.get("door") != final_door:
                raise ApiError(409, "door_mismatch", f"session {sid} runs as {known.get('door')}")
            if known.get("principal") != resolved:
                known = self._set({**known, "principal": resolved})
            if level and known.get("level") != level:
                known = self._set({**known, "level": level})
            return {**self.view(known), "resumed": True}
        if cont:
            kernel = str(cont)
            for p in KEY_PREFIXES:
                kernel = kernel.removeprefix(p)
            target = self.e.load(kernel) if self.e.store.exists(kernel) else None
            if resolved["kind"] != "owner" and not (resolved["kind"] == "test" and target is not None and
                                                    (target.principal or {}).get("kind") == "test"):
                raise ApiError(403, "owner_only")
            if self.bindings.by_kernel(kernel):
                raise ApiError(409, "already_bound")
            if target is None:
                raise ApiError(404, "unknown_walter_session")
        else:
            kernel = self.e.create(cwd=str(self.s.workspace), door=final_door, principal=resolved,
                                   extra={"interface": iface, "engine_session": sid}).sid
        row = self._set({"session_id": sid, "kernel": kernel, "interface": iface, "door": final_door, "mode": mode,
                         "principal": resolved, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                         **({"level": level} if level else {})})
        self.journal("session.open", {"session_id": sid, "door": final_door, "continued": bool(cont),
                                      "principal_kind": resolved["kind"], **({"level": level} if level else {})})
        return {**self.view(row), "resumed": False}

    async def submit(self, body: dict, mode: str, keyed: bool = False) -> dict:
        row = self.row(body.get("session_id"))
        msg = body.get("message")
        text = msg.get("text") if isinstance(msg, dict) and isinstance(msg.get("text"), str) else ""
        if not text.strip():
            raise ApiError(400, "empty_message")
        if (body.get("channel") or "owner") not in ("owner", "machine", "test"):
            raise ApiError(400, "invalid_channel")
        key = body.get("idempotency_key")
        if keyed and not key:
            raise ApiError(400, "idempotency_key_required", "turn.submit needs the message id of its door (never run twice)")
        request_id = str(key) if key else str(uuid.uuid4())
        if not 8 <= len(request_id) <= 200:
            raise ApiError(400, "invalid_idempotency_key")
        a = self.agent(row)
        now = time.time()
        for k in [k for k, t in self.accepted.items() if now - t > 3600]:
            del self.accepted[k]
        seen = f"{row['kernel']} {request_id}"
        replay = bool(key) and seen in self.accepted
        if not replay:
            if key:
                self.accepted[seen] = now
            r = self.e.submit(a, text, request_id=request_id, mode=mode, source={"kind": "user"})
            replay = bool(r.get("replayed"))
        out = {"accepted": True, "session_id": row["session_id"], "request_id": request_id, "walter_session": a.key,
               "mode": mode, **({"replayed": True} if replay else {})}
        wait = body.get("wait_ms")
        if not wait:
            return out
        return {**out, "result": await self.watch(a, request_id, min(int(wait or 0), MAX_WAIT_MS))}

    async def result(self, body: dict) -> dict:
        row = self.row(body.get("session_id"))
        rid = body.get("request_id")
        if not rid:
            raise ApiError(400, "request_id_required")
        a = self.agent(row)
        return {"session_id": row["session_id"], "request_id": rid,
                "result": await self.watch(a, str(rid), min(int(body.get("wait_ms") or 0), MAX_WAIT_MS))}

    async def watch(self, a, request_id: str, wait_ms: int) -> dict:
        tw = TurnWatch(request_id)
        q: asyncio.Queue = asyncio.Queue()
        a.session.listeners.add(q.put_nowait)
        try:
            for ev in list(a.session.events):
                tw.feed(ev)
                if tw.done:
                    break
            deadline = time.monotonic() + wait_ms / 1000
            while not tw.done and wait_ms:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                try:
                    tw.feed(await asyncio.wait_for(q.get(), left))
                except asyncio.TimeoutError:
                    break
        finally:
            a.session.listeners.discard(q.put_nowait)
        return tw.result()

    def cancel(self, body: dict) -> dict:
        row = self.row(body.get("session_id"))
        if not body.get("reason"):
            raise ApiError(400, "reason_required")
        a = self.e.agents.get(row["kernel"])
        if a is None or not self.e.interrupt(a, str(body["reason"])[:200]):
            raise ApiError(409, "not_running", "the session has no turn running")
        self.journal("turn.cancel", {"session_id": row["session_id"]})
        return {"accepted": True, "session_id": row["session_id"]}

    def answer(self, body: dict) -> dict:
        rid, decision, principal = body.get("request_id"), body.get("decision"), body.get("principal")
        p = self.e.approvals.get(rid)
        if not p:
            raise ApiError(404, "unknown_request", "already answered, withdrawn or expired")
        if decision not in ("allow_once", "deny"):
            raise ApiError(400, "invalid_decision")
        try:
            who = identity.resolve(principal)
        except identity.IdentityError:
            raise ApiError(403, "not_the_owner") from None
        if not identity.acts_as_owner(who, p["principal"]) or who.get("id") != (p["principal"] or {}).get("id"):
            raise ApiError(403, "not_the_owner")
        self.e.answer(rid, decision)
        return {"accepted": True, "request_id": rid, "outcome": decision}

    async def delegate(self, body: dict) -> dict:
        d, caller = body.get("delegation"), body.get("caller") or "mcp"
        if not isinstance(d, dict) or d.get("version") != 1 or not isinstance(d.get("goal"), str) or not d["goal"].strip():
            raise ApiError(400, "invalid_delegation", "delegation.v1 with a goal")
        key = str(d.get("idempotency_key") or "")
        if not 8 <= len(key) <= 200:
            raise ApiError(400, "idempotency_key_required")
        model = None
        if d.get("model") is not None:
            m = d["model"]
            mid = m if isinstance(m, str) else (m or {}).get("id")
            prov = (m or {}).get("provider") if isinstance(m, dict) else None
            if not MODEL_ID.match(str(mid or "")) or (prov is not None and not MODEL_ID.match(str(prov))):
                raise ApiError(400, "invalid_model", "model {id, provider?}")
            model = {"id": mid, **({"provider": prov} if prov else {})}
            v = await self.e.doors.validate_model(model)
            if not v.get("ok"):
                raise ApiError(422, "model_unavailable", v.get("error") or "refused by Walter Router")
        parent = d.get("parent") or {}
        try:
            depth = int(parent.get("depth", 0) or 0)
        except (TypeError, ValueError):
            raise ApiError(400, "invalid_depth") from None
        if depth < 0:
            raise ApiError(400, "invalid_depth")
        if depth >= self.s.max_depth:
            raise ApiError(403, "max_depth", f"delegation depth {depth} reaches the limit {self.s.max_depth}")
        if not PART.match(str(caller)):
            raise ApiError(400, "invalid_principal")
        level = d.get("level")
        if level is not None and level not in ("L1", "L2", "L3"):
            raise ApiError(400, "invalid_level", "level L1, L2 or L3")
        conversation = "task-" + hashlib.sha256(key.encode()).hexdigest()[:24]
        opened = await self.open({"interface": "mcp", "conversation": conversation,
                                  "principal": {"kind": "machine", "id": caller}, "mode": "interactive",
                                  **({"level": level} if level else {})})
        row = self.bindings.get(opened["session_id"])
        if not row.get("unattended"):
            row = self._set({**row, "unattended": True,
                             "parent": {"run_id": parent.get("run_id"), "session_id": parent.get("session_id"),
                                        "task_id": parent.get("task_id"), "depth": depth},
                             "goal_sha": hashlib.sha256(d["goal"].encode()).hexdigest()[:16], **({"model": model} if model else {})})
        a = self.agent(row)
        if not opened["resumed"] and not model and d.get("task") and d["task"] != "auto" and d["task"] in self.s.models:
            self.e.set_model(a, d["task"])
        budget_ms = max(60, min(int(d.get("budget_seconds") or 900), 3600)) * 1000
        r = await self.submit({"session_id": opened["session_id"], "message": {"text": mission(d)}, "channel": "machine",
                               "idempotency_key": key, "wait_ms": budget_ms}, "queue", keyed=True)
        res = r["result"]
        if not res["done"]:
            self.e.interrupt(a, "budget_seconds")
            res = {**res, "status": "cancelled", "reason": "budget_seconds"}
        self.journal("delegate", {"session_id": opened["session_id"], "caller": caller, "depth": depth,
                                  "status": res["status"], "tools": len(res["tools"])})
        return {"ok": res["status"] == "ok" and bool(res["text"]), "output": res["text"], "status": res["status"],
                "reason": res["reason"], **({"error": res["error"]} if res.get("error") else {}), "tools": res["tools"],
                "session_id": opened["session_id"], "walter_session": opened["walter_session"], "request_id": key,
                "resumed": opened["resumed"], **({"model": model} if model else {})}

    # ── web additions ──
    def history(self, body: dict) -> dict:
        row = self.row(body.get("session_id"))
        a = self.agent(row)
        limit = max(1, min(int(body.get("limit") or 200), 1000))
        before = body.get("before_seq")
        raw = [e for e in a.session.events if before is None or e["seq"] < int(before)]
        out, first = [], None
        for e in reversed(raw):
            ce = to_client_event(e, rich=True)
            if ce is None:
                continue
            out.append(ce)
            first = e["seq"]
            if len(out) >= limit:
                break
        out.reverse()
        if len(out) < limit:
            first = 0
        return {"events": out, "first_seq": first or 0, "last_seq": a.session.seq, "busy": a.busy,
                "title": a.session.title() or ""}

    def rename(self, body: dict) -> dict:
        row = self.row(body.get("session_id"))
        title = " ".join(str(body.get("title") or "").split())[:120]
        if not title:
            raise ApiError(400, "invalid_title")
        a = self.agent(row)
        a.session.append("session/title", {"title": title, "by": "owner"})
        return {"ok": True, "session_id": row["session_id"], "title": title}

    # ── live ──
    def _emit(self, engine_session: str, event: dict) -> None:
        for fn in list(self.listeners):
            try:
                fn(engine_session, {**event, "at": int(time.time() * 1000)})
            except Exception:  # noqa: BLE001
                pass

    async def events(self, sid: str, since_seq: int | None, stop: asyncio.Event, *, rich: bool = False):
        """Client events of one session: journal events after `since_seq` (live only when absent), the live-only
        events of a running turn (web: text deltas), approval notices."""
        row = self.row(sid)
        a = self.agent(row)
        q: asyncio.Queue = asyncio.Queue()
        on_journal = lambda ev: q.put_nowait(("j", ev))                      # noqa: E731
        on_live = lambda ev: q.put_nowait(("l", ev))                         # noqa: E731
        on_notice = lambda s, ev: q.put_nowait(("n", ev)) if s == sid else None  # noqa: E731
        a.session.listeners.add(on_journal)
        if rich:
            a.live.add(on_live)
        self.listeners.add(on_notice)
        last = a.session.seq if since_seq is None else int(since_seq)
        try:
            if since_seq is not None:
                for ev in a.session.since(last):
                    ce = to_client_event(ev, rich=rich)
                    last = ev["seq"]
                    if ce:
                        yield ce
            for p in list(self.e.approvals.values()):
                if p["view"]["session_id"] == sid:
                    yield {"type": "approval.requested", **p["view"]}
            while not stop.is_set():
                getter = asyncio.ensure_future(q.get())
                stopper = asyncio.ensure_future(stop.wait())
                done, _ = await asyncio.wait({getter, stopper}, return_when=asyncio.FIRST_COMPLETED)
                stopper.cancel()
                if getter not in done:
                    getter.cancel()
                    return
                kind, ev = getter.result()
                if kind == "j":
                    if ev["seq"] <= last:
                        continue
                    last = ev["seq"]
                    ce = to_client_event(ev, rich=rich)
                    if ce:
                        yield ce
                else:
                    yield ev
        finally:
            a.session.listeners.discard(on_journal)
            a.live.discard(on_live)
            self.listeners.discard(on_notice)
