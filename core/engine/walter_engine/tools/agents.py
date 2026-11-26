"""Walter Engine — sub-agents (2026-11-17).

A sub-agent is a session of its own (its journal, its context window, its Python kernel), run by the same engine
under the same policy: it is judged under its root session's door with the `child` preset (never above its parent:
no outgoing message of its own), files its runs under its parent's current run (correlation, costs, cancellation
follow the tree), and can delegate in turn until `max_depth`. Its model is a Walter Router poste (`coding`,
`general`, `document`…) or the engine's default; walter-llm plans and executes it.

A module can have its own agent (2026-11-21, the Router first): `agent: "<module id>"` gives the sub-agent that
module's identity — declared in the module's `contracts/maintenance.json` (`agent.identity`, a file of the module,
rendered for the instance, plus the owner's rules for it, `agent.rules`) — before the mission, and its poste
(`agent.task`) when no model is given. The same identity opens the module's own missions (repair, advice…).

Foreground: the parent's call returns the child's final answer. Background: an engine job; the parent is woken with
the answer when the child settles (and can follow it with `send_message` / `interrupt_agent` / `list_agents`).
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
from pathlib import Path

from . import Exec, Result, Tool, clip, obj
from .. import config

POSTE = re.compile(r"^[A-Za-z0-9._:/-]{1,120}$")
EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")


def _child_of(ex: Exec, agent_id: str):
    child = ex.engine.agents.get(str(agent_id or ""))
    if not child or child.parent_sid != ex.agent.sid:
        return None
    return child


def module_agent(module: str) -> tuple[str, dict] | None:
    """(identity text, declaration) of a module's own agent, or None when the module declares none."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,40}", module or ""):
        return None
    root = config.module_root(module)
    try:
        decl = json.loads((root / "contracts" / "maintenance.json").read_text()).get("agent") if root else None
        text = (root / decl["identity"]).read_text().split("\n---\n", 1)[-1].strip()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    try:
        r = subprocess.run(["walter", "instance", "render"], input=text, capture_output=True, text=True, timeout=20)
        text = r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else text
        rules = []
        if decl.get("rules"):
            p = subprocess.run(["walter", "instance", "config", module, str(decl["rules"])], capture_output=True,
                               text=True, timeout=20).stdout.strip()
            rules = [ln.strip() for ln in Path(p).read_text().splitlines()
                     if ln.strip().startswith("- ") and len(ln.strip()) > 2] if p and Path(p).is_file() else []
    except (OSError, subprocess.SubprocessError):
        rules = []
    if rules:
        text += "\n\n## Règles du propriétaire pour toi (elles priment sur tout le reste)\n" + "\n".join(rules)
    return text, decl


async def subagent(args: dict, ex: Exec) -> Result:
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return Result("prompt must be non-empty: the sub-agent sees only what you write there", True)
    eng = ex.engine
    if ex.agent.depth + 1 > eng.s.max_depth:
        return Result(f"délégation refusée : profondeur maximale ({eng.s.max_depth}) atteinte", True)
    model = args.get("model")
    if model is not None and (not isinstance(model, str) or not POSTE.match(model)):
        return Result("model must be a Walter Router poste (coding, general, document, summarization, auto…)", True)
    provider = args.get("provider")
    if provider not in (None, "", "walter"):
        return Result("provider must be walter (Walter Router chooses and executes every model)", True)
    effort = args.get("reasoning_effort")
    if effort is not None and effort not in EFFORTS:
        return Result(f"reasoning_effort must be one of {', '.join(EFFORTS)}", True)
    description = str(args.get("description") or " ".join(prompt.split()[:6]))[:120]
    module = args.get("agent")
    if module:
        found = await asyncio.to_thread(module_agent, str(module))
        if not found:
            return Result(f"no module agent « {module} » (a module declares one in contracts/maintenance.json → agent; "
                          "known: router)", True)
        identity, decl = found
        prompt = identity + "\n\n---\n\n## Mission\n" + prompt
        model = model or (decl.get("task") if isinstance(decl.get("task"), str) and POSTE.match(decl["task"]) else None)
    child = eng.spawn_child(ex.agent, description=description, model=model or None, effort=effort)
    if args.get("run_in_background"):
        async def work(job):
            res = await eng.run_child(child, prompt)
            eng.jobs.append(job.id, res["text"] or "")
            return {"code": 0 if res["status"] == "ok" else 1,
                    "result": f"[{res['status']}] {clip(res['text'] or '', 3500)}"}

        job = eng.jobs.start(kind="subagent", label=f"sub-agent: {description}", owner=ex.agent.sid, work=work,
                             cancel=lambda: eng.interrupt(child, "parent killed the job"),
                             meta={"agent_id": child.sid})
        return Result(f"Sub-agent {child.sid} started in the background as job {job.id} ({description}). "
                      "End your turn if you have nothing else to do: you will be woken with its answer. "
                      "send_message / interrupt_agent take its agent_id, job_output its job id.",
                      value={"agent_id": child.sid, "job_id": job.id})
    res = await eng.run_child(child, prompt, cancel=ex.cancel)
    head = f"[sub-agent {child.sid} · {res['status']}{' · ' + res['reason'] if res.get('reason') else ''}]"
    return Result(f"{head}\n{res['text'] or '(no answer)'}", res["status"] not in ("ok",),
                  value={"agent_id": child.sid, "status": res["status"], "text": res["text"], "tools": res["tools"]})


async def send_message(args: dict, ex: Exec) -> Result:
    child = _child_of(ex, args.get("agent_id") or args.get("to"))
    if not child:
        return Result("no sub-agent of this conversation with that agent_id (list_agents)", True)
    text = str(args.get("message") or "").strip()
    if not text:
        return Result("message must be non-empty", True)
    eng = ex.engine
    if child.busy:
        eng.steer(child, text, source={"kind": "parent"})
        return Result(f"delivered to {child.sid} while it works (it reads it at its next step)")
    res = await eng.run_child(child, text, cancel=ex.cancel)
    return Result(f"[sub-agent {child.sid} · {res['status']}]\n{res['text'] or '(no answer)'}", res["status"] != "ok",
                  value={"agent_id": child.sid, "status": res["status"], "text": res["text"]})


async def interrupt_agent(args: dict, ex: Exec) -> Result:
    child = _child_of(ex, args.get("agent_id"))
    if not child:
        return Result("no sub-agent of this conversation with that agent_id (list_agents)", True)
    was = child.busy
    ex.engine.interrupt(child, str(args.get("reason") or "parent"))
    return Result(f"{child.sid}: {'interrupted' if was else 'was idle'}")


async def list_agents(args: dict, ex: Exec) -> Result:
    rows = [{"agent_id": a.sid, "description": a.description, "busy": a.busy, "model": a.model,
             "turns": a.session.turns(), "depth": a.depth}
            for a in ex.engine.agents.values() if a.parent_sid == ex.agent.sid]
    return Result("\n".join(f"{r['agent_id']} · {'busy' if r['busy'] else 'idle'} · {r['turns']} turn(s) · {r['description']}"
                            for r in rows) or "no sub-agent in this conversation", value=rows)


def register(reg) -> None:
    s = {"type": "string"}
    reg.add(Tool("subagent",
                 "Delegate a self-contained task to a sub-agent with its own context (it does not see this "
                 "conversation: write everything it needs in prompt). model = a Walter Router poste (coding, general, "
                 "document, summarization; omitted = Walter's choice). agent = a module whose own agent should do "
                 "it — \"router\": the Router itself, Walter's sub-agent that maintains the Walter Router (models per "
                 "poste, subscriptions, rankings, prices): it understands the module, diagnoses, explains, advises, "
                 "repairs. run_in_background=true returns at once; you are woken with its answer.",
                 obj({"description": {"type": "string", "description": "3-6 words shown to the owner."},
                      "prompt": {"type": "string", "description": "The complete mission."},
                      "run_in_background": {"type": "boolean"},
                      "provider": {"type": "string", "enum": ["walter"]},
                      "model": {"type": "string"},
                      "agent": {"type": "string", "description": "A module's own agent (router)."},
                      "reasoning_effort": {"type": "string", "enum": list(EFFORTS)}},
                     ["description", "prompt"]), subagent))
    reg.add(Tool("send_message", "Send a follow-up to one of your sub-agents (by agent_id); an idle one answers it.",
                 obj({"agent_id": s, "message": s}, ["agent_id", "message"]), send_message))
    reg.add(Tool("interrupt_agent", "Stop what one of your sub-agents is doing.",
                 obj({"agent_id": s, "reason": s}, ["agent_id"]), interrupt_agent))
    reg.add(Tool("list_agents", "List your sub-agents (id, state, description).", obj({}), list_agents, parallel=True))
