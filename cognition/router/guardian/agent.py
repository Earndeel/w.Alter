"""The Router's agent (owner, 2026-11-21): « il doit s'identifier comme le Router, il fait partie intégrante de ce
module. Il doit s'occuper de toute la partie agentique, de compréhension plus profonde, de réparation. Il comprend
l'architecture de Walter et de son module. Il est un sous-agent de Walter spécialisé dans le maintien du module ».

One agent, one identity: `guardian/agent.md` (declared in `contracts/maintenance.json` → `agent`), rendered for the
instance and followed by the owner's own rules for it (instance file `config/router/guardian-rules.md`). Every
mission of the module that needs a model with tools goes through `delegate` here — one Walter Engine delegation as
the machine caller `guardian-router` (policy « guardian- » = interface maintenance): advice (advice.py), plan watch
(plan/watch.py). Repair runs through the guardians' common agent (`walter-guardian repair`), which reads the same
declaration; Walter's own sub-agent tool does too (`subagent`, agent "router").
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from walter_router import instance

ENGINE_URL = os.environ.get("WALTER_ENGINE_API_URL", "http://127.0.0.1:8895")
CALLER = "guardian-router"              # the agent's one identity (policy « guardian- » = maintenance)
IDENTITY_FILE = Path(__file__).with_name("agent.md")
RULES_FILE = "guardian-rules.md"        # instance config/router/<this>: the owner's rules for the agent
NAME = "Walter Router"                  # how it signs what it sends the owner


def owner_rules() -> list[str]:
    """The owner's own rules for the agent (lines « - … » of the instance file); they win over the rest."""
    try:
        text = instance.config_path(RULES_FILE).read_text()
    except OSError:
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("- ") and len(ln.strip()) > 2]


def identity() -> str:
    """Who the agent is, what Walter and the Router are, the owner's rules (agent.md + instance rules)."""
    text = IDENTITY_FILE.read_text().split("\n---\n", 1)[-1].strip()      # the file's own header is for humans
    owner = instance.owner()
    text = text.replace("{{owner.address}}", owner)
    rules = owner_rules()
    if rules:
        text += f"\n\n## Règles de {owner} pour toi (elles priment sur tout le reste)\n" + "\n".join(rules)
    return text


def goal(mission: str) -> str:
    """The identity first, then the mission's own brief."""
    return identity() + "\n\n---\n\n" + mission.strip()


def _engine_token() -> str:
    root = instance._walter("path")
    if not root:
        raise RuntimeError("no active Walter instance")
    return (Path(root) / "bootstrap" / "engine" / "api.token").read_text().strip()


def delegate(mission: str, key: str, *, task: str = "general", level: str | None = None, budget: int = 900) -> dict:
    """One mission of the Router's agent on Walter Engine (Engine API, the declared door to the runtime)."""
    d = {"version": 1, "goal": goal(mission), "task": task, "budget_seconds": budget,
         "idempotency_key": re.sub(r"[^A-Za-z0-9._:-]", "-", key)[:200], "parent": {"depth": 0}}
    if level:
        d["level"] = level
    req = Request(ENGINE_URL.rstrip("/") + "/v1",
                  data=json.dumps({"version": 1, "op": "delegate", "caller": CALLER, "delegation": d}).encode(),
                  headers={"Authorization": "Bearer " + _engine_token(), "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=budget + 120) as r:
            out = json.load(r)
    except Exception as exc:  # noqa: BLE001 — engine down: a failed run, said as such
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    res = out.get("result") or out
    return {"ok": bool(res.get("ok")), "output": res.get("output") or "", "status": res.get("status"),
            "reason": res.get("reason"), "error": res.get("error"), "tools": len(res.get("tools") or []),
            "walter_session": res.get("walter_session")}
