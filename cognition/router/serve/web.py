"""Conversational web services as a Router tool (walter_web): a message, optional files and model, the reply verbatim.

The rule table and the exchange belong to the module's gateway (`web_services`, `POST /v1/web/converse`); this is
its local entry for agents (MCP, Hermes tool, CLI), through the gateway's own CLI (`walter-llm web`), as text runs
use `walter-llm call`. Files go in as local paths and come back as local paths (never base64 in an agent context).
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
from pathlib import Path

from walter_router import instance

# The owner's rule (knowledge.json `web_services`): which classified intents a web chat service answers, e.g.
# {"chatgpt": {"tasks": {"weather": null, "calculation": null, "research": ["L1"]}}} — null = any level. Only a
# service the gateway has enabled is chosen; when it fails the request takes the usual path (with a notice).
DEFAULT_CONVERSATION = "walter-router"
MAX_FILES = 10
MAX_FILE_BYTES = 50 * 1024 * 1024
KEYS = ("service", "message", "model", "files", "conversation", "request_id", "timeout_s")


def out_dir() -> Path:
    """Same place as the router's generated media (the agents already look there)."""
    return instance.hermes_home() / "generated" / "walter-router"


def converse(spec: dict) -> dict:
    unknown = sorted(set(spec) - set(KEYS) - {"agent"})
    if unknown:
        return {"ok": False, "error": f"unknown fields: {', '.join(unknown)}"}
    message = str(spec.get("message") or "").strip()
    if not message:
        return {"ok": False, "error": "message required"}
    body: dict = {"message": message, "agent": str(spec.get("agent") or "router")}
    for key in ("service", "model", "conversation", "request_id", "timeout_s"):
        if spec.get(key) not in (None, "", 0):
            body[key] = spec[key]
    paths = spec.get("files") or []
    if isinstance(paths, str):
        paths = [paths]
    if len(paths) > MAX_FILES:
        return {"ok": False, "error": f"at most {MAX_FILES} files"}
    body["files"] = []
    for raw in paths:
        p = Path(str(raw)).expanduser()
        if not p.is_file():
            return {"ok": False, "error": f"file not found: {raw}"}
        if p.stat().st_size > MAX_FILE_BYTES:
            return {"ok": False, "error": f"file larger than 50 MB: {raw}"}
        body["files"].append({"name": p.name, "data": base64.b64encode(p.read_bytes()).decode()})
    timeout = min(float(spec.get("timeout_s") or 300), 600) + 120
    try:
        run = subprocess.run(["walter-llm", "web"], input=json.dumps(body), capture_output=True, text=True,
                             timeout=timeout)
        out = json.loads(run.stdout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "web_timeout"}
    except ValueError:
        return {"ok": False, "error": "invalid_gateway_response"}
    produced = out.get("files") or []
    if produced:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        rid = re.sub(r"[^\w.-]+", "_", str(out.get("request_id") or "web"))[:40]
        folder = out_dir() / f"{stamp}-web-{out.get('service') or 'service'}-{rid}"
        folder.mkdir(parents=True, exist_ok=True)
        for n, f in enumerate(produced):
            data = f.pop("data", None)
            if not data:
                continue
            name = re.sub(r"[^\w.\- ]+", "_", Path(str(f.get("name") or f"file-{n + 1}")).name).strip() \
                or f"file-{n + 1}"
            target = folder / name
            if target.exists():
                target = folder / f"{n + 1}-{name}"
            target.write_bytes(base64.b64decode(data))
            target.chmod(0o600)
            f["path"] = str(target)
    return out


def _enabled() -> set[str]:
    """Services the gateway has enabled (its own rule table, the owner's switch)."""
    path = instance._walter("config", "llm", "gateway.json")
    try:
        services = json.loads(Path(path).read_text()).get("web_services") or {} if path else {}
    except (OSError, ValueError):
        return set()
    return {k for k, v in services.items() if isinstance(v, dict) and v.get("enabled") and not k.startswith("_")}


def commands() -> dict[str, str]:
    """Chat command → web service, from the gateway's rule table (`/gpt` → chatgpt…), for the Telegram door."""
    path = instance._walter("config", "llm", "gateway.json")
    try:
        services = json.loads(Path(path).read_text()).get("web_services") or {} if path else {}
    except (OSError, ValueError):
        return {}
    return {str(v.get("command") or ("gpt" if k == "chatgpt" else k)): k
            for k, v in services.items() if not k.startswith("_") and isinstance(v, dict)}


def route_for(task: str | None, level: str | None) -> dict | None:
    """The web service the owner's rule gives this classified intent, or None."""
    from walter_router.analysis import knowledge   # late import (knowledge -> select -> …)
    try:
        rules = knowledge.load().get("web_services") or {}
    except (OSError, ValueError):
        return None
    matches = []
    for service, rule in rules.items():
        if service.startswith("_") or not isinstance(rule, dict):
            continue
        tasks = rule.get("tasks") or {}
        if task in tasks and (tasks[task] is None or level in tasks[task]):
            matches.append((service, rule))
    if not matches:
        return None
    enabled = _enabled()
    for service, rule in matches:
        if service in enabled:
            return {"service": service, "conversation": rule.get("conversation") or DEFAULT_CONVERSATION,
                    "why": rule.get("why") or f"règle web_services.{service} ({task}, {level})"}
    return None
