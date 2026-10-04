#!/opt/walter-llm/venv/bin/python3
"""walter-llm — W.Alter's model gateway (P8.5 + P8.7): one OpenAI-compatible endpoint for every agent runtime.

    agent (DeepSeek Harness, Codex, scripts…) ──token──▶ walter-llm (127.0.0.1:8894)
        model = a Walter Router task ("coding", "document"…) or "auto"
        ├─ Walter Router  → ordered routes (provider, model, reasoning) for the task      [choice]
        ├─ walter-secrets → provider key read from Monsieur's Bitwarden, kept in RAM here [secrets]
        └─ LiteLLM        → provider protocol (Anthropic, Responses, OpenAI-compatible)   [adapters]

Agents never hold a provider key: they get a local per-agent token (sha256 in agents.json, 0600) that only allows
model calls through here (DeepSeek Harness' own docs: file permissions cannot keep keys away from an agent whose
tools run as the same user — a gateway can). Every attempt is logged (no content) to
~/.hermes/logs/walter-llm.jsonl and to Walter Router's models.exec_log, so the router learns from these runs too.
A route that fails before its first token falls through to the next one.

Run:   gateway.py serve                 (127.0.0.1:8894)
       gateway.py add-agent NAME FILE   new token for NAME, written into a dsh credentials YAML (never printed)
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request  # module level: FastAPI resolves endpoint annotations from module globals

HERE = Path(__file__).resolve().parent
AGENTS = HERE / "agents.json"
LOG = Path("/root/.hermes/logs/walter-llm.jsonl")
ROUTER = "/opt/walter-router/bin/walter-router"
SECRETS_MAP = Path("/root/.hermes/vault/secrets-map.json")
sys.path.insert(0, "/root/.hermes/plugins/walter-secrets")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
DEFAULT_TASK = "coding"
KEY_TTL, ROUTE_TTL = 600, 600
KIE_GPT = ("gpt-",)


# ───────────────────────── secrets (Bitwarden through walter-secrets) ─────────────────────────
_keys: dict[str, tuple[float, str]] = {}
_keys_lock = threading.Lock()


def provider_key(env_name: str) -> str:
    """Value of the Bitwarden item mapped to `env_name` (secrets-map.json), cached in this process only."""
    with _keys_lock:
        hit = _keys.get(env_name)
        if hit and time.time() - hit[0] < KEY_TTL:
            return hit[1]
    entries = json.loads(SECRETS_MAP.read_text())["entries"]
    e = next((e for e in entries if e["target"].endswith(f":{env_name}") and e["target"].startswith("env:/root/.hermes/.env")),
             None) or next((e for e in entries if e["target"].endswith(f":{env_name}")), None)
    if not e:
        raise LookupError(f"{env_name} is not in Bitwarden (secrets-map)")
    from bwvault import VAULT, audit
    value = VAULT.value(e["item_id"], e["field"])
    audit("use", {"id": e["item_id"], "name": e["item"]}, e["field"], tool="walter-llm")
    with _keys_lock:
        _keys[env_name] = (time.time(), value)
    return value


# ───────────────────────── routes (Walter Router) ─────────────────────────
_routes: dict[str, tuple[float, dict]] = {}


def _router(*args: str) -> dict | list:
    r = subprocess.run([ROUTER, *args], capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(f"walter-router {' '.join(args)}: {(r.stderr or r.stdout)[-300:]}")
    return json.loads(r.stdout)


def decision(task: str) -> dict:
    hit = _routes.get(task)
    if hit and time.time() - hit[0] < ROUTE_TTL:
        return hit[1]
    d = _router("pick", task)
    _routes[task] = (time.time(), d)
    return d


def chat_tasks() -> list[str]:
    hit = _routes.get("__tasks__")
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    tasks = [t["task"] for t in _router("tasks") if t.get("interface") == "chat"]
    _routes["__tasks__"] = (time.time(), tasks)
    return tasks


def litellm_target(route: dict) -> dict | None:
    """LiteLLM arguments for one router route, or None when this gateway cannot run it (yet)."""
    p, m = route["provider"], route["model"]
    if p == "kie" and m.startswith(KIE_GPT):                 # Kie /codex = OpenAI Responses protocol
        key = provider_key("KIE_API_KEY")
        return {"model": f"openai/responses/{m}", "api_base": "https://api.kie.ai/codex/v1", "api_key": key,
                "extra_headers": {"User-Agent": UA}}
    if p == "kie":                                            # Kie /claude = Anthropic Messages protocol
        key = provider_key("KIE_API_KEY")
        return {"model": f"anthropic/{m}", "api_base": "https://api.kie.ai/claude", "api_key": key,
                "extra_headers": {"User-Agent": UA, "Authorization": f"Bearer {key}"}}
    if p == "openrouter":
        return {"model": f"openrouter/{m}", "api_key": provider_key("OPENROUTER_API_KEY")}
    if p == "arnict":
        return {"model": f"openai/{m}", "api_base": "https://api.arnict.com/v1", "api_key": provider_key("ARNICT_API_KEY")}
    return None    # "codex" = ChatGPT subscription held by Hermes (OAuth), not an API key — P8.7


# ───────────────────────── logging ─────────────────────────
def _usage(resp) -> dict | None:
    u = getattr(resp, "usage", None)
    if not u:
        return None
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", None)
    return {"in": u.prompt_tokens, "out": u.completion_tokens, "cached": cached}


def log(entry: dict) -> None:
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    try:
        with LOG.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    if entry.get("provider"):                                 # teach the router (background, best effort)
        row = {"task": entry.get("task"), "model_id": entry.get("model_id"), "provider": entry["provider"],
               "model": entry.get("model"), "ok": entry.get("ok"), "seconds": entry.get("seconds"), "kind": "text",
               "role": f"agent:{entry.get('agent')}"}
        threading.Thread(target=subprocess.run, args=([ROUTER, "log-exec", json.dumps(row)],),
                         kwargs={"capture_output": True, "timeout": 60}, daemon=True).start()


# ───────────────────────── HTTP ─────────────────────────
def build_app():
    import litellm
    from fastapi import FastAPI, Header, HTTPException
    from fastapi.responses import JSONResponse, StreamingResponse

    litellm.drop_params = True
    litellm.suppress_debug_info = True
    app = FastAPI(title="walter-llm")

    def agent_of(authorization: str) -> str:
        tok = authorization.removeprefix("Bearer ").strip()
        agents = json.loads(AGENTS.read_text()) if AGENTS.exists() else {}
        a = agents.get(hashlib.sha256(tok.encode()).hexdigest()) if tok else None
        if not a:
            raise HTTPException(401, "unknown agent token")
        return a["agent"]

    @app.get("/v1/models")
    def models(authorization: str = Header(default="")):
        agent_of(authorization)
        return {"object": "list", "data": [{"id": t, "object": "model", "owned_by": "walter-router"}
                                           for t in ["auto", *chat_tasks()]]}

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/v1/chat/completions")
    async def completions(request: Request, authorization: str = Header(default="")):
        agent = agent_of(authorization)
        body = await request.json()
        task = body.pop("model", None) or DEFAULT_TASK
        task = DEFAULT_TASK if task in ("auto", "walter") else task.removeprefix("walter/")
        stream = bool(body.pop("stream", False))
        try:
            d = decision(task)
        except Exception as e:
            raise HTTPException(400, f"no route for task {task!r}: {e}")
        errors = []
        for route in d.get("execution") or []:
            t0 = time.perf_counter()
            base = {"agent": agent, "task": task, "model_id": d.get("model_id"), "provider": route["provider"],
                    "model": route["model"]}
            try:
                target = litellm_target(route)
            except Exception as e:                            # key missing in Bitwarden, vault locked…
                errors.append(f"{route['provider']}/{route['model']}: {type(e).__name__}")
                continue
            if target is None:
                continue
            kwargs = {**body, **target, "stream": stream, "num_retries": 0}
            if route.get("reasoning") and route["reasoning"] not in ("none", "non-reasoning"):
                kwargs.setdefault("reasoning_effort", route["reasoning"])
            try:
                resp = await litellm.acompletion(**kwargs)
                if not stream:
                    log({**base, "ok": True, "seconds": round(time.perf_counter() - t0, 2),
                         "usage": _usage(resp)})
                    return JSONResponse(resp.model_dump(), headers={"X-Walter-Route": f"{route['provider']}/{route['model']}"})
                it = resp.__aiter__()
                first = await it.__anext__()                  # fail over until the first token arrives
            except Exception as e:
                errors.append(f"{route['provider']}/{route['model']}: {type(e).__name__}: {str(e)[:160]}")
                log({**base, "ok": False, "seconds": round(time.perf_counter() - t0, 2), "error": type(e).__name__})
                continue

            async def sse(first=first, it=it, base=base, t0=t0):
                ok = True
                try:
                    yield f"data: {first.model_dump_json()}\n\n"
                    async for chunk in it:
                        yield f"data: {chunk.model_dump_json()}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:                        # mid-stream failure: surface it, do not hang
                    ok = False
                    yield f"data: {json.dumps({'error': {'message': f'{type(e).__name__}: {e}'[:300]}})}\n\n"
                finally:
                    log({**base, "ok": ok, "seconds": round(time.perf_counter() - t0, 2), "stream": True})

            return StreamingResponse(sse(), media_type="text/event-stream",
                                     headers={"X-Walter-Route": f"{route['provider']}/{route['model']}"})
        log({"agent": agent, "task": task, "ok": False, "error": "all routes failed"})
        raise HTTPException(502, {"message": "every route failed", "attempts": errors})

    return app


def add_agent(name: str, cred_file: str, ref: str = "WALTER_LLM_TOKEN") -> None:
    token = "wllm_" + secrets.token_urlsafe(32)
    agents = json.loads(AGENTS.read_text()) if AGENTS.exists() else {}
    agents = {h: a for h, a in agents.items() if a["agent"] != name}          # rotate: one token per agent
    agents[hashlib.sha256(token.encode()).hexdigest()] = {"agent": name, "created": datetime.now(timezone.utc).isoformat()}
    AGENTS.write_text(json.dumps(agents, indent=1))
    os.chmod(AGENTS, 0o600)
    p = Path(cred_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"version: 1\n\nrefs:\n  {ref}: {token}\n")
    os.chmod(p, 0o600)
    print(f"agent {name}: token written to {p} (ref {ref})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "add-agent":
        add_agent(sys.argv[2], sys.argv[3])
    else:
        import uvicorn
        uvicorn.run(build_app(), host="127.0.0.1", port=int(os.environ.get("WALTER_LLM_PORT", "8894")), log_level="warning")
