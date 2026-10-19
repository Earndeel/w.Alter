"""Model postes (editor, indexer, judge): the only way walter-skills reaches a model.

A poste is an ordered list of routes in config/walter-skills.toml; the first route that answers wins.
  via = "codex"      W.Alter's own Codex subscription session (`codex exec`, read-only sandbox, ephemeral) —
                     never Hermes' session, whose rotating refresh token must have a single writer.
  via = "openrouter" walter_memory.llm: privacy guard (local_only refused, redacted pseudonymised), monthly budget,
                     OpenRouter balance floor, ledger in system.model_calls.
  via = "router"     Walter Router (2026-10-16): `level` = one of Monsieur's text tiers (task general); its Codex
                     routes run through W.Alter's own Codex session as above, the others through walter_memory.llm
                     poste=general/LEVEL (walter-llm gateway). The tier Monsieur adopts reaches the poste by itself.
Every prompt is secret-masked before it leaves the VM.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from walter_memory import llm
from walter_memory.logs import mask

from . import config


_ready: tuple[float, bool] = (0.0, False)


def _codex_ready() -> bool:
    """Is W.Alter's Codex session logged in? (checked at most once a minute)"""
    global _ready
    import time
    if time.monotonic() - _ready[0] < 60:
        return _ready[1]
    try:
        r = subprocess.run(["codex", "login", "status"], capture_output=True, text=True, timeout=20)
        ok = r.returncode == 0 and "not logged in" not in (r.stdout + r.stderr).lower()
    except Exception:
        ok = False
    _ready = (time.monotonic(), ok)
    return ok


def _codex(prompt: str, model: str, effort: str, timeout: int, processor: str = "skills") -> str | None:
    if not _codex_ready():
        return None
    import time
    t0 = time.perf_counter()
    text = _codex_exec(prompt, model, effort, timeout)
    try:  # Codex calls are accounted like the others (subscription: no per-token cost)
        llm._log(processor=processor, provider="codex", model=model, purpose=processor, budget="recurring",
                 privacy_class="cloud_allowed", status="ok" if text else "error", cost_usd=0,
                 latency_ms=int((time.perf_counter() - t0) * 1000))
    except Exception:
        pass
    return text


def _codex_exec(prompt: str, model: str, effort: str, timeout: int) -> str | None:
    with tempfile.TemporaryDirectory(prefix="walter-skills-") as d:
        out = Path(d) / "last.txt"
        cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "-m", model,
               "-c", f"model_reasoning_effort={effort}", "-o", str(out), "-"]
        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=d)
        except subprocess.TimeoutExpired:
            return None
        return out.read_text(errors="replace") if r.returncode == 0 and out.exists() else None


def _openrouter(prompt: str, model: str, budget: str, processor: str, timeout: int) -> str | None:
    try:
        r = llm.chat([{"role": "user", "content": prompt}], model=model, processor=processor,
                     privacy_class="cloud_allowed", budget=budget, timeout=timeout, purpose=processor)
        return r["content"]
    except Exception:
        return None


_ROUTER: dict[str, tuple[float, list[dict]]] = {}


def _router_routes(route: dict) -> list[dict]:
    """A via="router" route expanded into concrete routes (cached 10 min; [] when the router is unreachable)."""
    import time
    level = route.get("level", "L1")
    key = f"{level}|{route.get("budget", "recurring")}"
    hit = _ROUTER.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    try:
        r = subprocess.run(["walter-router", "pick", "general", "--level", level],
                           capture_output=True, text=True, timeout=60)
        d = json.loads(r.stdout)
    except Exception:
        return hit[1] if hit else []
    out, gateway = [], False
    for e in d.get("execution") or []:
        if e.get("hermes_provider") == "openai-codex":
            out.append({"via": "codex", "model": e["model"], "effort": e.get("reasoning") or "medium"})
        elif not gateway:   # the gateway runs every paid route of the tier in the router's order
            out.append({"via": "gateway", "poste": f"general/{level}", "budget": route.get("budget", "recurring")})
            gateway = True
    _ROUTER[key] = (time.time(), out)
    return out


def _gateway(prompt: str, poste: str, budget: str, processor: str, timeout: int) -> str | None:
    try:
        r = llm.chat([{"role": "user", "content": prompt}], poste=poste, processor=processor,
                     privacy_class="cloud_allowed", budget=budget, timeout=timeout, purpose=processor)
        return r["content"]
    except Exception:
        return None


def _routes(poste: str) -> list[dict]:
    out = []
    for route in config.poste(poste):
        out += _router_routes(route) if route["via"] == "router" else [route]
    return out


def ask(poste: str, prompt: str, *, timeout: int = 900, processor: str | None = None) -> tuple[str | None, str | None]:
    """(answer, route used) — the first route of the poste that answers; (None, None) if none did."""
    prompt = mask(prompt)
    for route in _routes(poste):
        if route["via"] == "codex":
            text = _codex(prompt, route["model"], route.get("effort", "medium"), timeout, processor or f"skills.{poste}")
        elif route["via"] == "openrouter":
            text = _openrouter(prompt, route["model"], route.get("budget", "recurring"),
                               processor or f"skills.{poste}", min(timeout, 300))
        elif route["via"] == "gateway":
            text = _gateway(prompt, route["poste"], route.get("budget", "recurring"),
                            processor or f"skills.{poste}", min(timeout, 300))
        else:
            continue
        if text:
            return text, f"{route['via']}:{route.get('model') or route.get('poste')}"
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
    return any(r["via"] in ("openrouter", "gateway") or (r["via"] == "codex" and _codex_ready()) for r in _routes(poste))


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
