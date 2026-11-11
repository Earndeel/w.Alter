"""One-shot answers for the Router's own needs (lot E6, 2026-11-10: no longer through Hermes).

Two paths, by what the question needs:
  • a plain answer (proposal recommendation, a prompt rewrite): the economical direct path — one call to the model
    gateway walter-llm on the owner's economic tier (`general/L1`), no agent loop;
  • an answer that needs tools (the plans research on the web): one delegation to Walter Engine (Engine API
    `delegate`, the same door as walter_run text jobs), under the engine's policy, run and budget.
Either path failing returns None (the callers keep their fallback); nothing is retried elsewhere.

The Router's walter-llm agent token lives in the instance (`@instance/bootstrap/llm/walter-router.env`,
WALTER_LLM_TOKEN, 0600; `gateway.py add-agent walter-router env:<that file>` rotates it)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid

from walter_router import instance

LLM_URL = os.environ.get("WALTER_LLM_URL", "http://127.0.0.1:8894")
TOKEN_FILE = "@instance/bootstrap/llm/walter-router.env"
ECONOMIC = "general/L1"


def _llm_token() -> str | None:
    if os.environ.get("WALTER_LLM_TOKEN"):
        return os.environ["WALTER_LLM_TOKEN"]
    try:
        for line in instance._expand(TOKEN_FILE).read_text().splitlines():
            if line.startswith("WALTER_LLM_TOKEN="):
                return line.split("=", 1)[1].strip() or None
    except OSError:
        return None
    return None


def complete(prompt: str, source: str, *, task: str = ECONOMIC, timeout: int = 240, max_tokens: int = 2000) -> str | None:
    """One completion from walter-llm (task = a Router poste; `general/L1` = economic tier). None on any failure."""
    token = _llm_token()
    if not token:
        return None
    body = {"model": task, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens,
            "user": source}
    req = urllib.request.Request(LLM_URL.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.load(r)
        text = out["choices"][0]["message"]["content"] or ""
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    return text.strip().strip('"') or None


STT_PROMPT = ("Transcris exactement cette note vocale, dans sa langue, sans rien ajouter ni résumer. "
              "S'il n'y a aucune parole, réponds seulement [silence].")
AUDIO_FORMATS = {".oga": "ogg", ".ogg": "ogg", ".opus": "ogg", ".mp3": "mp3", ".m4a": "m4a", ".wav": "wav",
                 ".mp4": "mp4", ".webm": "webm", ".flac": "flac", ".aac": "aac"}
STT_MAX_BYTES = 25 * 1024 * 1024


def transcribe(path: str, source: str = "walter-router", *, task: str = "stt", timeout: int = 180) -> dict:
    """One audio file → its transcript by the Router's `stt` poste through walter-llm (2026-11-11: the capability
    every runtime reaches through MCP `audio_transcribe`; before, the engine had no door to it and tried provider keys
    under `walter-secret exec`, whose output is discarded by design). Returns {file, ok, text|error}; never raises."""
    import base64
    from pathlib import Path as _P
    f = _P(path)
    out = {"file": str(f)}
    fmt = AUDIO_FORMATS.get(f.suffix.lower())
    if fmt is None:
        return {**out, "ok": False, "error": f"unsupported audio format {f.suffix or '(none)'}"}
    try:
        size = f.stat().st_size
    except OSError:
        return {**out, "ok": False, "error": "file not found"}
    if size > STT_MAX_BYTES:
        return {**out, "ok": False, "error": "file larger than 25 MB"}
    token = _llm_token()
    if not token:
        return {**out, "ok": False, "error": "no walter-llm token for the Router"}
    body = {"model": task, "max_tokens": 4000, "user": source, "messages": [{"role": "user", "content": [
        {"type": "input_audio", "input_audio": {"data": base64.b64encode(f.read_bytes()).decode("ascii"), "format": fmt}},
        {"type": "text", "text": STT_PROMPT}]}]}
    req = urllib.request.Request(LLM_URL.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (local gateway)
            text = (json.load(r)["choices"][0]["message"]["content"] or "").strip()
    except urllib.error.HTTPError as e:
        return {**out, "ok": False, "error": f"stt HTTP {e.code}"}
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return {**out, "ok": False, "error": f"stt {type(e).__name__}"}
    if not text or text == "[silence]":
        return {**out, "ok": True, "text": "", "note": "no speech"}
    return {**out, "ok": True, "text": text}


def delegate(prompt: str, source: str, *, timeout: int = 900, task: str = "general") -> str | None:
    """One task for Walter Engine (Engine API `delegate`): tools, policy and run are the engine's."""
    from walter_router.serve import engine
    budget = max(60, min(int(timeout), 3600))
    delegation = {"version": 1, "goal": prompt, "task": task, "budget_seconds": budget,
                  "idempotency_key": f"{source}-{uuid.uuid4()}",
                  "parent": {"run_id": os.environ.get("WALTER_RUN_ID"), "task_id": None, "depth": 0}}
    try:
        status, out = engine._post(engine.binding(), {"op": "delegate", "delegation": delegation, "caller": source},
                                   timeout=budget + 60)
    except (OSError, ValueError):
        return None
    r = out.get("result") or out
    if status != 200 or not r.get("ok"):
        return None
    return (r.get("output") or "").strip() or None


def ask_l1(conn, prompt: str, source: str, timeout: int = 240, tools: str = "memory", max_turns: int = 1) -> str | None:
    """Former Hermes one-shot, same signature: no tool use → economical direct path; tools (web…) → the engine."""
    if tools in (None, "", "memory") and max_turns <= 1:
        return complete(prompt, source, timeout=timeout)
    return delegate(prompt, source, timeout=timeout)
