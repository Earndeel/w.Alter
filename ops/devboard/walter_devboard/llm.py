"""One model reading, guarded. Before any call: the Router must route the poste `devboard_reading` to the required
provider, and at least one subscription account (`subscription_prefix*`) must have a fresh meter under the pause
threshold. Otherwise nothing is sent and the caller waits (`Paused`) — never a silent paid fallback.

The gateway is called with `exact:<picked model>@<required provider>`: the model still comes from the Router, but
the gateway cannot fall through to another provider. The schema travels in the prompt and is checked here (the
subscription bridge refuses response_format json_schema). Readings are memoized in devboard.readings by their exact
inputs: a done reading is never asked twice."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Callable

import httpx
import jsonschema

from .config import Config

PROMPT_VERSION = "1"
POSTE = "devboard_reading"
FRESH_S = 900
MAX_ATTEMPTS = 4
MAX_TOKENS = 8000          # two calls per read, one later read of a failed reading


class Paused(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def key(kind: str, source_ref: str, from_seq: int | None, to_seq: int | None) -> str:
    return hashlib.sha256(f"{kind}|{source_ref}|{from_seq}|{to_seq}|{PROMPT_VERSION}".encode()).hexdigest()


def _router(*args: str):
    out = subprocess.run(["walter-router", *args], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise Paused("route", f"walter-router {' '.join(args)}: {out.stderr.strip()[-300:]}")
    return json.loads(out.stdout) if out.stdout.strip() else {}


def _transport():
    return None


def _accounts(cfg: Config) -> list[dict]:
    return [s for s in _router("subscriptions", "show") or [] if str(s.get("id", "")).startswith(cfg.subscription_prefix)]


def _room(meter: dict | None, cfg: Config) -> bool | None:
    """True/False = fresh meter under/over the threshold, None = unknown or stale."""
    if not meter or meter.get("used_percent") is None or float(meter.get("age_s") or 1e9) > FRESH_S:
        return None
    return float(meter["used_percent"]) < cfg.quota_pause_percent


def _sessions_window(pick: dict, cfg: Config) -> dict[str, float]:
    """5-hour window per subscription account, from the Router pick (shared with the owner's own Claude use)."""
    out = {}
    for e in pick.get("execution") or []:
        sub = e.get("subscription") or {}
        acc = sub.get("account") or e.get("account")
        if e.get("provider") == cfg.required_provider and acc and sub.get("session_used_percent") is not None:
            out[acc] = float(sub["session_used_percent"])
    return out


def gate(cfg: Config) -> dict:
    """Raise Paused unless a call may go; returns the Router pick. An account has room when its weekly meter is
    fresh and under the threshold, and its 5-hour window too."""
    pick = _router("pick", POSTE)
    if pick.get("provider") != cfg.required_provider or not pick.get("model_id"):
        raise Paused("route", f"{POSTE} → {pick.get('provider')}")
    accounts = _accounts(cfg)
    stale = [a["id"] for a in accounts if _room(a.get("meter"), cfg) is None]
    if stale and not any(_room(a.get("meter"), cfg) for a in accounts):
        for sub in stale:
            try:
                _router("subscriptions", "refresh", sub)
            except Paused:
                pass
        accounts = _accounts(cfg)
        pick = _router("pick", POSTE)
    window = _sessions_window(pick, cfg)
    rooms = []
    for a in accounts:
        r = _room(a.get("meter"), cfg)
        if r and window.get(a["id"], 0.0) >= cfg.quota_pause_percent:
            r = False
        rooms.append(r)
    if any(rooms):
        return pick
    if any(r is False for r in rooms):
        raise Paused("quota", ", ".join(
            f"{a['id']} {a['meter']['used_percent']}% (5 h : {window.get(a['id'], '?')}%)"
            for a, r in zip(accounts, rooms) if r is False))
    raise Paused("unknown_quota", ", ".join(a.get("id", "?") for a in accounts) or "no account")


def _token(cfg: Config) -> str:
    if os.environ.get("WALTER_LLM_TOKEN"):
        return os.environ["WALTER_LLM_TOKEN"]
    if cfg.token_file and cfg.token_file.is_file():
        for line in cfg.token_file.read_text().splitlines():
            if line.startswith("WALTER_LLM_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"')
    raise Paused("route", "no walter-llm token")


def _save(conn, k, kind, source_ref, from_seq, to_seq, status, attempts, result=None, error=None) -> None:
    conn.execute("""insert into devboard.readings (key, kind, source_ref, from_seq, to_seq, prompt_version, status,
                                                   attempts, result, error, at)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    on conflict (key) do update set status = excluded.status, attempts = excluded.attempts,
                      result = excluded.result, error = excluded.error, at = now()""",
                 (k, kind, source_ref, from_seq, to_seq, PROMPT_VERSION, status, attempts,
                  json.dumps(result) if result is not None else None, error))


def _save_apart(k, kind, source_ref, from_seq, to_seq, attempts, error) -> None:
    """A failure that must outlive the caller's transaction (it is rolled back by the Paused that follows)."""
    from . import db
    with db.autocommit() as c:
        _save(c, k, kind, source_ref, from_seq, to_seq, "failed", attempts, error=error)


def read(cfg: Config, conn, *, key: str, kind: str, source_ref: str, from_seq: int | None, to_seq: int | None,
         prompt: list[dict], schema: dict, validate: Callable[[dict], None]) -> dict | None:
    row = conn.execute("select status, attempts, result from devboard.readings where key = %s", (key,)).fetchone()
    if row and row["status"] == "done":
        return row["result"]
    attempts = row["attempts"] if row else 0
    if attempts >= MAX_ATTEMPTS:
        return None
    pick = gate(cfg)
    prompt = with_schema(prompt, schema)
    body = {"model": f"exact:{pick['model_id']}@{cfg.required_provider}", "messages": prompt, "temperature": 0,
            "max_tokens": MAX_TOKENS}
    headers = {"Authorization": f"Bearer {_token(cfg)}"}
    error = ""
    with httpx.Client(base_url=cfg.gateway_url, timeout=120, transport=_transport()) as client:
        for _ in range(2):
            attempts += 1
            content = None
            try:
                resp = client.post("/v1/chat/completions", json=body, headers=headers)
            except httpx.HTTPError as e:             # gateway down or too slow: not the slice's fault
                raise Paused("gateway", str(e)[:300])
            route = resp.headers.get("X-Walter-Route", "")
            if resp.status_code == 200 and not route.startswith(cfg.required_provider + "/"):
                _save_apart(key, kind, source_ref, from_seq, to_seq, attempts, f"route {route}")
                raise Paused("route", route)
            if resp.status_code == 429 or resp.status_code >= 500:
                # Rate limited, or every Pro account refused ("every route failed"): pause, keep the attempts.
                raise Paused("quota" if resp.status_code in (429, 502) else "gateway",
                             f"gateway {resp.status_code}: {resp.text[:300]}")
            if resp.status_code != 200:
                error = f"gateway {resp.status_code}: {resp.text[:300]}"
                continue
            try:
                content = resp.json()["choices"][0]["message"]["content"] or ""
                result = json.loads(_strip_fence(content))
                if not isinstance(result, dict):
                    raise ValueError("answer is not an object")
                jsonschema.validate(result, schema)
                validate(result)
            except (ValueError, KeyError, IndexError, TypeError, jsonschema.ValidationError) as e:
                if isinstance(e, jsonschema.ValidationError):
                    e = ValueError(f"{e.message} (at {'/'.join(map(str, e.absolute_path)) or 'root'})")
                error = f"invalid answer: {e}"
                body["messages"] = list(prompt) + [
                    {"role": "assistant", "content": str(content or "")[:4000]},
                    {"role": "user", "content": f"Réponse refusée : {e}. Corrige et renvoie le JSON complet."}]
                continue
            _save(conn, key, kind, source_ref, from_seq, to_seq, "done", attempts, result=result)
            return result
    _save(conn, key, kind, source_ref, from_seq, to_seq, "failed", attempts, error=error[:1000])
    return None


def with_schema(prompt: list[dict], schema: dict) -> list[dict]:
    """The Claude subscription bridge refuses response_format json_schema (BadRequest, 2026-11-14): the schema goes
    at the end of the system message and the answer is checked here against it."""
    rule = ("\n\nRéponds uniquement par un objet JSON, sans texte autour, conforme à ce schéma JSON :\n"
            + json.dumps(schema, ensure_ascii=False))
    msgs = [dict(m) for m in prompt]
    if msgs and msgs[0].get("role") == "system":
        msgs[0]["content"] = str(msgs[0]["content"]) + rule
    else:
        msgs.insert(0, {"role": "system", "content": rule.strip()})
    return msgs


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t.strip()
