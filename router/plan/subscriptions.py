"""The owner's subscriptions — information only, no routing effect (2026-10-14).

Two sources, nothing else: our own measurement and SemiAnalysis (config/subscriptions.json).
  Our measurement
    meter      ChatGPT Plus: the real weekly % from the Codex usage API, through Hermes (read-only, the token never
               leaves Hermes). Claude Pro: no Claude login on the VM → weekly % estimated from the Claude Code
               transcripts (units over a capacity, calibrable with the % shown on claude.ai).
    usage      tokens W.Alter's runtimes really spent on each plan (Hermes + Codex CLI on ChatGPT, Claude Code on
               Claude), priced at list API rates → API value consumed and what a million tokens cost at this pace.
    capacity   ChatGPT: API value per meter point between two readings of the same week (Wokey / SemiAnalysis
               method on the owner's account) → a full week, a full month. Claude: once calibrated.
  SemiAnalysis
    published API value of the plan per model (2026-10-05) and the tokens it buys on their agentic mix.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from walter_router.analysis import identity
from walter_router.analysis import select as sel
from walter_router import instance

CONFIG = instance.config_path("subscriptions.json")
HERMES_HOME = instance.hermes_home()
HERMES_PY = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python"
CLAUDE_PROJECTS = Path(os.environ.get("CLAUDE_PROJECTS") or Path.home() / ".claude" / "projects")
CODEX_SESSIONS = Path(os.environ.get("CODEX_SESSIONS") or Path.home() / ".codex" / "sessions")
WEEK = timedelta(days=7)
MONTH_WEEKS = 30.44 / 7
KINDS = ("input", "cache_read", "cache_write", "cache_write_1h", "output")
MIN_POINTS = 3  # meter points between two readings before we trust a capacity (Codex reports whole percents)


def doc() -> dict:
    return json.loads(CONFIG.read_text())


def load() -> list[dict]:
    return doc()["subscriptions"]


def get(sub_id: str) -> dict:
    for s in load():
        if s["id"] == sub_id:
            return s
    raise KeyError(f"unknown subscription {sub_id!r} (config/subscriptions.json)")


# --- token usage, per model -----------------------------------------------------------------------------------------

def _add(acc: dict, model: str, **kinds: float) -> None:
    row = acc.setdefault(model, dict.fromkeys(KINDS, 0))
    for k, v in kinds.items():
        row[k] += v or 0


def claude_code_usage(since: datetime | None, root: Path = CLAUDE_PROJECTS) -> dict:
    """Tokens per Claude model in the Claude Code transcripts (each API call once)."""
    acc: dict = {}
    seen: set = set()
    floor = since.timestamp() - 3600 if since else 0
    for path in root.glob("**/*.jsonl"):
        if path.stat().st_mtime < floor:
            continue
        with path.open(errors="ignore") as fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                m = d.get("message") if d.get("type") == "assistant" else None
                if not isinstance(m, dict) or not m.get("usage") or not str(m.get("model", "")).startswith("claude"):
                    continue
                key, ts = (m.get("id"), d.get("requestId")), d.get("timestamp")
                if key in seen or not ts or (since and datetime.fromisoformat(ts.replace("Z", "+00:00")) < since):
                    continue
                seen.add(key)
                u = m["usage"]
                cc = u.get("cache_creation") or {}
                one_h = cc.get("ephemeral_1h_input_tokens") or 0
                _add(acc, m["model"], input=u.get("input_tokens"), cache_read=u.get("cache_read_input_tokens"),
                     cache_write=(u.get("cache_creation_input_tokens") or 0) - one_h, cache_write_1h=one_h,
                     output=u.get("output_tokens"))
    return acc


def hermes_codex_usage(since: datetime | None, home: Path = HERMES_HOME) -> dict:
    """Tokens per model of Hermes sessions billed to the ChatGPT subscription (main + every profile, read-only)."""
    acc: dict = {}
    for db in [home / "state.db", *sorted(home.glob("profiles/*/state.db"))]:
        if not db.exists():
            continue
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            rows = con.execute("""select model, sum(input_tokens), sum(cache_read_tokens), sum(cache_write_tokens),
                                  sum(output_tokens) from sessions where billing_provider = 'openai-codex'
                                  and coalesce(last_activity_at, started_at) >= ? group by model""",
                               (since.timestamp() if since else 0,)).fetchall()
        except sqlite3.Error:
            rows = []
        finally:
            con.close()
        for model, i, cr, cw, o in rows:
            _add(acc, identity.normalize("codex", model or "")[0], input=i, cache_read=cr, cache_write=cw, output=o)
    return acc


def codex_cli_usage(since: datetime | None, root: Path = CODEX_SESSIONS) -> dict:
    """Tokens per model of Codex CLI / Codex Desktop sessions (last cumulative token_count of each session)."""
    acc: dict = {}
    floor = since.timestamp() if since else 0
    for path in root.glob("**/*.jsonl"):
        if path.stat().st_mtime < floor:
            continue
        total, model = None, None
        with path.open(errors="ignore") as fh:
            for line in fh:
                if '"total_token_usage"' in line or '"model"' in line:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    p = d.get("payload") or {}
                    info = p.get("info") if isinstance(p, dict) else None
                    if isinstance(info, dict) and info.get("total_token_usage"):
                        total = info["total_token_usage"]
                    if isinstance(p, dict) and isinstance(p.get("model"), str):
                        model = p["model"]
        if total and model:
            cached = total.get("cached_input_tokens") or 0
            _add(acc, identity.normalize("codex", model)[0], input=(total.get("input_tokens") or 0) - cached,
                 cache_read=cached, cache_write=total.get("cache_write_input_tokens"), output=total.get("output_tokens"))
    return acc


USAGE = {"claude_code": claude_code_usage, "hermes_codex": hermes_codex_usage, "codex_cli": codex_cli_usage}


def usage(sub: dict, since: datetime | None) -> dict:
    acc: dict = {}
    for src in sub["usage_sources"]:
        for model, row in USAGE[src](since).items():
            _add(acc, model, **row)
    return acc


def list_prices(conn) -> dict:
    """$ per million tokens at list API rates (OpenRouter's first-party pricing) per model."""
    out = {}
    for model, offers in sel.load_offers(conn, sel.latest_snapshots(conn)).items():
        p = next((o.get("pricing") or {} for o in offers if o["provider"] == "openrouter" and o["interface"] == "chat"),
                 None)
        if not p or not p.get("prompt"):
            continue
        f = lambda k, d: float(p.get(k) or d) * 1e6  # noqa: E731
        inp = f("prompt", 0)
        out[model] = {"input": inp, "output": f("completion", 0), "cache_read": f("input_cache_read", p["prompt"]),
                      "cache_write": f("input_cache_write", p["prompt"]),
                      "cache_write_1h": f("input_cache_write_1h", p.get("input_cache_write") or p["prompt"])}
    return out


def priced(acc: dict, prices: dict) -> dict:
    """Totals of a usage dict + its API value; models without a list price are counted but not valued."""
    tokens = {k: sum(r[k] for r in acc.values()) for k in KINDS}
    value, unpriced = 0.0, []
    for model, r in acc.items():
        p = prices.get(model)
        if not p:
            unpriced.append(model)
            continue
        value += sum(r[k] * p[k] for k in KINDS) / 1e6
    return {"tokens": tokens, "total_tokens": sum(tokens.values()), "api_value_usd": round(value, 2),
            "unpriced_models": unpriced, "by_model": acc}


# --- meters ---------------------------------------------------------------------------------------------------------

def read_codex() -> list[dict]:
    """Live Codex windows of the owner's ChatGPT account, through Hermes' own usage fetcher (read-only)."""
    code = ("import json; from agent.account_usage import fetch_account_usage; s = fetch_account_usage('openai-codex'); "
            "print(json.dumps(None if s is None else {'plan': s.plan, 'windows': [{'label': w.label, "
            "'used_percent': w.used_percent, 'reset_at': w.reset_at.isoformat() if w.reset_at else None} "
            "for w in s.windows]}))")
    out = subprocess.run([str(HERMES_PY), "-c", code], cwd=str(HERMES_HOME / "hermes-agent"), capture_output=True,
                         text=True, timeout=60, env={**os.environ, "HERMES_HOME": str(HERMES_HOME)})
    data = json.loads(out.stdout.strip().splitlines()[-1]) if out.returncode == 0 and out.stdout.strip() else None
    if not data or not data.get("windows"):
        raise ValueError(f"codex usage unavailable (exit {out.returncode})")
    return [{"window": {"Session": "session", "Weekly": "weekly"}.get(w["label"], w["label"].lower()),
             "used_percent": float(w["used_percent"]), "resets_at": w["reset_at"], "detail": {"plan": data.get("plan")}}
            for w in data["windows"]]


def units(row: dict, weights: dict) -> float:
    """Meter units of a token row: what moves the Claude meter, cache reads ~free."""
    return (row["input"] * weights["input"] + (row["cache_write"] + row["cache_write_1h"]) * weights["cache_write"]
            + row["cache_read"] * weights["cache_read"] + row["output"] * weights["output"])


def claude_week_units(sub: dict, now: datetime | None = None) -> float:
    acc = claude_code_usage((now or datetime.now(timezone.utc)) - WEEK)
    return sum(units(r, sub["meter"]["weights"]) for m, r in acc.items() if m in sub["models"])


def estimate_claude(sub: dict) -> list[dict]:
    meter = sub["meter"]
    u = claude_week_units(sub)
    return [{"window": "weekly", "used_percent": round(min(100.0 * u / meter["weekly_capacity_units"], 999.0), 2),
             "resets_at": None, "detail": {"units_7d": u, "capacity_units": meter["weekly_capacity_units"],
                                           "calibrated": meter.get("calibrated", False)}}]


def record(conn, sub_id: str, windows: list[dict], source: str, estimated: bool) -> None:
    for w in windows:
        conn.execute("""insert into models.subscription_usage (sub_id, window_name, used_percent, resets_at, source,
                        estimated, detail) values (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
                     (sub_id, w["window"], w["used_percent"], w["resets_at"], source, estimated,
                      json.dumps(w.get("detail") or {}, default=str)))


def refresh(conn, only: str | None = None, min_age_s: float = 0) -> dict:
    """Read every meter (or one); skip a meter read less than `min_age_s` ago. A ChatGPT reading carries the
    cumulative tokens of the plan at that moment, so two readings give the API value of a meter point."""
    out = {}
    prices = None
    for sub in load():
        if only and sub["id"] != only:
            continue
        source = (sub.get("meter") or {}).get("source") or "none"
        if source == "none":   # a plan without a readable meter (Google AI Pro: Flow credits, Colab)
            continue
        last = conn.execute("""select extract(epoch from now() - max(read_at)) as age from models.subscription_usage
                               where sub_id = %s and source = %s""", (sub["id"], source)).fetchone()["age"]
        if last is not None and float(last) < min_age_s:
            out[sub["id"]] = {"skipped": f"read {float(last):.0f} s ago"}
            continue
        try:
            if source == "codex_usage_api":
                windows = read_codex()
                prices = prices or list_prices(conn)
                cumul = priced(usage(sub, None), prices)
                for w in windows:
                    w["detail"]["cumulative_api_value_usd"] = cumul["api_value_usd"]
                    w["detail"]["cumulative_tokens"] = cumul["total_tokens"]
            else:
                windows = estimate_claude(sub)
        except Exception as exc:  # noqa: BLE001 — one meter down never blocks the others
            out[sub["id"]] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
            continue
        record(conn, sub["id"], windows, source, estimated=source.startswith("estimate"))
        out[sub["id"]] = {w["window"]: w["used_percent"] for w in windows}
    return out


def calibrate(conn, sub_id: str, weekly_percent: float) -> dict:
    """The owner read the weekly % on claude.ai: capacity = units of the last 7 days / that %. Written to the config."""
    sub = get(sub_id)
    if sub["meter"]["source"] != "estimate_claude_code_logs":
        raise ValueError(f"{sub_id} is read from its vendor, nothing to calibrate")
    if not 1 <= weekly_percent <= 100:
        raise ValueError("weekly_percent must be between 1 and 100 (a reading near 0 says nothing about capacity)")
    u = claude_week_units(sub)
    capacity = int(u / (weekly_percent / 100))
    d = doc()
    for s in d["subscriptions"]:
        if s["id"] == sub_id:
            s["meter"].update(weekly_capacity_units=capacity, calibrated=True,
                              capacity_basis=f"calibrated {datetime.now(timezone.utc):%Y-%m-%d}: {weekly_percent:g} % "
                                             f"weekly on claude.ai for {u / 1e6:.1f} M units in the last 7 days")
    tmp = CONFIG.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(CONFIG)
    record(conn, sub_id, [{"window": "weekly", "used_percent": weekly_percent, "resets_at": None,
                           "detail": {"units_7d": u, "capacity_units": capacity}}], "calibration", estimated=False)
    return {"sub_id": sub_id, "weekly_capacity_units": capacity, "units_7d": u}


# --- what the plan is worth -----------------------------------------------------------------------------------------

def blended(prices: dict, mix: dict) -> float:
    """$ per million tokens of a model on SemiAnalysis' workload mix."""
    return sum(prices[k] * share for k, share in mix.items())


def measured_point_value(readings: list[dict]) -> dict | None:
    """API value per meter point from ChatGPT readings of one weekly window (oldest → newest of the window with the
    most points). Usage outside the VM moves the meter without tokens here, so this is a floor."""
    by_window: dict = {}
    for r in readings:
        if r["detail"].get("cumulative_api_value_usd") is not None and r["resets_at"]:
            by_window.setdefault(r["resets_at"], []).append(r)
    best = None
    for resets, rs in by_window.items():
        rs = sorted(rs, key=lambda r: r["read_at"])
        dp = float(rs[-1]["used_percent"]) - float(rs[0]["used_percent"])
        dv = rs[-1]["detail"]["cumulative_api_value_usd"] - rs[0]["detail"]["cumulative_api_value_usd"]
        if dp >= MIN_POINTS and dv > 0 and (best is None or dp > best["points"]):
            best = {"points": dp, "api_value_usd": round(dv, 2), "usd_per_point": round(dv / dp, 3),
                    "week_usd": round(100 * dv / dp, 0), "month_usd": round(100 * dv / dp * MONTH_WEEKS, 0),
                    "from": rs[0]["read_at"], "to": rs[-1]["read_at"]}
    return best


def state(conn) -> list[dict]:
    """Everything the library shows, per subscription."""
    d = doc()
    mix = d["semianalysis"]["workload_mix"]
    prices = list_prices(conn)
    latest = conn.execute("""select * , extract(epoch from now() - read_at) as age_s
                             from models.latest_subscription_usage where source <> 'calibration'""").fetchall()
    week_ago = datetime.now(timezone.utc) - WEEK
    out = []
    for sub in d["subscriptions"]:
        meter = next((r for r in latest if r["sub_id"] == sub["id"] and r["window_name"] == "weekly"), None)
        used = priced(usage(sub, week_ago), prices)
        weekly_price = sub["price_usd_month"] / MONTH_WEEKS
        semi = []
        for v in sub.get("semianalysis_values", []):
            p = prices.get(v["model_id"])
            per_m = blended(p, mix) if p else None
            tokens = v["usd_month"] / per_m * 1e6 if per_m else None
            semi.append({**v, "multiple": round(v["usd_month"] / sub["price_usd_month"], 1),
                         "tokens_month": tokens, "usd_per_m_full": sub["price_usd_month"] / tokens * 1e6 if tokens else None})
        mine = None
        if sub["meter"]["source"] == "codex_usage_api":
            rs = conn.execute("""select used_percent, resets_at, read_at, detail from models.subscription_usage
                                 where sub_id = %s and window_name = 'weekly' and source = 'codex_usage_api'
                                 and read_at > now() - interval '35 days' order by read_at""", (sub["id"],)).fetchall()
            mine = measured_point_value(rs)
        elif sub["meter"].get("calibrated") and meter and float(meter["used_percent"]) > 0:
            pct = float(meter["used_percent"])
            mine = {"week_usd": round(used["api_value_usd"] * 100 / pct, 0),
                    "month_usd": round(used["api_value_usd"] * 100 / pct * MONTH_WEEKS, 0), "points": pct}
        if mine:
            mine["multiple"] = round(mine["month_usd"] / sub["price_usd_month"], 1)
        out.append({"id": sub["id"], "plan": f'{sub["vendor"]} {sub["plan"]}', "vendor": sub["vendor"],
                    "name": sub["plan"], "price_usd_month": sub["price_usd_month"], "execution": sub.get("execution") or "—",
                    "excluded": sub.get("excluded") or {},
                    "meter": None if not meter else {
                        "used_percent": float(meter["used_percent"]), "resets_at": meter["resets_at"],
                        "estimated": meter["estimated"], "read_at": meter["read_at"], "age_s": float(meter["age_s"]),
                        "calibrated": sub["meter"].get("calibrated")},
                    "usage_7d": {k: used[k] for k in ("tokens", "total_tokens", "api_value_usd", "unpriced_models")},
                    "usd_per_m_at_pace": weekly_price / used["total_tokens"] * 1e6 if used["total_tokens"] else None,
                    "measured_capacity": mine, "semianalysis": semi})
    return out


def record_costs(conn) -> dict:
    """Cost price of a token through each plan (owner, 2026-10-22): price / API value carried per month, at the current
    pace (last 7 days) and at capacity (measured meter points, else SemiAnalysis' best published value)."""
    out = {}
    for st in state(conn):
        price = float(st["price_usd_month"])
        pace = (st["usage_7d"]["api_value_usd"] or 0) * MONTH_WEEKS or None
        published = [v["usd_month"] for v in st["semianalysis"]] + [float(r["value"]) for r in conn.execute(
            """select value from models.plan_evidence where sub_id = %s and metric = 'usd_value_month' and value > 0""",
            (st["id"],))]   # web research (SemiAnalysis / Tokenomics, other measurements), owner's config
        full = (st["measured_capacity"] or {}).get("month_usd") or max(published, default=None)
        row = {"price_usd_month": price, "api_value_month_pace": pace, "api_value_month_full": full,
               "ratio_pace": price / pace if pace else None, "ratio_full": price / full if full else None,
               "used_percent": (st["meter"] or {}).get("used_percent"),
               "detail": {"capacity_source": "measured" if st["measured_capacity"] else "published",
                          "published_values": len(published),
                          "tokens_7d": st["usage_7d"]["total_tokens"]}}
        conn.execute("""insert into models.subscription_costs (sub_id, price_usd_month, api_value_month_pace, api_value_month_full,
                        ratio_pace, ratio_full, used_percent, detail) values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                     (st["id"], price, pace, full, row["ratio_pace"], row["ratio_full"], row["used_percent"],
                      json.dumps(row["detail"])))
        out[st["id"]] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items() if k != "detail"}
    return out
