"""ModelDial: the measured weekly quota of each AI subscription, model by model (owner, 2026-11-16: « intègre
modeldial.com pour déterminer le prix de revient du token avec nos abonnements »).

https://modeldial.com/subscriptions lists, for every plan it has measured (« 实测额度 ») and every model of the plan,
the weekly tokens (unit 亿 = 100 M, input + output together) and their API-equivalent value in USD. The page is the
only source (no JSON for it, checked 2026-11-16: /openapi-v1.json and /llms.txt cover the Radar only), so this reads
the rendered table: one cell = one plan x model, identified by its `calc_row` id (« claude-pro-opus-5.5-20261005 »:
plan key, model, measurement date).

A declared plan opts in with `modeldial_plan` = the plan key of its cells (« claude-pro », « openai-plus »,
« google-pro »). Each matching cell becomes two rows of models.plan_evidence (origin 'modeldial'): usd_value_month
and tokens_month, per model, monthly = weekly x 52 / 12 (ModelDial's own average month). A model name is linked to a
router id only on an exact canonical match (the owner's rule on model names, 2026-11-13): an unmatched cell is
reported, never guessed. subscriptions.record_costs turns these rows into a cost price per plan x model.
"""
from __future__ import annotations

import html
import re

from walter_router.analysis import identity
from walter_router.plan import declared
from walter_router.research.web import fetch_text

URL = "https://modeldial.com/subscriptions"
SOURCE = "ModelDial — 订阅额度 (measured subscription quotas)"
WEEKS_PER_MONTH = 52 / 12            # ModelDial: « 平均月按每周额度 × 52 ÷ 12 计算 »
TOKENS_UNIT = 1e8                    # 亿

_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
_ROW_NAME = re.compile(r'<th\b[^>]*scope="row"[^>]*>(.*?)</th>', re.S)
_CELL = re.compile(r'<a\b[^>]*href="[^"]*calc_row=([a-z0-9.\-]+)[^"]*"[^>]*>(.*?)</a>', re.S)
_NUMBER = re.compile(r'quotaNumber[^>]*>(.*?)</span>', re.S)
_API = re.compile(r'apiValue[^>]*>(.*?)</span>', re.S)
_DATE = re.compile(r"-(20\d{2})(\d{2})(\d{2})$")
_MODIFIED = re.compile(r'"dateModified":"(\d{4}-\d{2}-\d{2})"')


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _num(text: str) -> float | None:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    return float(m.group(0).replace(",", "")) if m else None


def parse(page: str) -> list[dict]:
    """Every measured cell of the page: {row_id, model_name, weekly_tokens, weekly_api_usd, measured}."""
    modified = _MODIFIED.search(page)
    out, seen = [], set()
    for tr in _ROW.findall(page):
        name = _ROW_NAME.search(tr)
        if not name:
            continue
        model_name = _text(name.group(1))
        for row_id, body in _CELL.findall(tr):
            if row_id in seen:
                continue
            number, api = _NUMBER.search(body), _API.search(body)
            tokens = _num(_text(number.group(1))) if number else None
            usd = _num(_text(api.group(1)).replace("API 等值", "")) if api else None
            if tokens is None:   # a cell without its API value still tells the tokens (Gemini 4 Hydrogen, 2026-11-16)
                continue
            seen.add(row_id)
            d = _DATE.search(row_id)
            out.append({"row_id": row_id, "model_name": model_name, "weekly_tokens": tokens * TOKENS_UNIT,
                        "weekly_api_usd": usd,
                        "measured": f"{d.group(1)}-{d.group(2)}-{d.group(3)}" if d else
                        (modified.group(1) if modified else None)})
    return out


def model_id(name: str, plan_key: str, known: set[str]) -> str | None:
    """Router id of a ModelDial row name, exact canonical match only: « Opus 5.5 » on a Claude plan -> claude-opus-5-5,
    « Gemini 4 Hydrogen » -> gemini-4-hydrogen. The plan's vendor word is tried as a prefix (Claude rows omit it)."""
    base = identity.canon(identity.slugify(name))
    vendor = plan_key.split("-", 1)[0]
    for cand in (base, f"{vendor}-{base}"):
        if cand in known:
            return cand
    return None


def cells_for(cells: list[dict], plan_key: str) -> list[dict]:
    """The cells of one plan key: the row id is « <plan key>-<model>[-date] »; a longer key never steals a shorter one
    (« openai-pro-100-… » is not « openai-pro »'s)."""
    return [c for c in cells if c["row_id"].startswith(plan_key + "-")
            and not re.match(r"\d", c["row_id"][len(plan_key) + 1:])]


def run(conn, page: str | None = None) -> dict:
    page = page if page is not None else fetch_text(URL)
    cells = parse(page)
    if not cells:
        raise ValueError("ModelDial: no measured cell found (page layout changed?)")
    known = {r["model_id"] for r in conn.execute("select model_id from models.canonical")}
    plans = [s for s in declared.read().get("subscriptions", []) if s.get("modeldial_plan") and not s.get("retired")]
    stored, unmatched, per_plan = 0, [], {}
    for sub in plans:
        key = sub["modeldial_plan"]
        mine = cells_for(cells, key)
        per_plan[sub["id"]] = len(mine)
        for c in mine:
            mid = model_id(c["model_name"], key, known)
            if mid is None:
                unmatched.append(f'{key}: {c["model_name"]}')
                continue
            usd = c["weekly_api_usd"]
            month_usd = round(usd * WEEKS_PER_MONTH, 2) if usd is not None else None
            month_tokens = round(c["weekly_tokens"] * WEEKS_PER_MONTH)
            url = f"{URL}?calc_row={c['row_id']}"
            quote = (f"{c['model_name']} : ≈ {c['weekly_tokens'] / TOKENS_UNIT:g} 亿 tokens par semaine, "
                     + (f"API 等值 ≈ ${usd:,.0f} par semaine" if usd is not None else "valeur API non publiée")
                     + f" (cellule {c['row_id']})")
            rows = [("tokens_month", month_tokens, "tokens/mois, entrée + sortie (semaine × 52 ÷ 12)")]
            if month_usd is not None:
                rows.insert(0, ("usd_value_month", month_usd, "USD/mois au prix API (semaine × 52 ÷ 12)"))
            for metric, value, unit in rows:
                cur = conn.execute(
                    """insert into models.plan_evidence (sub_id, vendor, plan, model_id, metric, value, unit, source_name,
                       source_url, published, quote, origin) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'modeldial')
                       on conflict do nothing""",
                    (sub["id"], sub.get("vendor") or "?", sub.get("plan") or "?", mid, metric, value, unit, SOURCE, url,
                     c["measured"], quote))
                stored += cur.rowcount
    return {"cells": len(cells), "plans": per_plan, "new_rows": stored, "unmatched": sorted(set(unmatched))}


def latest(conn, sub_id: str) -> dict[str, dict]:
    """model_id -> {usd_value_month, tokens_month, published, url} from the newest ModelDial rows of one plan."""
    out: dict[str, dict] = {}
    for r in conn.execute(
            """select distinct on (model_id, metric) model_id, metric, value, published, source_url from models.plan_evidence
               where origin = 'modeldial' and sub_id = %s and model_id is not null and value > 0
               order by model_id, metric, found_at desc, evidence_id desc""", (sub_id,)):
        row = out.setdefault(r["model_id"], {"published": r["published"], "url": r["source_url"]})
        row[r["metric"]] = float(r["value"])
    return {m: v for m, v in out.items() if v.get("usd_value_month")}
