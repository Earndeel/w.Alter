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
       gateway.py add-agent NAME FILE   new token for NAME, written into a dsh credentials YAML or env:FILE[:VAR] (never printed)
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
ROUTER = "walter-router"   # Walter Router CLI on the PATH
SECRETS_MAP = Path("/root/.hermes/vault/secrets-map.json")
sys.path.insert(0, "/root/.hermes/plugins/walter-secrets")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
DEFAULT_TASK = "coding"
# Codex routes = W.Alter's OWN Codex subscription session, the one of its Codex CLI (~/.codex/auth.json, also used by
# walter-skills), never Hermes' session. Read-only here: the Codex CLI stays the single writer of its rotating refresh
# token — when the access token is about to expire, a tiny `codex exec` makes the CLI refresh it, then it is re-read.
CODEX_AUTH = Path("/root/.codex/auth.json")
CHATGPT_DIR = HERE / "chatgpt"                      # LiteLLM wants a token dir; nothing is ever stored there
os.environ.setdefault("CHATGPT_TOKEN_DIR", str(CHATGPT_DIR))
CODEX_REFRESH_MARGIN = 3600
# LiteLLM prepends the Codex CLI's coding-agent prompt (~1.7k tokens) to every call: a neutral one for module jobs
os.environ.setdefault("CHATGPT_DEFAULT_INSTRUCTIONS", "You are a precise assistant for W.Alter's background jobs. Follow "
                      "the system and user instructions exactly; answer in the language of the request.")
KEY_TTL, ROUTE_TTL = 600, 600
KIE_GPT = ("gpt-",)


# ───────────────────────── secrets (Bitwarden through walter-secrets) ─────────────────────────
_keys: dict[str, tuple[float, str]] = {}
_keys_lock = threading.Lock()


def provider_key(env_name: str) -> str:
    """Value of the Bitwarden item mapped to `env_name` (secrets-map.json), cached in this process only. A stale
    value is served while it is re-read in the background (a Bitwarden read takes seconds; a phone call cannot wait)."""
    with _keys_lock:
        hit = _keys.get(env_name)
        if hit and time.time() - hit[0] < KEY_TTL:
            return hit[1]
        if hit:
            _keys[env_name] = (time.time(), hit[1])   # one background re-read per TTL
            threading.Thread(target=_read_key, args=(env_name,), daemon=True).start()
            return hit[1]
    return _read_key(env_name)


def _read_key(env_name: str) -> str:
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


_refreshing: set[str] = set()


def _refresh(task: str) -> dict:
    """task = a router task, or task/LEVEL for one of Monsieur's text tiers ("general/L2")."""
    try:
        name, _, level = task.partition("/")
        d = _router("pick", name, *(["--level", level] if level else []))
        _routes[task] = (time.time(), d)
        return d
    finally:
        _refreshing.discard(task)


def decision(task: str) -> dict:
    """The router's routes for a task. A stale entry is served at once and refreshed in the background (a phone call
    must not wait ~5 s for `walter-router pick`); only a task never seen blocks."""
    hit = _routes.get(task)
    if hit and time.time() - hit[0] < ROUTE_TTL:
        return hit[1]
    if hit:
        if task not in _refreshing:
            _refreshing.add(task)
            threading.Thread(target=_refresh, args=(task,), daemon=True).start()
        return hit[1]
    _refreshing.add(task)
    return _refresh(task)


def warm() -> None:
    """Fill the route cache at start-up for every chat task (background)."""
    from concurrent.futures import ThreadPoolExecutor

    def one(t: str) -> None:
        try:
            decision(t)
        except Exception:   # noqa: BLE001 — a task without route answers 400 when asked
            pass
    with ThreadPoolExecutor(4) as pool:   # the phone's poste first
        list(pool.map(one, sorted(chat_tasks(), key=lambda t: t != "voice_assist")))
    for name in ("OPENROUTER_API_KEY", "KIE_API_KEY"):   # Bitwarden reads, before the first call needs them
        try:
            provider_key(name)
        except Exception:   # noqa: BLE001
            pass
    try:   # LiteLLM's first call pays its lazy imports: pay them now
        import litellm
        litellm.get_llm_provider("openrouter/google/gemini-3.8-flash")
    except Exception:   # noqa: BLE001
        pass


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
    if p == "codex":                                          # ChatGPT subscription (Codex models), own login
        if not chatgpt_ready():
            return None
        return {"model": f"chatgpt/{m}"}
    return None


def _codex_tokens() -> dict:
    return json.loads(CODEX_AUTH.read_text()).get("tokens") or {}


def _jwt_exp(token: str) -> float:
    import base64
    part = token.split(".")[1]
    return float(json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("exp", 0))


_codex_lock = threading.Lock()


def codex_access_token() -> str:
    """W.Alter's Codex CLI access token, refreshed through the CLI itself when it expires within the hour."""
    tok = _codex_tokens().get("access_token") or ""
    if tok and _jwt_exp(tok) - time.time() > CODEX_REFRESH_MARGIN:
        return tok
    with _codex_lock:
        tok = _codex_tokens().get("access_token") or ""
        if not tok or _jwt_exp(tok) - time.time() <= CODEX_REFRESH_MARGIN:
            subprocess.run(["codex", "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
                            "-c", "model_reasoning_effort=low", "Réponds OK."], capture_output=True, timeout=180,
                           cwd="/tmp")
            tok = _codex_tokens().get("access_token") or ""
    if not tok or _jwt_exp(tok) <= time.time():
        raise RuntimeError("W.Alter's Codex session has no valid token (codex login)")
    return tok


def _install_codex_auth() -> None:
    """LiteLLM's chatgpt provider reads W.Alter's Codex CLI session (read-only) instead of its own device login."""
    from litellm.llms.chatgpt.authenticator import Authenticator
    Authenticator.get_access_token = lambda self: codex_access_token()
    Authenticator.get_account_id = lambda self: _codex_tokens().get("account_id")


def chatgpt_ready() -> bool:
    try:
        return bool(_codex_tokens().get("access_token"))
    except (OSError, ValueError):
        return False


def json_instruction(fmt: dict) -> str:
    schema = (fmt.get("json_schema") or {}).get("schema")
    return ("Réponds uniquement par un objet JSON valide, sans texte autour ni bloc de code."
            + (f" Il doit respecter exactement ce schéma JSON : {json.dumps(schema, ensure_ascii=False)}" if schema else ""))


def as_json(text: str | None) -> str:
    """The JSON object of a Codex answer; ValueError (= next route, which honours response_format) when there is none."""
    t = (text or "").strip()
    t = t[t.find("{"):t.rfind("}") + 1] if "{" in t else t
    json.loads(t)
    return t


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

    _install_codex_auth()
    litellm.drop_params = True
    litellm.suppress_debug_info = True
    app = FastAPI(title="walter-llm")
    threading.Thread(target=warm, daemon=True).start()

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
            # Kie's endpoints answer a quick Cloudflare 502 on about half the calls (2026-10-16): one retry there
            # costs ~3 s and spares an OpenRouter fallback (paid, low credit)
            kwargs = {**body, **target, "stream": stream, "num_retries": 2 if route["provider"] == "kie" else 0}
            if route.get("reasoning") and route["reasoning"] not in ("none", "non-reasoning"):
                kwargs.setdefault("reasoning_effort", route["reasoning"])
            want_json = route["provider"] == "codex" and (body.get("response_format") or {}).get("type") in (
                "json_object", "json_schema")
            if want_json:   # the Codex backend ignores response_format: ask in words, check the answer below
                kwargs["messages"] = [{"role": "system", "content": json_instruction(body["response_format"])},
                                      *body.get("messages", [])]
            try:
                resp = await litellm.acompletion(**kwargs)
                if want_json and not stream:
                    resp.choices[0].message.content = as_json(resp.choices[0].message.content)
                if not stream:
                    log({**base, "ok": True, "seconds": round(time.perf_counter() - t0, 2),
                         "usage": _usage(resp)})
                    return JSONResponse(resp.model_dump(), headers={"X-Walter-Route": f"{route['provider']}/{route['model']}"})
                it = resp.__aiter__()
                first = await it.__anext__()                  # fail over until the first token arrives
            except Exception as e:
                errors.append(f"{route['provider']}/{route['model']}: {type(e).__name__}: {str(e)[:160]}")
                log({**base, "ok": False, "seconds": round(time.perf_counter() - t0, 2), "error": type(e).__name__,
                     "detail": str(e)[:300], "params": sorted(k for k in body if k != "messages")})
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
    """New token for NAME (one per agent: rotates). cred_file = a DSH credentials YAML, or `env:FILE[:VAR]` = a
    0600 KEY=VALUE file (systemd EnvironmentFile / .env) where only VAR's line is (re)written."""
    token = "wllm_" + secrets.token_urlsafe(32)
    agents = json.loads(AGENTS.read_text()) if AGENTS.exists() else {}
    agents = {h: a for h, a in agents.items() if a["agent"] != name}          # rotate: one token per agent
    agents[hashlib.sha256(token.encode()).hexdigest()] = {"agent": name, "created": datetime.now(timezone.utc).isoformat()}
    AGENTS.write_text(json.dumps(agents, indent=1))
    os.chmod(AGENTS, 0o600)
    if cred_file.startswith("env:"):
        path, _, var = cred_file[4:].partition(":")
        var = var or ref
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [ln for ln in (p.read_text().splitlines() if p.exists() else []) if not ln.startswith(f"{var}=")]
        p.touch(mode=0o600)
        os.chmod(p, 0o600)
        p.write_text("\n".join([*lines, f"{var}={token}"]) + "\n")
        print(f"agent {name}: token written to {p} ({var})")
        return
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
