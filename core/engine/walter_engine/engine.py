"""Walter Engine — the native runtime (2026-11-17, mission « Walter Native Engine »).

Walter owns its execution: no DSH/Cordis process, package or runtime component. One asyncio process runs every
conversation of the instance (owner sessions of every door, API delegations, sub-agents) as Agents over their
journals (`journal.py`); it reaches every other responsibility through that module's declared door (`walter.py`):

  a turn    = intake (Run Plane run, Context's plan + pack, skills) → window (walter-context) → model steps through
              walter-llm (the Router chooses and executes the model) → tools under Walter's policy → end (run closed,
              bus `turn.ended`, Context's living state told) → the next queued input;
  a step    = budget verdict (the effort Context stated) → steering and notices that arrived → one model call →
              its tool calls (read-only ones together, the others one at a time) → targeted reassessment when a
              trigger asks for it (§7: a failure, a sub-agent's answer, a job's end) — never a full preflight;
  durable   = a turn interrupted by a restart is closed `interrupted`, its calls in flight get an explicit « résultat
              inconnu », and (by default) the session resumes from its journal with a notice saying so: nothing that
              had an external effect is ever re-executed by the engine itself; background jobs that were running are
              reported `lost` with their idempotency contract.

The engine's job is execution and continuity; the plan (Context), the model (Router), the memory (Memory), the
skills (Skills) and the rules (Security's policy) stay where they are decided.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

from . import config, identity, journal
from .jobs import Job, Jobs
from .llm import Answer, Client, LLMError
from .policy import Policy
from .tools import Exec, Registry, Result, as_result, clip, elapsed_ms, parse_args
from .tools import agents as agent_tools
from .tools import builtin
from .tools.mcp import PREFIX as MCP_PREFIX, McpClient
from .tools.python import PythonHost
from .walter import Doors

log = logging.getLogger("walter_engine")

HEADER = ("Mémoire W.Alter (injectée automatiquement pour ce message ; souvenirs datés : réponds à partir d'eux en citant "
          "la date, le plus récent l'emporte ; si l'état réel compte et que tu as les outils, vérifie-le ; approfondir "
          "avec memory_search / person_lookup) :")
DEGRADED = ("Contexte dégradé : la préparation du contexte n'a pas répondu, l'intention de ce message n'a pas pu être "
            "évaluée. Ce qui suit est une sélection mémoire par défaut : vérifie avec les outils mémoire si la demande en dépend.")
NOTICE = ("Budget de ce tour atteint (Walter) : conclus maintenant avec ce que tu as déjà, sans nouvel appel "
          "d'outil ; dis clairement ce qui reste à faire.")
UNKNOWN = "[résultat inconnu : le moteur a redémarré pendant cet appel ; vérifier l'état réel avant de le refaire]"
MACHINE_PROMPTS = ("<task-notification", "[SYSTEM NOTIFICATION", "Another Claude session sent a message",
                   "<cross-session-message", "<side-sessions-event>", "<ci-monitor-event>", "[Subagent hand-back]",
                   "<system-reminder", "[ASYNC DELEGATION", "[CONTEXT COMPACTION", "[System:", "[SYSTEM:")
REQUEST_KINDS = ("user", "mission")          # a message that is a request (intake + plan); others are notices
RANK = ["L0", "L1", "L2", "L3", "L4"]
SECRET_ENV = ("WALTER_LLM_TOKEN", "WALTER_MEMORY_GATEWAY_TOKEN", "WALTER_ENGINE_API_TOKEN")
OUTPUT_RESERVE = 32_000
IMAGE_TURNS = 1                              # images are sent to the model for the turn that attached them


def checkpoint_text(step: int, level: str | None) -> str:
    return (f"Point d'étape (Walter) : ce tour a déjà pris {step} étapes pour une demande dont l'effort a été évalué {level}. "
            "Si le résultat demandé est atteignable avec ce que tu as, conclus maintenant. Sinon dis en une phrase ce qui manque "
            "et continue uniquement là-dessus, sans retenter à l'identique une opération qui a déjà échoué.")


def machine_prompt(text: str) -> bool:
    head = (text or "").lstrip()[:400]
    return any(m in head for m in MACHINE_PROMPTS)


def sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def at_least(effort: str | None, pinned: str | None) -> str | None:
    if not pinned or (effort in RANK and RANK.index(effort) >= RANK.index(pinned)):
        return effort
    return pinned


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


class Agent:
    """One conversation the engine runs (an owner session of any door, an API delegation, a sub-agent)."""

    def __init__(self, engine: "Engine", session: journal.Session):
        h = session.header
        self.engine = engine
        self.session = session
        self.sid = session.id
        self.key = h.get("walter_key") or config.KEY_PREFIX + self.sid
        self.cwd = h.get("cwd") or str(engine.s.workspace)
        self.depth = int(h.get("depth") or 0)
        self.parent_sid = h.get("parent")
        self.root_sid = h.get("root") or (self.sid if not self.parent_sid else self.parent_sid)
        self.description = h.get("description")
        self.model = h.get("model")
        self.effort = h.get("effort")
        # what the door that opened it says (Engine API binding; set again at every load by the API)
        self.meta: dict = {"door": h.get("door") or "web", "principal": h.get("principal") or {"kind": "owner", "id": "owner"},
                           "unattended": bool(h.get("unattended")), "parent_run_id": None, "model": None, "level": None,
                           "interface": None, "engine_session": None}
        # runtime
        self.task: asyncio.Task | None = None
        self.inbox: list[dict] = []
        self.steers: list[dict] = []
        self.cancel = asyncio.Event()
        self.run_id: str | None = None
        self.run_key: str | None = None
        self.plan: dict | None = None
        self.last: dict | None = None            # {run_id, channel, plan} of the last request turn (wake turns inherit)
        self.images: list[dict] = []
        self.live: set = set()                   # callables(event) for events that are not journaled (deltas, notices)
        self._sys: tuple[str, str] | None = None  # (day, system prompt)
        self._skills0: str | None = None
        self.turn_no: int | None = None
        self.step_no: int | None = None
        self.title_asked = bool(session.title())
        self.seen_requests: set | None = None
        self.pending_trigger: dict | None = None   # §7: what changed during execution, for a targeted reassessment
        self.fails: dict[str, int] = {}            # failures per tool in the running turn
        self.joined: list[asyncio.Future] = []     # waits of inputs that joined the running turn (steers)

    # ── who ──
    @property
    def busy(self) -> bool:
        return self.task is not None and not self.task.done()

    @property
    def door(self) -> str:
        return self.root().meta.get("door") or "web"

    @property
    def principal(self) -> dict:
        return self.root().meta.get("principal") or {"kind": "owner", "id": "owner"}

    @property
    def policy_door(self) -> str:
        """The door the policy judges under: a test account's conversation is judged under the `test` interface
        whatever door it came through (17/11: `e2e` on Telegram had the owner's preset, act_as_owner included)."""
        return "test" if (self.principal or {}).get("kind") == "test" else self.door

    @property
    def unattended(self) -> bool:
        return bool(self.meta.get("unattended") or self.root().meta.get("unattended"))

    def root(self) -> "Agent":
        a, n = self, 0
        while a.parent_sid and n < 16:
            p = self.engine.agents.get(a.parent_sid) or self.engine.load(a.parent_sid)
            if p is None:
                break
            a, n = p, n + 1
        return a

    def parent(self) -> "Agent | None":
        return self.engine.agents.get(self.parent_sid) if self.parent_sid else None

    def channel(self) -> str:
        if os.environ.get("WALTER_RUN_CHANNEL"):
            return os.environ["WALTER_RUN_CHANNEL"]
        if self.parent_sid:
            return "machine"
        ch = identity.channel_of(self.meta.get("principal"))
        return ch

    def attach_image(self, path: str, mime: str) -> None:
        self.images.append({"path": path, "mime": mime})

    def notify(self, event: dict) -> None:
        for fn in list(self.live):
            try:
                fn(event)
            except Exception:  # noqa: BLE001
                pass

    def requested(self) -> dict | None:
        m, lv = self.meta.get("model"), self.meta.get("level")
        req = {}
        if isinstance(m, dict) and m.get("id"):
            req["model"] = m["id"]
            if m.get("provider"):
                req["provider"] = m["provider"]
        if isinstance(lv, str) and re.fullmatch(r"L[1-3]", lv):
            req["pinned_level"] = lv
        return req or None


class Engine:
    def __init__(self, settings: config.Settings):
        self.s = settings
        self.s.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.store = journal.Store(settings.sessions_dir)
        self.registry = Registry()
        self.jobs = Jobs(settings.state / "jobs", on_settled=self._job_settled)
        self.doors = Doors(settings)
        self.llm = Client(settings)
        self.policy = Policy(settings, self.doors)
        self.mcp = McpClient(settings, self.registry)
        self.python = PythonHost(self, settings)
        self.agents: dict[str, Agent] = {}
        self.approvals: dict[str, dict] = {}
        self.approval_listeners: set = set()     # callables(sid, event): API SSE for approval notices
        self.ratio = 1 / 3.5                      # tokens per character, calibrated by the provider's usage
        self.deliverables = _read_json(settings.state / "deliverables.json", {})
        self.active_file = settings.state / "active.json"
        self.runs_file = settings.state / "open-runs.json"
        self.obs_dir = settings.state / "intake"
        self.started_at = time.time()
        self._mcp_task: asyncio.Task | None = None
        self.stopping = False
        self.binder = None                        # callable(agent): the doors' word on a session (Engine API bindings)

    # ── lifecycle ──
    async def start(self) -> None:
        builtin.register(self.registry)
        agent_tools.register(self.registry)
        self.registry.add(self.python.tool())
        self._mcp_task = asyncio.get_running_loop().create_task(self._mcp_up())
        await self._recover()

    async def _mcp_up(self) -> None:
        delay = 2.0
        while not self.stopping:
            try:
                await self.mcp.start()
                return
            except Exception as e:  # noqa: BLE001 — Walter tools come back when the server does
                log.warning("walter MCP unavailable (%s); retrying in %.0f s", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    async def stop(self) -> None:
        self.stopping = True
        for a in list(self.agents.values()):
            if a.busy:
                a.cancel.set()
        await self.jobs.shutdown()
        busy = [a.task for a in self.agents.values() if a.busy]
        if busy:
            await asyncio.wait(busy, timeout=10)
        for t in busy:
            if not t.done():
                t.cancel()
        await self.python.stop_all("engine stopping")
        await self.mcp.close()
        for p in self.approvals.values():
            if not p["future"].done():
                p["future"].set_result("cancelled")
        for a in self.agents.values():
            a.session.close()
        await self.doors.close()
        await self.llm.close()

    # ── sessions ──
    def load(self, sid: str) -> Agent | None:
        a = self.agents.get(sid)
        if a is not None:
            return a
        try:
            session = self.store.get(sid)
        except (KeyError, ValueError):
            return None
        a = Agent(self, session)
        for e in session.events:
            if e["type"] == "session/model":
                a.model = e["data"].get("model") or None
        self.agents[sid] = a
        if self.binder is not None:
            self.binder(a)
        return a

    def set_model(self, a: Agent, model: str | None) -> None:
        a.model = model or None
        a.session.append("session/model", {"model": a.model})

    def create(self, *, cwd: str | None = None, door: str = "web", principal: dict | None = None, depth: int = 0,
               parent: str | None = None, root: str | None = None, extra: dict | None = None) -> Agent:
        sid = journal.new_id()
        extra = {"walter_key": config.KEY_PREFIX + sid, "principal": principal, **({"root": root} if root else {}),
                 **(extra or {})}
        session = self.store.create(cwd=cwd or str(self.s.workspace), depth=depth, parent=parent, door=door,
                                    origin=(principal or {}).get("kind", "owner"), sid=sid, extra=extra)
        a = Agent(self, session)
        a.meta["door"], a.meta["principal"] = door, principal or a.meta["principal"]
        self.agents[sid] = a
        if self.binder is not None:
            self.binder(a)
        return a

    def spawn_child(self, parent: Agent, *, description: str, model: str | None, effort: str | None) -> Agent:
        return self.create(cwd=parent.cwd, door=parent.door, principal=parent.principal, depth=parent.depth + 1,
                           parent=parent.sid, root=parent.root().sid,
                           extra={"description": description, "model": model, "effort": effort,
                                  "unattended": parent.unattended, "parent_key": parent.key})

    # ── inputs ──
    def _requests_seen(self, a: Agent) -> set:
        if a.seen_requests is None:
            a.seen_requests = {e["data"].get("source", {}).get("rpcId") for e in a.session.events
                               if e["type"] == "user/message" and (e["data"].get("source") or {}).get("rpcId")}
        return a.seen_requests

    def submit(self, a: Agent, text: str, *, request_id: str | None = None, mode: str = "queue",
               source: dict | None = None, future: asyncio.Future | None = None) -> dict:
        """An input for the session: a new turn (idle), the next turn (queue), or the running turn's next step (steer).
        One request id is one input, always (a door redelivering it gets `replayed`)."""
        if request_id:
            seen = self._requests_seen(a)
            if request_id in seen or any(i.get("request_id") == request_id for i in a.inbox + a.steers):
                return {"replayed": True}
            seen.add(request_id)
        item = {"text": text, "request_id": request_id, "source": source or {"kind": "user"}, "future": future,
                "at": journal.now_ms()}
        if mode == "steer" and a.busy:
            a.steers.append(item)
        else:
            a.inbox.append(item)
            self._ensure(a)
        return {"replayed": False, "queued": a.busy and mode != "steer"}

    def steer(self, a: Agent, text: str, *, source: dict | None = None) -> None:
        self.submit(a, text, mode="steer", source=source or {"kind": "user"})

    def notice(self, a: Agent, text: str, kind: str) -> None:
        """A runtime notice (a job or a sub-agent settled, the engine restarted): read at the running turn's next step,
        or a wake-up turn of its own when the session is idle."""
        item = {"text": text, "request_id": None, "source": {"kind": kind}, "future": None, "at": journal.now_ms()}
        if a.busy:
            a.steers.append(item)
        else:
            a.inbox.append(item)
            self._ensure(a)

    def interrupt(self, a: Agent, reason: str = "") -> bool:
        if not a.busy:
            return False
        a.cancel.set()
        for c in [x for x in self.agents.values() if x.parent_sid == a.sid and x.busy]:
            self.interrupt(c, "parent interrupted")
        return True

    async def run_child(self, child: Agent, prompt: str, cancel: asyncio.Event | None = None) -> dict:
        fut = asyncio.get_running_loop().create_future()
        self.submit(child, prompt, request_id=f"mission-{uuid.uuid4().hex[:12]}", source={"kind": "mission"}, future=fut)
        await self.state_event(child.parent() or child, "subagent.started",
                               {"subagent_id": child.sid, "goal": (child.description or prompt)[:300]})
        if cancel is None:
            res = await fut
        else:
            stop = asyncio.ensure_future(cancel.wait())
            try:
                done, _ = await asyncio.wait({fut, stop}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                stop.cancel()
            if fut not in done:
                self.interrupt(child, "parent interrupted")
                res = await fut
            else:
                res = fut.result()
        parent = child.parent()
        if parent is not None:
            await self.state_event(parent, "subagent.reply", {"subagent_id": child.sid, "ok": res["status"] == "ok",
                                                              "text": (res["text"] or "")[:1500]})
            if res["status"] != "ok" and not parent.pending_trigger:
                parent.pending_trigger = {"kind": "failure", "where": f"sous-agent {child.description or child.sid}",
                                          "error": str(res.get("reason") or res["status"])}
        return res

    def _ensure(self, a: Agent) -> None:
        if self.stopping or a.busy:
            return
        a.task = asyncio.get_running_loop().create_task(self._drive(a), name=f"agent:{a.sid}")

    async def _drive(self, a: Agent) -> None:
        while a.inbox and not self.stopping:
            items, a.inbox = a.inbox, []
            try:
                await self._turn(a, items)
            except Exception as e:  # noqa: BLE001 — a defect of one turn never stops the session
                log.exception("turn of %s failed: %s", a.sid, e)
                for it in items:
                    if it.get("future") and not it["future"].done():
                        it["future"].set_result({"status": "error", "reason": "engine_error", "text": "", "tools": []})
            if a.steers:                      # arrived after the last step: they start the next turn
                a.inbox.extend(a.steers)
                a.steers = []

    # ── a turn ──
    async def _turn(self, a: Agent, items: list[dict], *, trigger: str | None = None) -> None:
        s = a.session
        turn = s.turns() + 1
        requests = [i for i in items if (i["source"] or {}).get("kind") in REQUEST_KINDS]
        trigger = trigger or ("request" if requests else "wake:" + ",".join(sorted({i["source"]["kind"] for i in items})))
        a.cancel = asyncio.Event()
        a.turn_no, a.step_no = turn, 0
        a.fails, a.joined = {}, []
        kinds = sorted({(i["source"] or {}).get("kind") for i in items})
        a.pending_trigger = None if requests else (
            {"kind": "interrupted", "reason": "engine_restart"} if "engine-restart" in kinds else
            {"kind": "info.arrived", "text": "\n".join(i["text"] for i in items)[:600]} if "subagent-settled" in kinds else None)
        tier0 = asyncio.ensure_future(self._skills_tier0(a)) if a._skills0 is None else None
        self._active(a.sid, True)
        t0 = time.monotonic()
        s.append("turn/start", {"turn": turn, "request_id": next((i["request_id"] for i in requests if i["request_id"]), None),
                                "trigger": trigger}, sync=True)
        for it in items:
            src = {k: v for k, v in (it["source"] or {}).items() if v is not None}
            if it.get("request_id"):
                src["rpcId"] = it["request_id"]
            s.append("user/message", {"text": it["text"], "turn": turn, "source": src})
        stats = {"steps": 0, "tool_calls": 0, "tool_errors": 0}
        status, reason, error = "ok", {"kind": "completed"}, None
        text = "\n\n".join(i["text"] for i in requests) if requests else ""
        try:
            if requests:
                run_id, plan, pack = await self._intake(a, turn, text, requests[0].get("request_id"))
            else:
                notice = "\n".join(i["text"] for i in items)
                run_id, plan = await self._wake(a, turn, notice, sorted({i["source"]["kind"] for i in items}))
                pack = ""
            a.run_id, a.plan = run_id, plan
            if tier0 is not None:
                await tier0
            if requests:
                await self._window(a, plan)
            if pack:
                src = {"kind": "walter-intake", **{k: plan[k] for k in ("thread", "act", "level") if plan and plan.get(k)},
                       **({"degraded": True} if plan and plan.get("degraded") else {})}
                s.append("user/message", {"text": pack, "turn": turn, "source": src})
            if requests and not a.parent_sid and a.channel() == "owner":
                asyncio.get_running_loop().create_task(self.state_event(a, "message.owner", {"text": text[:4000]}))
            if not a.title_asked and requests and a.depth == 0:
                a.title_asked = True
                asyncio.get_running_loop().create_task(self._title(a, text))
            status, reason = await self._steps(a, turn, plan, stats, t0)
        except asyncio.CancelledError:
            status, reason = "cancelled", {"kind": "aborted"}
            if self.stopping:
                raise
        except Exception as e:  # noqa: BLE001
            log.exception("turn %s/%s: %s", a.sid, turn, e)
            status, reason = "error", {"kind": "error", "error": {"code": type(e).__name__}}
            error = {"kind": type(e).__name__, "message": str(e)[:500]}
        finally:
            if not (self.stopping and status == "cancelled"):
                s.append("turn/end", {"turn": turn, "status": status, "reason": reason, "ms": int((time.monotonic() - t0) * 1000)},
                         sync=True)
                self._active(a.sid, False)
        final = self._turn_text(a, turn)
        tools = [e["data"].get("name") for e in s.events if e["type"] == "tool/call" and e["data"].get("turn") == turn
                 and not e["data"].get("nested")]
        res = {"status": status, "reason": reason.get("kind") if status != "ok" else None, "text": final, "tools": tools,
               **({"error": (reason.get("error") or {}).get("code")} if reason.get("error") else {})}
        for fut in [it.get("future") for it in items] + a.joined:
            if fut is not None and not fut.done():
                fut.set_result(res)
        a.joined = []
        if reason.get("why") == "budget" and not error:
            error = {"kind": "budget", "message": "the turn reached its ceiling and was stopped"}
        if status == "error" and reason.get("error") and not error:
            error = {"kind": str(reason["error"].get("code") or "error"), "message": str(reason["error"].get("status") or "")}
        if self.stopping and status == "cancelled":
            # cut by the engine stopping, not by the owner: the run stays open in the runs file with what its
            # continuation needs; the next process closes it `interrupted` (engine_restart: its objective is
            # suspended, never left « open » nor closed « cancelled ») and resumes the turn as its child (_recover)
            self._track_run(a, a.run_id, turn, carry=a.last)
            a.run_id = None
        else:
            await self._end_run(a, turn, status, stats, error)
        if status == "cancelled":
            await self.state_event(a, "interrupted", {"reason": "owner" if not self.stopping else "engine_stop"})

    def _turn_text(self, a: Agent, turn: int) -> str:
        for e in reversed(a.session.events):
            if e["type"] == "assistant/message" and e["data"].get("turn") == turn and (e["data"].get("text") or "").strip():
                return e["data"]["text"]
            if e["type"] == "turn/start" and e["data"].get("turn") == turn:
                break
        return ""

    def _ceilings(self, plan: dict | None) -> dict:
        b = self.s.budget or {}
        gen = {"level": None, "checkpoint": 0, "max_steps": int(b.get("max_steps", 80)),
               "max_ms": float(b.get("max_turn_min", 45)) * 60_000}
        name = (plan.get("effort") or plan.get("level")) if plan and not plan.get("degraded") and plan.get("channel") != "machine" else None
        lv = (b.get("levels") or {}).get(name) if name else None
        if not lv:
            return gen
        return {"level": name, "checkpoint": min(int(lv.get("checkpoint", 0)), gen["max_steps"]),
                "max_steps": min(int(lv.get("max_steps", gen["max_steps"])), gen["max_steps"]),
                "max_ms": min(float(lv.get("max_turn_min", gen["max_ms"] / 60_000)) * 60_000, gen["max_ms"])}

    def _verdict(self, c: dict, step: int, ms: float) -> str:
        b = self.s.budget or {}
        over_steps, over_time = step >= c["max_steps"], ms >= c["max_ms"]
        if not over_steps and not over_time:
            return "checkpoint" if c["checkpoint"] and step >= c["checkpoint"] else "go"
        grace = step >= c["max_steps"] + int(b.get("grace_steps", 3)) or ms >= c["max_ms"] + float(b.get("grace_min", 5)) * 60_000
        return "stop" if grace else "conclude"

    def _budget_record(self, row: dict) -> None:
        try:
            d = config.instance_root() / "state" / "core" / "engine" / "budget"
            d.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(d / f"budget-{_today()}.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as fh:
                fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runtime": config.RUNTIME,
                                     **row}) + "\n")
        except OSError:
            pass

    async def _steps(self, a: Agent, turn: int, plan: dict | None, stats: dict, t0: float) -> tuple[str, dict]:
        s = a.session
        c = self._ceilings(plan)
        checked = told = False
        overflow_retry = False
        while True:
            if a.cancel.is_set():
                return "cancelled", {"kind": "aborted"}
            step = (a.step_no or 0) + 1
            a.step_no = step
            ms = (time.monotonic() - t0) * 1000
            v = self._verdict(c, step, ms)
            no_tools = False
            row = {"session": a.sid, "turn": turn, "step": step, "ms": int(ms), "level": c["level"]}
            if v == "stop":
                self._budget_record({"action": "stop", **row})
                return "budget_exhausted", {"kind": "blocked", "why": "budget"}
            if v == "checkpoint" and not checked:
                checked = True
                self._budget_record({"action": "checkpoint", **row})
                s.append("user/message", {"text": checkpoint_text(step, c["level"]), "turn": turn, "source": {"kind": "walter-budget"}})
            if v == "conclude":
                no_tools = True
                if not told:
                    told = True
                    self._budget_record({"action": "conclude", **row})
                    s.append("user/message", {"text": NOTICE, "turn": turn, "source": {"kind": "walter-budget"}})
            self._drain_steers(a, turn)
            await self._reassess(a, turn)
            messages = await self._pressure(a)
            tools = None if no_tools else self.registry.schemas()
            stats["steps"] += 1
            try:
                ans = await self._call_model(a, messages, tools)
            except asyncio.CancelledError:
                if self.stopping:
                    raise
                return "cancelled", {"kind": "aborted"}
            except LLMError as e:
                if e.status == 400 and not overflow_retry and re.search(r"context|too long|token", e.detail or "", re.I):
                    overflow_retry = True
                    await self._window(a, a.plan, force=True)
                    a.step_no = step - 1
                    continue
                return "error", {"kind": "error", "error": {"code": e.code, "status": e.status}}
            if a.cancel.is_set() and not ans.text and not ans.tool_calls:
                return "cancelled", {"kind": "aborted"}
            s.append("assistant/message", {"turn": turn, "step": step, "text": ans.text, "reasoning": ans.reasoning[:20000] or None,
                                           "tool_calls": ans.tool_calls, "model": ans.model, "route": ans.route,
                                           "usage": ans.usage, "finish": ans.finish, "ms": ans.total_ms,
                                           "first_token_ms": ans.first_token_ms})
            if ans.usage.get("prompt_tokens") and messages:
                chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
                if chars:
                    self.ratio = 0.8 * self.ratio + 0.2 * (ans.usage["prompt_tokens"] / chars)
            if not ans.tool_calls:
                if a.steers and not a.cancel.is_set():
                    continue                       # a message arrived during the answer: the turn goes on
                return "ok", {"kind": "completed"}
            if no_tools:                           # the model called tools after being told to conclude: refused
                for call in ans.tool_calls:
                    s.append("tool/call", {"turn": turn, "step": step, "callId": call["id"], "name": call["name"],
                                           "arguments": call["arguments"]})
                    s.append("tool/result", {"turn": turn, "step": step, "callId": call["id"], "name": call["name"],
                                             "content": "refusé : budget du tour atteint, conclus sans nouvel appel d'outil",
                                             "isError": True})
                continue
            await self._run_tools(a, turn, step, ans.tool_calls, stats)
            if a.cancel.is_set():
                return "cancelled", {"kind": "aborted"}

    def _drain_steers(self, a: Agent, turn: int) -> None:
        while a.steers:
            it = a.steers.pop(0)
            src = {k: v for k, v in (it["source"] or {}).items() if v is not None}
            if it.get("request_id"):
                src["rpcId"] = it["request_id"]
            if src.get("kind") == "user":
                src["steer"] = True
            a.session.append("user/message", {"text": it["text"], "turn": turn, "source": src})
            if it.get("future") is not None:
                a.joined.append(it["future"])       # resolved with the turn it joined
            if src.get("kind") == "subagent-settled" and not a.pending_trigger:
                a.pending_trigger = {"kind": "info.arrived", "text": it["text"][:600]}

    async def _call_model(self, a: Agent, messages: list[dict], tools: list[dict] | None) -> Answer:
        model = a.model or self.s.model
        extra = {"reasoning_effort": a.effort} if a.effort else None
        ev = a.notify
        call = asyncio.ensure_future(self.llm.chat(messages=messages, tools=tools, model=model, run_id=a.run_id,
                                                   on_delta=lambda t: ev({"type": "message.delta", "text": t}),
                                                   cancel=a.cancel, extra=extra))
        stop = asyncio.ensure_future(a.cancel.wait())
        try:
            done, _ = await asyncio.wait({call, stop}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()
        if call not in done:
            call.cancel()
            raise asyncio.CancelledError()
        return call.result()

    # ── tools ──
    async def _run_tools(self, a: Agent, turn: int, step: int, calls: list[dict], stats: dict) -> None:
        s = a.session
        for call in calls:
            s.append("tool/call", {"turn": turn, "step": step, "callId": call["id"], "name": call["name"],
                                   "arguments": call["arguments"]})
        batch: list[dict] = []

        async def flush():
            if not batch:
                return
            await asyncio.gather(*(self._model_call(a, turn, step, c, stats) for c in batch))
            batch.clear()

        for call in calls:
            t = self.registry.tools.get(call["name"])
            if t is not None and t.parallel:
                batch.append(call)
                continue
            await flush()
            if a.cancel.is_set():
                self._result(a, turn, step, call, Result("[interrupted before it started]", True))
                continue
            await self._model_call(a, turn, step, call, stats)
        await flush()
        if a.images:
            imgs, a.images = a.images[:4], []
            s.append("user/message", {"text": "Image(s) jointe(s) : " + ", ".join(i["path"] for i in imgs), "turn": turn,
                                      "source": {"kind": "tool-image"}, "images": imgs})

    async def _model_call(self, a: Agent, turn: int, step: int, call: dict, stats: dict) -> None:
        args, err = parse_args(call["arguments"])
        stats["tool_calls"] += 1
        if err:
            res = Result(err, True)
        else:
            res = await self.execute_tool(a, call["name"], args, via="model", cancel=a.cancel, turn=turn, step=step,
                                          call_id=call["id"], journal_call=False)
        if res.is_error:
            stats["tool_errors"] += 1
        self._result(a, turn, step, call, res)

    def _result(self, a: Agent, turn, step, call: dict, res: Result) -> None:
        a.session.append("tool/result", {"turn": turn, "step": step, "callId": call["id"], "name": call["name"],
                                         "content": res.content, "isError": bool(res.is_error),
                                         **({"meta": res.meta} if res.meta else {})})

    async def execute_tool(self, a: Agent, name: str, args: dict, *, via: str = "model", cancel: asyncio.Event | None = None,
                           parent_call: str | None = None, turn: int | None = None, step: int | None = None,
                           call_id: str | None = None, journal_call: bool = True) -> Result:
        """The one path of every call (the model's, Python's `await tools.x()`, the API's): policy, approval, journal."""
        cancel = cancel or a.cancel
        tool = self.registry.tools.get(name)
        call_id = call_id or f"{via}-{uuid.uuid4().hex[:12]}"
        nested = journal_call
        if nested:
            a.session.append("tool/call", {"turn": turn, "step": step, "callId": call_id, "name": name, "nested": True,
                                           "via": via, "parentCall": parent_call,
                                           "arguments": json.dumps(args, ensure_ascii=False, default=str)[:20000]})
        t0 = time.monotonic()
        missing = [k for k in ((tool.parameters or {}).get("required") or ()) if args.get(k) in (None, "")] if tool else []
        if tool is None:
            res = Result(f"no tool named {name}" + ("" if self.mcp.tools else " (Walter tools are starting; try again)"), True)
        elif missing:                     # never run a tool on a guessed default (`read` without file_path = the cwd)
            props = ", ".join(sorted((tool.parameters or {}).get("properties") or {}))
            res = Result(f"{name}: missing required argument(s) {', '.join(missing)} (arguments: {props})", True,
                         meta={"invalid_arguments": missing})
        else:
            decision = await self.policy.judge(tool=name, args=args, door=a.policy_door, depth=a.depth)
            if decision["decision"] == "deny":
                res = Result(decision.get("reason") or "refusé par la politique Walter", True,
                             meta={"policy": decision.get("rule")})
            elif decision["decision"] == "ask" and (await self.approve(a, name, decision.get("reason") or "", cancel)) != "allowed-once":
                res = Result(f"refusé : {decision.get('reason') or 'accord de Monsieur requis'} — pas d'accord donné", True,
                             meta={"policy": decision.get("rule"), "approval": "rejected"})
            else:
                if name.startswith(MCP_PREFIX):
                    self._record_run(a)
                ex = Exec(engine=self, agent=a, call_id=call_id, name=name, cancel=cancel, turn=turn, step=step,
                          parent_call=parent_call, via=via)
                try:
                    res = as_result(await tool.run(args, ex))
                except asyncio.CancelledError:
                    if self.stopping:
                        raise
                    res = Result("[interrupted]", True)
                except Exception as e:  # noqa: BLE001 — a tool's defect is the model's information, never the turn's end
                    log.warning("tool %s failed: %s", name, e)
                    res = Result(f"{type(e).__name__}: {str(e)[:2000]}", True)
        res.meta = {**(res.meta or {}), "ms": elapsed_ms(t0)}
        if nested:
            a.session.append("tool/result", {"turn": turn, "step": step, "callId": call_id, "name": name, "nested": True,
                                             "via": via, "content": clip(res.content, 20000), "isError": bool(res.is_error)})
        short = name.removeprefix(MCP_PREFIX)
        if name != "python":
            asyncio.get_running_loop().create_task(self.state_event(
                a, "tool.result", {"tool": short, "ok": not res.is_error, "summary": res.content[:240] if res.is_error else "",
                                   "call_id": call_id}))
        if res.is_error and tool is not None and not (res.meta or {}).get("policy") and res.content != "[interrupted]":
            # §7: a tool that fails a second time in the same turn is a change worth a decision (one failure is
            # ordinary trial and error, and Context's gate never asks twice for the same failure in a session)
            a.fails[short] = a.fails.get(short, 0) + 1
            if a.fails[short] == 2 and not a.pending_trigger:
                a.pending_trigger = {"kind": "failure", "tool": short, "where": short, "error": res.content[:300]}
        return res

    def shell_env(self, a: Agent) -> dict:
        """The environment of a command the agent runs: the engine's, without the engine's own credentials, plus
        the run of the turn (Walter's CLIs file their work under it: walter_run, walter-telegram…)."""
        env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
        if not env.get("HOME") or env["HOME"] == "/":   # a unit without User= has no login environment: the
            import pwd                                  # shell's rc files (~/.local/bin/env…) would fail
            pw = pwd.getpwuid(os.getuid())
            env.update(HOME=pw.pw_dir, USER=env.get("USER") or pw.pw_name, LOGNAME=env.get("LOGNAME") or pw.pw_name)
        rid = a.run_id or a.root().run_id
        if rid:
            env["WALTER_RUN_ID"] = rid
        env["WALTER_SESSION_ID"] = a.key
        env["WALTER_DELEGATION_DEPTH"] = str(int(a.root().meta.get("delegation_depth") or 0) + a.depth)
        ch = a.channel()
        if ch in ("test", "machine"):
            env["WALTER_RUN_CHANNEL"] = ch
        return env

    async def error_skills(self, a: Agent, output: str, command: str) -> str:
        try:
            r = await self.doors.http.post(f"{config.SKILLS_URL}/v1/expose", timeout=4.0, json={
                "kind": "error", "message": output[-1500:], "context": command[:300], "session_id": a.key,
                "runtime": config.RUNTIME, "first_turn": False})
            return (r.json() or {}).get("text") or "" if r.status_code == 200 else ""
        except Exception:  # noqa: BLE001
            return ""

    def deliverable(self, a: Agent, path: str, title: str | None) -> str:
        token = hashlib.sha256(f"{a.sid}:{path}:{time.time()}:{os.urandom(8).hex()}".encode()).hexdigest()[:32]
        self.deliverables[token] = {"path": path, "session": a.sid, "at": time.time(), "title": title}
        _write_json(self.s.state / "deliverables.json", self.deliverables)
        url = f"/files/{token}/{Path(path).name}"
        a.session.append("deliverable", {"url": url, "title": title or Path(path).name, "path": path, "turn": a.turn_no})
        return url

    # ── approvals ──
    async def approve(self, a: Agent, tool: str, reason: str, cancel: asyncio.Event) -> str:
        root = a.root()
        if root.door == "command" or a.unattended:
            a.session.append("approval/decided", {"tool": tool, "outcome": "rejected", "why": "nobody to ask"})
            return "rejected"
        rid = str(uuid.uuid4())
        view = {"request_id": rid, "session_id": root.meta.get("engine_session") or root.sid, "tool": tool,
                "reason": reason or None, "child": a is not root, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        fut = asyncio.get_running_loop().create_future()
        self.approvals[rid] = {"view": view, "future": fut, "principal": root.principal, "sid": root.sid}
        a.session.append("approval/asked", {"request_id": rid, "tool": tool, "reason": reason})
        self._approval_event(root, {"type": "approval.requested", **view})
        stop = asyncio.ensure_future(cancel.wait())
        try:
            done, _ = await asyncio.wait({fut, stop}, timeout=self.s.approval_timeout_s, return_when=asyncio.FIRST_COMPLETED)
            outcome = fut.result() if fut in done else ("cancelled" if stop in done else "rejected")
        finally:
            stop.cancel()
            self.approvals.pop(rid, None)
        a.session.append("approval/decided", {"request_id": rid, "tool": tool, "outcome": outcome})
        self._approval_event(root, {"type": "approval.answered", "request_id": rid, "outcome": outcome,
                                    "decision": "allow_once" if outcome == "allowed-once" else "deny"})
        return outcome

    def answer(self, rid: str, decision: str) -> str:
        p = self.approvals.get(rid)
        if not p:
            raise KeyError(rid)
        outcome = "allowed-once" if decision == "allow_once" else "rejected"
        if not p["future"].done():
            p["future"].set_result(outcome)
        return outcome

    def _approval_event(self, root: Agent, ev: dict) -> None:
        sid = root.meta.get("engine_session") or root.sid
        for fn in list(self.approval_listeners):
            try:
                fn(sid, ev)
            except Exception:  # noqa: BLE001
                pass

    # ── Run Plane, Context, Skills ──
    def _observe(self, row: dict) -> None:
        try:
            self.obs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(self.obs_dir / f"observations-{_today()}.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as fh:
                fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runtime": config.RUNTIME,
                                     **row}) + "\n")
        except OSError:
            pass

    def _origin(self, a: Agent, request_id: str | None = None, trigger: str | None = None) -> dict:
        return {"channel": a.channel(), "runtime": config.RUNTIME, "session_id": a.key,
                **({"interface": a.root().meta["interface"]} if a.root().meta.get("interface") else {}),
                **({"engine_session": a.root().meta["engine_session"]} if a.root().meta.get("engine_session") else {}),
                **({"request_id": str(request_id)[:200]} if request_id else {}),
                **({"trigger": trigger[:200]} if trigger else {})}

    def _parent_run(self, a: Agent) -> str | None:
        if a.meta.get("parent_run_id"):
            return a.meta["parent_run_id"]
        p = a.parent()
        return p.run_id if p else None

    async def _open_run(self, a: Agent, body: dict, turn: int) -> dict | None:
        try:
            run = await self.doors.run_start(body)
            a.run_key = body.get("dedupe_key")
            self._track_run(a, run.get("run_id"), turn)
            self._record_run(a, run.get("run_id"))
            return run
        except Exception as e:  # noqa: BLE001
            log.warning("runs/start for %s failed: %s", a.sid, type(e).__name__)
            return None

    async def _intake(self, a: Agent, turn: int, message: str, request_id: str | None) -> tuple[str | None, dict | None, str]:
        t0 = time.monotonic()
        channel = a.channel()
        if channel == "owner" and machine_prompt(message):
            channel = "machine"
        skills = asyncio.ensure_future(self.doors.skills(message, a.key))
        key = f"{a.key}:{turn}:1:{sha16(message)}"
        prev = a.last
        req = a.requested()
        body = {"origin": {**self._origin(a, request_id), "channel": channel}, "goal": message, "dedupe_key": key,
                **({"parent_run_id": self._parent_run(a)} if self._parent_run(a) else {}),
                "cancel_run_id": prev["run_id"] if prev and prev.get("run_id") and prev.get("key") != key and prev.get("open") else None,
                "routing": {"applied": False, "configured": True, "via": "walter-llm poste (Walter Engine)",
                            **({"requested": req} if req else {})}}
        run = await self._open_run(a, body, turn)
        run_ms = int((time.monotonic() - t0) * 1000)
        local = (run or {}).get("privacy_class") == "local_only"
        plan, source, mem = None, "none", ""
        previous = None if local else self._last_exchange(a)
        t1 = time.monotonic()
        if not local:
            try:
                out = await self.doors.preflight({
                    "turn_id": f"{a.key}:{journal.now_ms()}", "message": message[:6000], "previous": previous,
                    "runtime": config.RUNTIME, "session_id": a.key, "privacy_class": "cloud_allowed",
                    "run_id": (run or {}).get("run_id"), "exclude_blocks": ["capabilities"], "answer_within_ms": 7000,
                    **({"channel": "machine"} if channel == "machine" else {})}, timeout_s=8.0)
                if out.get("error") or not out.get("plan"):
                    raise RuntimeError(out.get("error") or "no plan")
                p = out["plan"]
                degraded = bool(out.get("degraded") or (p.get("decision") or {}).get("degraded"))
                dec = p.get("decision") or {}
                plan = {"thread": (p.get("thread") or {}).get("id"), "act": p.get("act"), "level": p.get("level"),
                        "task": (p.get("model_profile") or {}).get("task"), "model_level": (p.get("model_profile") or {}).get("level"),
                        "effort": at_least(dec.get("effort") or p.get("level"), a.meta.get("level")) if a.meta.get("level")
                        else dec.get("effort"), "degraded": degraded, "channel": channel}
                source = "pack_degraded" if degraded else "pack"
                mem = out.get("text") or ""
            except Exception as e:  # noqa: BLE001
                source = "legacy_degraded"
                plan = {"thread": None, "act": None, "level": None, "degraded": True, "channel": channel}
                rid = (run or {}).get("run_id")
                asyncio.get_running_loop().create_task(self.doors.emit(
                    "context.degraded", a.key, {"run_id": rid, "stage": "preflight_unreachable", "reason": type(e).__name__},
                    dedupe_key=f"context.degraded/{rid}" if rid else None))
                legacy = await self._legacy(a, message, channel)
                mem = f"{DEGRADED}\n\n{legacy}" if legacy else ("" if channel == "machine" else DEGRADED)
        else:
            source = "legacy"
            mem = await self._legacy(a, message, channel)
        memory_ms = int((time.monotonic() - t1) * 1000)
        try:
            sk = await asyncio.wait_for(skills, 5)
        except Exception:  # noqa: BLE001
            sk = ""
        a.last = {"run_id": (run or {}).get("run_id"), "key": key, "channel": channel, "plan": plan, "open": True}
        self._observe({"kind": "intake", "session": a.key, "turn": turn, "message_sha": sha16(message[:6000]),
                       "run_id": (run or {}).get("run_id"), "privacy_class": (run or {}).get("privacy_class"),
                       "run_outcome": "delivered" if run else "failed", "context_source": source,
                       "previous_sent": previous is not None,
                       "level": (plan or {}).get("level"), "effort": (plan or {}).get("effort"),
                       "memory_chars": len(mem), "skills_chars": len(sk), "run_ms": run_ms, "memory_ms": memory_ms,
                       "native_ms": int((time.monotonic() - t0) * 1000)})
        parts = [x for x in (mem, sk) if x]
        return (run or {}).get("run_id"), plan, ("<walter-context>\n" + "\n\n".join(parts) + "\n</walter-context>") if parts else ""

    async def _legacy(self, a: Agent, message: str, channel: str) -> str:
        if channel == "machine" or len(message.split()) < 4 or message.startswith("/"):
            return ""
        text = (await self.doors.context_legacy({
            "query": message[:4000], "budget": {"profile": 0, "people": 300, "knowledge": 600, "evidence": 300},
            "include_profile": False, "caller": f"{config.RUNTIME}-hook", "mode": "on", "session_id": a.key,
            "cloud_safe": True})).strip()
        return f"{HEADER}\n{text}" if text else ""

    async def _wake(self, a: Agent, turn: int, notice: str, kinds: list[str]) -> tuple[str | None, dict | None]:
        last = a.last or {}
        inherited = last.get("plan")
        channel = os.environ.get("WALTER_RUN_CHANNEL") or last.get("channel") or a.channel()
        req = {**({"task": inherited["task"]} if inherited and inherited.get("task") else {}),
               **({"level": inherited["model_level"]} if inherited and inherited.get("model_level") else {}),
               **(a.requested() or {})}
        key = f"{a.key}:{turn}:1:{sha16(notice)}"
        parent_run = last.get("run_id") or self._parent_run(a)
        body = {"origin": {**self._origin(a, trigger=f"wake:{','.join(kinds)}"), "channel": channel},
                "goal": notice[:2000], "dedupe_key": key, **({"parent_run_id": parent_run} if parent_run else {}),
                "routing": {"applied": False, "configured": True, "via": "walter-llm poste (Walter Engine)", "trigger": "wake",
                            **({"requested": req} if req else {})}}
        run = await self._open_run(a, body, turn)
        self._observe({"kind": "wake", "session": a.key, "turn": turn, "notice": kinds, "notice_sha": sha16(notice),
                       "run_id": (run or {}).get("run_id"), "parent_run_id": parent_run, "inherited": bool(inherited)})
        if run:
            a.last = {**last, "run_id": run.get("run_id"), "key": key, "channel": channel, "open": True}
        return (run or {}).get("run_id"), ({**inherited, "wake": True, "channel": channel} if inherited else None)

    async def _end_run(self, a: Agent, turn: int, status: str, stats: dict, error: dict | None) -> None:
        run_id = a.run_id
        a.run_id = None
        if a.last:
            a.last["open"] = False
        self._track_run(a, None, turn)
        if not run_id:
            return
        st = {"ok": "ended", "cancelled": "cancelled"}.get(status, "failed")      # a budget stop is a failed run
        outcome = {"status": {"ended": "ok", "cancelled": "cancelled", "failed": "failed"}[st], **stats}
        if error:
            outcome["error"] = {"kind": str(error.get("kind") or "error")[:80], "message": str(error.get("message") or "")[:500]}
        await self.doors.run_end(run_id, a.key, st, outcome)
        await self.doors.emit("turn.ended", a.key, {"run_id": run_id, "turn": turn, "status": st, "outcome": outcome["status"]},
                              dedupe_key=f"turn.ended/{run_id}")

    def _track_run(self, a: Agent, run_id: str | None, turn: int | None, carry: dict | None = None) -> None:
        rows = _read_json(self.runs_file, {})
        if run_id:
            rows[a.key] = {"run_id": run_id, "turn": turn, "pid": os.getpid(), "at": journal.now_ms(),
                           **({"last": {k: carry.get(k) for k in ("channel", "plan")}} if carry else {})}
        else:
            rows.pop(a.key, None)
        try:
            _write_json(self.runs_file, rows)
        except OSError:
            pass

    def _record_run(self, a: Agent, run_id: str | None = None) -> None:
        """The run record the walter MCP server (a child of this process) reads back (hooks/runctx.py)."""
        rid = run_id or a.run_id or (a.root().run_id)
        if not rid:
            return
        d = config.instance_root() / "state" / "runs" / "current"
        try:
            _write_json(d / f"{os.getpid()}.json", {"run_id": rid, "session_id": a.key, "runtime": config.RUNTIME, "at": time.time()})
        except OSError:
            pass

    async def state_event(self, a: Agent, kind: str, payload: dict) -> None:
        thread = (a.plan or {}).get("thread") or ((a.last or {}).get("plan") or {}).get("thread")
        await self.doors.state_event(a.key, kind, payload, thread_id=thread, run_id=a.run_id)

    async def _reassess(self, a: Agent, turn: int) -> None:
        """§7: a targeted reassessment when something changed during execution (never a full preflight). Context's
        gate answers `asked: false` at once when nothing relevant changed; a decision that changes the plan is said
        to the agent before its next step."""
        trig = getattr(a, "pending_trigger", None)
        a.pending_trigger = None
        if not trig or not a.run_id:
            return
        thread = (a.plan or {}).get("thread")
        res = await self.doors.reassess({"session_id": a.key, "run_id": a.run_id, "trigger": trig,
                                         **({"thread_id": thread} if thread else {})})
        self._observe({"kind": "reassess", "session": a.key, "turn": turn, "trigger": trig.get("kind"),
                       "asked": bool(res.get("asked")), "reason": str(res.get("reason") or "")[:120],
                       "memoized": res.get("memoized"), "ms": res.get("ms")})
        if res.get("asked") and (res.get("text") or "").strip():
            a.session.append("user/message", {"text": res["text"].strip(), "turn": turn, "source": {"kind": "walter-state"}})

    async def _title(self, a: Agent, text: str) -> None:
        if not a.run_id:
            return
        try:
            ans = await asyncio.wait_for(self.llm.chat(messages=[
                {"role": "system", "content": "Tu donnes un titre court (5 mots au plus, sans ponctuation finale, dans la langue "
                                              "du message) à une conversation. Réponds par le titre seul."},
                {"role": "user", "content": text[:2000]}], tools=None, model="summarization", run_id=a.run_id,
                max_tokens=40), 30)
            title = " ".join(ans.text.strip().strip('"«»').split())[:80]
            if title:
                a.session.append("session/title", {"title": title})
        except Exception as e:  # noqa: BLE001
            log.info("title for %s: %s", a.sid, type(e).__name__)

    def _last_exchange(self, a: Agent, limit: int = 1200) -> dict | None:
        ended, answer, message, thread = None, "", "", None
        for e in reversed(a.session.events):
            t = e["type"]
            if ended is None:
                if t == "turn/end":
                    ended = e["time"]
                continue
            if t == "turn/start":
                break
            d = e["data"]
            if t == "assistant/message" and not answer and (d.get("text") or "").strip():
                answer = d["text"].strip()
            elif t == "user/message":
                kind = (d.get("source") or {}).get("kind")
                if kind == "walter-intake" and d["source"].get("thread"):
                    thread = str(d["source"]["thread"])
                if kind == "user":
                    message = (d.get("text") or "").strip() + (f"\n{message}" if message else "")
        if ended is None or (not message and not answer):
            return None
        return {"message": message[:limit], "answer": answer[:limit], "age_s": max(0, round((journal.now_ms() - ended) / 1000)),
                "thread_id": thread}

    # ── what the model sees ──
    def _system(self, a: Agent) -> str:
        day = _today()
        if a._sys and a._sys[0] == day:
            return a._sys[1]
        parts = []
        if self.s.instructions:
            try:
                parts.append(Path(self.s.instructions).read_text().strip())
            except OSError:
                pass
        env = [f"- Date : {day} (UTC)", f"- Dossier de travail : {a.cwd}", f"- Session Walter : {a.key}",
               f"- Porte : {a.door}"]
        if a.depth:
            env.append(f"- Tu es un sous-agent (profondeur {a.depth}) : ta réponse finale est rendue à l'agent qui t'a "
                       "délégué la tâche, pas à Monsieur.")
        parts.append("## Environnement\n" + "\n".join(env))
        parts.append(f"Cette session est journalisée dans la mémoire W.Alter (core.events, source {config.RUNTIME}, "
                     f"thread_id={a.sid}).")
        if a._skills0:
            parts.append(a._skills0)
        if self.mcp.instructions:
            parts.append(self.mcp.instructions.strip())
        text = "\n\n".join(p for p in parts if p)
        a._sys = (day, text)
        return text

    async def _skills_tier0(self, a: Agent) -> None:
        if a._skills0 is not None:
            return
        try:
            r = await self.doors.http.post(f"{config.SKILLS_URL}/v1/expose", timeout=4.0, json={
                "kind": "session_start", "message": "", "context": "", "session_id": a.key, "runtime": config.RUNTIME,
                "first_turn": True})
            a._skills0 = ((r.json() or {}).get("text") or "") if r.status_code == 200 else ""
        except Exception:  # noqa: BLE001
            a._skills0 = ""
        a._sys = None

    def _turn_start_seq(self, a: Agent) -> int:
        for e in reversed(a.session.events):
            if e["type"] == "turn/start":
                return e["seq"]
        return 0

    def _messages(self, a: Agent) -> list[dict]:
        live_from = self._turn_start_seq(a)
        limit, head, tail = self.s.tool_result_chars, self.s.tool_result_head, self.s.tool_result_tail

        def prune(ev: dict) -> str:
            c = ev["data"].get("content") or ""
            if ev["seq"] >= live_from:
                return clip(c, 60_000)
            if len(c) <= limit:
                return c
            return (f"{c[:head]}\n… [résultat réduit : {len(c)} caractères ; context_recover(ref=\"{ev['data'].get('callId')}\") "
                    f"rend l'original] …\n{c[-tail:]}")

        out = [{"role": "system", "content": self._system(a)}]
        for seq, m in journal.surface(a.session, prune=prune):
            imgs = m.pop("_images", None)
            if imgs and seq >= live_from:
                parts = [{"type": "text", "text": m.get("content") or ""}]
                for im in imgs:
                    try:
                        data = base64.b64encode(Path(im["path"]).read_bytes()).decode()
                        parts.append({"type": "image_url", "image_url": {"url": f"data:{im['mime']};base64,{data}"}})
                    except OSError:
                        parts.append({"type": "text", "text": f"[image illisible : {im['path']}]"})
                m["content"] = parts
            out.append(m)
        return out

    def _tokens(self, text: str) -> int:
        return int(len(text) * self.ratio) + 1

    async def _pressure(self, a: Agent) -> list[dict]:
        """The messages of the next model call; past 85 % of the window, Context is asked for a window first."""
        budget = max(0, self.s.context_window - OUTPUT_RESERVE)
        msgs = self._messages(a)
        est = int(sum(len(json.dumps(m, ensure_ascii=False)) for m in msgs) * self.ratio)
        if est > 0.85 * budget:
            rep = await self._window(a, a.plan, force=True)
            if rep.get("applied"):
                msgs = self._messages(a)
        return msgs

    async def _window(self, a: Agent, plan: dict | None, force: bool = False) -> dict:
        """walter-context decides the window of the session from its ORIGINAL turns (its bridge, op `window`); the
        engine applies it as a `compaction/window` event (the journal keeps every original)."""
        t0 = time.monotonic()
        s = a.session
        win = s.last_window()
        cut = int(win["data"].get("cut_seq", -1)) if win else -1
        originals, turn, live = [], 0, None
        for e in s.events:
            t = e["type"]
            if t == "turn/start":
                turn += 1
                live = turn
                continue
            if t == "turn/end":
                live = None
                continue
            if t not in journal.MESSAGE_TYPES or e["data"].get("nested"):
                continue
            m = journal.message_of(e)
            if m is None:
                continue
            m.pop("_images", None)
            content = m.get("content") or ""
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            if m["role"] == "tool" and len(content) > 800:
                content = f"{content[:400]}\n{content[-400:]}"
            src = (e["data"].get("source") or {}) if t == "user/message" else {}
            visible = e["seq"] >= cut
            row = {"role": m["role"], "content": content, "turn": turn, "at": e["time"], "visible": visible,
                   "tok": self._tokens(json.dumps(m, ensure_ascii=False)) if visible else 0,
                   **({"tool_calls": m["tool_calls"]} if m.get("tool_calls") else {}),
                   **({"tool_call_id": m["tool_call_id"]} if m.get("tool_call_id") else {}),
                   **({"src": src["kind"]} if src.get("kind") else {}),
                   **({"thread": str(src["thread"])} if src.get("kind") == "walter-intake" and src.get("thread") else {})}
            originals.append((e["seq"], row))
        ck = self._tokens(win["data"].get("content") or "") if win else 0
        if not any(r["visible"] and r["turn"] != live for _, r in originals) and not ck:
            return {"applied": False, "reason": "no_completed_turn"}
        measured = sum(r["tok"] for _, r in originals) + ck + self._tokens(self._system(a))
        try:
            res = await self.doors.bridge({"op": "window", "messages": [r for _, r in originals], "model": f"walter/{a.model or self.s.model}",
                                           "budget_tokens": max(0, self.s.context_window - OUTPUT_RESERVE),
                                           "measured_tokens": measured, "now_ms": journal.now_ms(),
                                           "plan": {"thread": plan.get("thread")} if plan and plan.get("thread") else None,
                                           "live_turn": live, "checkpoint_tokens": ck, "force": force})
        except Exception as e:  # noqa: BLE001 — the window is not managed this turn: said in the measurements
            self._observe({"kind": "window", "session": a.key, "turn": live or turn, "applied": False, "reason": "error",
                           "error": f"{type(e).__name__}: {str(e)[:120]}", "window_ms": elapsed_ms(t0)})
            return {"applied": False, "reason": "error"}
        report = {"applied": False, "reason": res.get("reason"), "warm": res.get("warm"), "turns": res.get("turns"),
                  "tokens": res.get("tokens"), "measured_tokens": measured}
        if res.get("needed"):
            idx = int(res.get("cut", len(originals)))
            cut_seq = originals[idx][0] if 0 <= idx < len(originals) else s.seq + 1
            s.append("compaction/window", {"cut_seq": cut_seq, "content": res.get("content") or "", "reason": res.get("reason"),
                                           "tokens": res.get("tokens"), "turns": res.get("turns"), "force": force}, sync=True)
            report["applied"] = True
            asyncio.get_running_loop().create_task(self.state_event(a, "context.changed", {"reason": f"window:{res.get('reason')}"}))
        self._observe({"kind": "window", "session": a.key, "turn": live or turn, **report, "window_ms": elapsed_ms(t0)})
        return report

    # ── jobs, wake-ups, restarts ──
    def _job_settled(self, job: Job) -> None:
        if self.stopping or not job.wake:
            return
        a = self.load(job.owner)
        if a is None:
            return
        view = job.view()
        if job.kind == "subagent":
            text = (f"[Sous-agent terminé] {job.label} ({job.id}) : {job.status}, {view['runtime_s']} s.\n"
                    f"{job.result or ''}")
            kind = "subagent-settled"
        else:
            tail = ""
            try:
                tail = self.jobs.output(job.id, limit=1500)["output"]
            except KeyError:
                pass
            code = "" if job.code is None else f", code {job.code}"
            text = f"[Travail de fond terminé] {job.label} ({job.id}) : {job.status}{code}, {view['runtime_s']} s."
            if job.result and job.kind != "bash":
                text += " " + job.result
            if tail:
                text += f"\nFin de la sortie (job_output(job_id=\"{job.id}\") pour tout lire) :\n{tail}"
            kind = "tool-jobs"
        loop = asyncio.get_running_loop()
        loop.create_task(self.state_event(a, "task.ended", {"task_id": job.id, "goal": job.label,
                                                            "status": {"completed": "done", "killed": "cancelled"}.get(job.status, "failed"),
                                                            "result": (job.result or "")[:300]}))
        self.notice(a, text, kind)

    def _active(self, sid: str, on: bool) -> None:
        rows = set(_read_json(self.active_file, []))
        (rows.add if on else rows.discard)(sid)
        try:
            _write_json(self.active_file, sorted(rows))
        except OSError:
            pass

    async def _recover(self) -> None:
        """After a restart: close what the previous process left open, say it, resume where the journal says."""
        # 1. runs left open by a dead engine process (this one's file, and the DSH engine's at the switch)
        legacy = config.instance_root() / "state" / "core" / "engine" / "intake" / "open-runs.json"
        carry: dict[str, dict] = {}      # session key → the cut run (and its plan): the resumed turn is its continuation
        for f in (self.runs_file, legacy):
            rows = _read_json(f, {})
            gone = {k: r for k, r in rows.items() if isinstance(r, dict) and r.get("pid") != os.getpid() and not _alive(r.get("pid"))}
            if not gone:
                continue
            for key, r in gone.items():
                await self.doors.run_end(r["run_id"], key, "cancelled", {"status": "interrupted",
                                                                          "error": {"kind": "engine_restart", "message": "the engine restarted during this turn"}})
                carry[key] = {"run_id": r["run_id"], **(r.get("last") or {}), "open": False}
                rows.pop(key, None)
            try:
                _write_json(f, rows)
            except OSError:
                pass
        # 2. turns cut by the restart
        resumed = []
        for sid in _read_json(self.active_file, []):
            a = self.load(sid)
            if a is None:
                continue
            s = a.session
            open_ = s.open_turn()
            if open_ is None:
                continue
            turn = open_["data"].get("turn")
            for call in s.pending_calls():
                d = call["data"]
                s.append("tool/result", {"turn": d.get("turn"), "step": d.get("step"), "callId": d.get("callId"),
                                         "name": d.get("name"), "content": UNKNOWN, "isError": True, "recovered": True,
                                         **({"nested": True} if d.get("nested") else {})})
            s.append("turn/end", {"turn": turn, "status": "interrupted", "reason": {"kind": "interrupted",
                                                                                  "error": {"code": "engine_restart"}}}, sync=True)
            if self.s.resume_interrupted and not a.parent_sid and not a.unattended:
                if not a.last and a.key in carry:     # the wake run is a child of the cut run: same objective, same plan
                    a.last = carry[a.key]
                resumed.append(a)
        _write_json(self.active_file, [])
        # 3. background jobs a dead process was running
        lost = self.jobs.recover()
        notes: dict[str, list[str]] = {}
        for j in lost:
            notes.setdefault(j.owner, []).append(
                f"- {j.id} ({j.label}) : perdu au redémarrage — "
                + ("idempotent, peut être relancé tel quel" if j.idempotent else "effet réel inconnu, vérifier avant de relancer"))
        for a in resumed:
            text = ("[Walter] Le moteur a redémarré pendant le tour précédent ; il a été clos « interrompu ». Les appels "
                    "qui étaient en cours portent « résultat inconnu ». Reprends la demande là où elle en était à partir "
                    "de ce qui précède : vérifie l'état réel de ce qui était en cours avant de refaire une action qui a un "
                    "effet externe, ne refais pas ce qui est déjà fait, et dis à Monsieur où tu en es.")
            extra = notes.pop(a.sid, None)
            if extra:
                text += "\nTravaux de fond concernés :\n" + "\n".join(extra)
            self.notice(a, text, "engine-restart")
        for sid, rows in notes.items():
            a = self.load(sid)
            if a is not None and not a.unattended:
                self.notice(a, "[Walter] Le moteur a redémarré pendant des travaux de fond de cette conversation :\n"
                            + "\n".join(rows), "tool-jobs")


def _alive(pid) -> bool:
    try:
        if not pid:
            return False
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False
