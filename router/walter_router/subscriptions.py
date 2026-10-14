"""Monsieur's subscriptions: usage meters, what each plan is worth, and whether its routes may be used right now.

config/subscriptions.json declares the plans (Monsieur's word, never inferred). A subscription route costs nothing
per call while its quota lasts, so it stays first (DESIGN §6) — until its meter says otherwise:
  ok         below reserve_percent of every window → first, as before;
  reserve    at reserve_percent or more → sub-tasks go to paid routes first, the rest is kept for the Hermes
             conversation that runs on the same subscription;
  exhausted  at exhausted_percent or more → last everywhere;
  unknown    no fresh reading → treated as ok (fail-open: the run itself falls back on a quota error).
Readings: Codex from its usage API through Hermes (read-only, the token never leaves Hermes); Claude Pro has no
login on the VM, so its weekly meter is estimated from the Claude Code transcripts and can be calibrated against
the percentage shown on claude.ai.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config" / "subscriptions.json"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
HERMES_PY = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python"
CLAUDE_PROJECTS = Path(os.environ.get("CLAUDE_PROJECTS", "/root/.claude/projects"))
STALE_S = {"codex_usage_api": 6 * 3600, "estimate_claude_code_logs": 24 * 3600}
WINDOW_NAMES = {"Session": "session", "Weekly": "weekly"}
WEEK = timedelta(days=7)


def load() -> list[dict]:
    return json.loads(CONFIG.read_text())["subscriptions"]


def get(sub_id: str) -> dict:
    for s in load():
        if s["id"] == sub_id:
            return s
    raise KeyError(f"unknown subscription {sub_id!r} (config/subscriptions.json)")


# --- meters -------------------------------------------------------------------------------------------------------

def read_codex() -> list[dict]:
    """Live Codex windows of Monsieur's ChatGPT account, through Hermes' own usage fetcher (read-only)."""
    code = ("import json; from agent.account_usage import fetch_account_usage; s = fetch_account_usage('openai-codex'); "
            "print(json.dumps(None if s is None else {'plan': s.plan, 'windows': [{'label': w.label, "
            "'used_percent': w.used_percent, 'reset_at': w.reset_at.isoformat() if w.reset_at else None} "
            "for w in s.windows]}))")
    out = subprocess.run([str(HERMES_PY), "-c", code], cwd=str(HERMES_HOME / "hermes-agent"), capture_output=True,
                         text=True, timeout=60, env={**os.environ, "HERMES_HOME": str(HERMES_HOME)})
    data = json.loads(out.stdout.strip().splitlines()[-1]) if out.returncode == 0 and out.stdout.strip() else None
    if not data or not data.get("windows"):
        raise ValueError(f"codex usage unavailable (exit {out.returncode})")
    return [{"window": WINDOW_NAMES.get(w["label"], w["label"].lower()), "used_percent": float(w["used_percent"]),
             "resets_at": w["reset_at"], "detail": {"plan": data.get("plan")}} for w in data["windows"]]


def units(usage: dict, weights: dict) -> float:
    """Meter units of one Claude call: what moves the subscription meter, cache reads ~free."""
    return (usage.get("input_tokens", 0) * weights["input"]
            + usage.get("cache_creation_input_tokens", 0) * weights["cache_write"]
            + usage.get("cache_read_input_tokens", 0) * weights["cache_read"]
            + usage.get("output_tokens", 0) * weights["output"])


def claude_units(since: datetime, weights: dict, models: list[str], root: Path = CLAUDE_PROJECTS) -> dict:
    """Weighted units of the plan's models in the Claude Code transcripts since `since` (deduplicated per call)."""
    seen: set = set()
    total, calls, files = 0.0, 0, 0
    floor = since.timestamp() - 3600
    for path in root.glob("**/*.jsonl"):
        if path.stat().st_mtime < floor:
            continue
        files += 1
        with path.open(errors="ignore") as fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                m = d.get("message") if d.get("type") == "assistant" else None
                if not isinstance(m, dict) or not m.get("usage") or m.get("model") not in models:
                    continue
                key = (m.get("id"), d.get("requestId"))
                ts = d.get("timestamp")
                if key in seen or not ts or datetime.fromisoformat(ts.replace("Z", "+00:00")) < since:
                    continue
                seen.add(key)
                total += units(m["usage"], weights)
                calls += 1
    return {"units": total, "calls": calls, "files": files}


def estimate_claude(sub: dict, now: datetime | None = None) -> list[dict]:
    """Rolling-7-day estimate of the weekly meter (the weekly limit binds before the 5-hour one)."""
    now = now or datetime.now(timezone.utc)
    meter = sub["meter"]
    used = claude_units(now - WEEK, meter["weights"], sub["models"])
    pct = 100.0 * used["units"] / meter["weekly_capacity_units"]
    return [{"window": "weekly", "used_percent": round(min(pct, 999.0), 2), "resets_at": None,
             "detail": {**used, "capacity_units": meter["weekly_capacity_units"], "rolling": "7 days",
                        "capacity_basis": meter["capacity_basis"]}}]


READERS = {"codex_usage_api": lambda sub: read_codex(), "estimate_claude_code_logs": estimate_claude}


def record(conn, sub_id: str, windows: list[dict], source: str, estimated: bool) -> None:
    for w in windows:
        conn.execute("""insert into models.subscription_usage (sub_id, window_name, used_percent, resets_at, source,
                        estimated, detail) values (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
                     (sub_id, w["window"], w["used_percent"], w["resets_at"], source, estimated,
                      json.dumps(w.get("detail") or {}, default=str)))


def refresh(conn, only: str | None = None, min_age_s: float = 0) -> dict:
    """Read every subscription meter (or one); skip a meter read less than `min_age_s` ago."""
    out = {}
    for sub in load():
        if only and sub["id"] != only:
            continue
        source = sub["meter"]["source"]
        last = conn.execute("""select extract(epoch from now() - max(read_at)) as age from models.subscription_usage
                               where sub_id = %s and source = %s""", (sub["id"], source)).fetchone()["age"]
        if last is not None and float(last) < min_age_s:
            out[sub["id"]] = {"skipped": f"read {float(last):.0f} s ago"}
            continue
        try:
            windows = READERS[source](sub)
        except Exception as exc:  # noqa: BLE001 — one meter down never blocks the others
            out[sub["id"]] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
            continue
        record(conn, sub["id"], windows, source, estimated=source.startswith("estimate"))
        out[sub["id"]] = {w["window"]: w["used_percent"] for w in windows}
    return out


def calibrate(conn, sub_id: str, weekly_percent: float) -> dict:
    """Monsieur read the weekly % on claude.ai: capacity = units of the last 7 days / that %. Written to the config."""
    sub = get(sub_id)
    meter = sub["meter"]
    if meter["source"] != "estimate_claude_code_logs":
        raise ValueError(f"{sub_id} is read from its vendor, nothing to calibrate")
    if not 1 <= weekly_percent <= 100:
        raise ValueError("weekly_percent must be between 1 and 100 (a reading near 0 says nothing about capacity)")
    used = claude_units(datetime.now(timezone.utc) - WEEK, meter["weights"], sub["models"])
    capacity = int(used["units"] / (weekly_percent / 100))
    doc = json.loads(CONFIG.read_text())
    for s in doc["subscriptions"]:
        if s["id"] == sub_id:
            s["meter"]["weekly_capacity_units"] = capacity
            s["meter"]["capacity_basis"] = (f"calibrated {datetime.now(timezone.utc):%Y-%m-%d}: {weekly_percent:g} % "
                                            f"weekly on claude.ai for {used['units'] / 1e6:.1f} M units in the last 7 days")
    tmp = CONFIG.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(CONFIG)
    record(conn, sub_id, [{"window": "weekly", "used_percent": weekly_percent, "resets_at": None,
                           "detail": {**used, "capacity_units": capacity}}], "calibration", estimated=False)
    return {"sub_id": sub_id, "weekly_capacity_units": capacity, "units_7d": used["units"]}


# --- state --------------------------------------------------------------------------------------------------------

def classify(windows: list[dict], policy: dict, now: datetime | None = None) -> dict:
    """ok / reserve / exhausted / unknown from the latest windows; a window past its reset time counts as 0 %."""
    now = now or datetime.now(timezone.utc)
    live = []
    for w in windows:
        resets = w.get("resets_at")
        if isinstance(resets, str):
            resets = datetime.fromisoformat(resets)
        stale = w.get("age_s") is not None and w["age_s"] > STALE_S.get(w.get("source"), 6 * 3600)
        if stale:
            continue
        live.append(0.0 if resets and resets <= now else float(w["used_percent"]))
    if not live:
        return {"status": "unknown", "used_percent": None}
    used = max(live)
    status = ("exhausted" if used >= policy["exhausted_percent"] else
              "reserve" if used >= policy["reserve_percent"] else "ok")
    return {"status": status, "used_percent": used}


def values(sub: dict) -> list[dict]:
    """Each published plan value with what Monsieur pays per API-dollar at full use (price / value)."""
    return [{**v, "pays_per_api_dollar": round(sub["price_usd_month"] / v["usd_month"], 4),
             "multiple": round(v["usd_month"] / sub["price_usd_month"], 1)} for v in sub.get("plan_values", [])]


def state(conn) -> list[dict]:
    rows = conn.execute("""select sub_id, window_name, used_percent, resets_at, source, estimated, read_at, detail,
                                  extract(epoch from now() - read_at) as age_s from models.latest_subscription_usage
                           where source <> 'calibration'""").fetchall()
    out = []
    for sub in load():
        windows = [{"window": r["window_name"], "used_percent": float(r["used_percent"]), "resets_at": r["resets_at"],
                    "source": r["source"], "estimated": r["estimated"], "read_at": r["read_at"],
                    "age_s": float(r["age_s"])} for r in rows if r["sub_id"] == sub["id"]]
        out.append({"id": sub["id"], "plan": f'{sub["vendor"]} {sub["plan"]}', "price_usd_month": sub["price_usd_month"],
                    "execution": sub["execution"], "route_provider": sub.get("route_provider"),
                    **classify(windows, sub["policy"]), "windows": windows, "values": values(sub)})
    return out


_CACHE: dict = {"at": 0.0, "by_provider": {}}


def route_status(conn, provider: str) -> dict:
    """Quota status of the subscription behind a route provider (codex), cached 60 s per process."""
    if time.monotonic() - _CACHE["at"] > 60:
        try:
            _CACHE["by_provider"] = {s["route_provider"]: s for s in state(conn) if s["route_provider"]}
        except Exception:  # noqa: BLE001 — table missing / db hiccup: behave as before (subscription first)
            _CACHE["by_provider"] = {}
        _CACHE["at"] = time.monotonic()
    s = _CACHE["by_provider"].get(provider)
    return {"status": s["status"], "used_percent": s["used_percent"], "sub_id": s["id"]} if s else \
        {"status": "unknown", "used_percent": None, "sub_id": None}
