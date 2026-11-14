"""One model reading, guarded. Before any call: the Router must route the poste `devboard_reading` to the required
provider, and at least one subscription account (`subscription_prefix*`) must have a fresh meter under the pause
threshold. Otherwise nothing is sent and the caller waits (`Paused`) — never a silent paid fallback.

The gateway is called with `exact:<picked model>@<required provider>`: the model still comes from the Router, but
the gateway cannot fall through to another provider. Readings are memoized in devboard.readings by their exact
inputs: a done reading is never asked twice."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Callable

import httpx

from .config import Config

PROMPT_VERSION = "1"
POSTE = "devboard_reading"
FRESH_S = 900
MAX_ATTEMPTS = 4          # two calls per read, one later read of a failed reading


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


def gate(cfg: Config) -> dict:
    """Raise Paused unless a call may go; returns the Router pick."""
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
    rooms = [_room(a.get("meter"), cfg) for a in accounts]
    if any(rooms):
        return pick
    if any(r is False for r in rooms):
        raise Paused("quota", ", ".join(f"{a['id']} {a['meter']['used_percent']}%" for a, r in zip(accounts, rooms)
                                        if r is False))
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


def read(cfg: Config, conn, *, key: str, kind: str, source_ref: str, from_seq: int | None, to_seq: int | None,
         prompt: list[dict], schema: dict, validate: Callable[[dict], None]) -> dict | None:
    row = conn.execute("select status, attempts, result from devboard.readings where key = %s", (key,)).fetchone()
    if row and row["status"] == "done":
        return row["result"]
    attempts = row["attempts"] if row else 0
    if attempts >= MAX_ATTEMPTS:
        return None
    pick = gate(cfg)
    body = {"model": f"exact:{pick['model_id']}@{cfg.required_provider}", "messages": prompt, "temperature": 0,
            "response_format": {"type": "json_schema", "json_schema": {"name": kind, "schema": schema}}}
    headers = {"Authorization": f"Bearer {_token(cfg)}"}
    error = ""
    with httpx.Client(base_url=cfg.gateway_url, timeout=120, transport=_transport()) as client:
        for _ in range(2):
            attempts += 1
            try:
                resp = client.post("/v1/chat/completions", json=body, headers=headers)
            except httpx.HTTPError as e:
                error = f"gateway: {e}"
                continue
            route = resp.headers.get("X-Walter-Route", "")
            if resp.status_code == 200 and not route.startswith(cfg.required_provider + "/"):
                _save(conn, key, kind, source_ref, from_seq, to_seq, "failed", attempts, error=f"route {route}")
                raise Paused("route", route)
            if resp.status_code != 200:
                error = f"gateway {resp.status_code}: {resp.text[:300]}"
                if resp.status_code == 429:
                    _save(conn, key, kind, source_ref, from_seq, to_seq, "failed", attempts - 1, error=error)
                    raise Paused("quota", error)
                continue
            try:
                content = resp.json()["choices"][0]["message"]["content"] or ""
                result = json.loads(_strip_fence(content))
                if not isinstance(result, dict):
                    raise ValueError("answer is not an object")
                validate(result)
            except (ValueError, KeyError, IndexError, TypeError) as e:
                error = f"invalid answer: {e}"
                continue
            _save(conn, key, kind, source_ref, from_seq, to_seq, "done", attempts, result=result)
            return result
    _save(conn, key, kind, source_ref, from_seq, to_seq, "failed", attempts, error=error[:1000])
    return None


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t.strip()
