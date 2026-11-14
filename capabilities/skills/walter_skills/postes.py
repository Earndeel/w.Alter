"""Model postes (editor, indexer, judge): the only way walter-skills reaches a model.

A poste is an ordered list of routes in config/walter-skills.toml; a route names a Walter Router task and one of
Monsieur's text tiers (`task = "general"`, `level = "L2"`) and nothing else: no model, no provider. The call goes to
the walter-llm gateway by poste (`task/level`) through walter_memory.llm.chat — privacy guard (local_only refused,
redacted pseudonymised), monthly budget, ledger in system.model_calls. The Router chooses the model and its routes
(Codex subscription, Kie, OpenRouter…) and the gateway executes them with its own keys and fallbacks (SOCLE A6,
2026-11-11: no `codex exec` launched from here any more, no static model).
Every prompt is secret-masked before it leaves the VM.

Token: the gateway call carries Walter Memory's walter-llm agent token (the call goes through Memory's door).
walter-skills has no walter-llm token of its own.
"""
from __future__ import annotations

import json
import re

from walter_memory import llm
from walter_memory.logs import mask

from . import config


def _routes(poste: str) -> list[dict]:
    """The poste's routes as Router postes: [{"poste": "general/L2", "budget": "recurring"}…]. A route that names a
    model or a transport (the former via = "codex" / "openrouter") is ignored: models are the Router's choice."""
    out = []
    for route in config.poste(poste):
        if route.get("model") or route.get("via") not in (None, "router"):
            continue
        task, level = route.get("task", "general"), route.get("level")
        out.append({"poste": f"{task}/{level}" if level else task, "budget": route.get("budget", "recurring")})
    return out


def _gateway(prompt: str, poste: str, budget: str, processor: str, timeout: int) -> str | None:
    try:
        r = llm.chat([{"role": "user", "content": prompt}], poste=poste, processor=processor,
                     privacy_class="cloud_allowed", budget=budget, timeout=timeout, purpose=processor)
        return r["content"]
    except Exception:  # noqa: BLE001 — recorded in system.model_calls by llm.chat; the next route is tried
        return None


def ask(poste: str, prompt: str, *, timeout: int = 900, processor: str | None = None) -> tuple[str | None, str | None]:
    """(answer, route used) — the first route of the poste that answers; (None, None) if none did."""
    prompt = mask(prompt)
    for route in _routes(poste):
        text = _gateway(prompt, route["poste"], route["budget"], processor or f"skills.{poste}", min(timeout, 300))
        if text:
            return text, f"router:{route['poste']}"
    return None, None


def ask_json(poste: str, prompt: str, *, require: str | None = None, retries: int = 1, **kw) -> tuple[dict | None, str | None]:
    """ask() and parse the JSON object of the answer; retried once on an unparsable answer."""
    for _ in range(retries + 1):
        text, route = ask(poste, prompt, **kw)
        obj = parse_json(text)
        if obj is not None and (require is None or require in obj):
            return obj, route
    return None, None


def available(poste: str) -> bool:
    return bool(_routes(poste))


def parse_json(text: str | None) -> dict | None:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None
