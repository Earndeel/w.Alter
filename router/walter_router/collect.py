"""Collect leaderboards (from the aa-pareto skill cache) and live provider catalogues into models.snapshots,
then parse each new snapshot into models.benchmarks / models.offers."""
from __future__ import annotations

import hashlib
import html
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from . import identity

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
CACHE = HERMES_HOME / "cache" / "aa-pareto"
HERMES_PY = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models?output_modalities=all"
KIE_URL = "https://api.kie.ai/client/v1/model-pricing/page"
MAX_BYTES = 64 * 1024 * 1024
MM_TASKS = {"provider_voice": "tts", "index": "speech_to_speech"}
# Kie publishes a few chat price rows with a wrong dimension label; each fix is checked against the
# published input price and the vendor's 1:5 input/output ratio before being added here.
KIE_DIMENSION_FIXES = {("claude-opus-5-5", "claude-opus-5"): "output"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def fetch_json(url: str, payload: dict | None = None) -> Any:
    headers = {"User-Agent": "Walter-Router/1.0", "Accept": "application/json"}
    data = None
    if payload is not None:
        headers.update({"Content-Type": "application/json", "Origin": "https://kie.ai", "Referer": "https://kie.ai/pricing"})
        data = json.dumps(payload).encode()
    with urlopen(Request(url, data=data, headers=headers), timeout=60) as resp:  # noqa: S310 (fixed https URLs)
        raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"response too large: {url}")
    return json.loads(raw)


def _parse_time(value: str | None) -> datetime:
    if not value:
        return now()
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# --- sources -------------------------------------------------------------------------------------------

def source_aa() -> tuple[dict, datetime, str]:
    doc = json.loads((CACHE / "latest.json").read_text())
    return doc, _parse_time(doc.get("generated_at")), "https://artificialanalysis.ai/"


def source_mm() -> tuple[dict, datetime, str]:
    doc = json.loads((CACHE / "multimodal_latest.json").read_text())
    return doc, _parse_time(doc.get("generated_at")), "https://artificialanalysis.ai/"


def source_da() -> tuple[dict, datetime, str]:
    doc = json.loads((CACHE / "designarena.json").read_text())
    return doc, _parse_time(doc.get("generated_at")), doc.get("source_url") or "https://www.designarena.ai/"


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Walter-Router/1.0)", "Accept": "text/html"})
    with urlopen(req, timeout=40) as resp:  # noqa: S310 (fixed https host)
        raw = resp.read(MAX_BYTES + 1)
    return raw.decode("utf-8", "replace")


def display_pricing(page: str) -> list | None:
    """The `displayPricing` array embedded in an OpenRouter model page (per-second / per-song / per-tier prices
    that the /models API reports as 0 for media models)."""
    text = html.unescape(page).replace('\\"', '"')
    i = text.find('"displayPricing":')
    if i < 0:
        return None
    j = text.index("[", i)
    depth = 0
    for k in range(j, len(text)):
        if text[k] == "[":
            depth += 1
        elif text[k] == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[j:k + 1])
    return None


def source_openrouter() -> tuple[dict, datetime, str]:
    doc = fetch_json(OPENROUTER_URL)
    if not doc.get("data"):
        raise ValueError("openrouter: empty catalogue")
    for m in doc["data"]:
        if _or_interface(m) == "chat" or ":" in m["id"] or m["id"].startswith(("openrouter/", "~")):
            continue
        try:
            m["_display_pricing"] = display_pricing(fetch_text(f"https://openrouter.ai/{m['id']}"))
        except Exception as exc:  # noqa: BLE001 — a missing page leaves that model unpriced, not the run failed
            m["_display_pricing_error"] = f"{type(exc).__name__}: {exc}"[:200]
        time.sleep(0.3)
    return doc, now(), OPENROUTER_URL


def source_kie() -> tuple[dict, datetime, str]:
    records, page = [], 1
    while True:
        body = fetch_json(KIE_URL, {"pageNum": page, "pageSize": 100, "modelDescription": "", "interfaceType": ""})
        data = body["data"]
        if body.get("code") != 200 or data["current"] != page or not 1 <= data["pages"] <= 100:
            raise ValueError("kie: invalid page")
        records.extend(data["records"])
        if page == data["pages"]:
            break
        page += 1
    if len(records) != data["total"]:
        raise ValueError("kie: incomplete catalogue")
    return {"data": records}, now(), KIE_URL


def source_codex() -> tuple[dict, datetime, str]:
    """Live Codex catalogue of Monsieur's ChatGPT account, read through Hermes (read-only; token never printed)."""
    code = ("import json; from hermes_cli.models import _codex_catalog; "
            "print(json.dumps(_codex_catalog('openai-codex', False)))")
    out = subprocess.run([str(HERMES_PY), "-c", code], cwd=str(HERMES_HOME / "hermes-agent"), capture_output=True,
                         text=True, timeout=120, env={**os.environ, "HERMES_HOME": str(HERMES_HOME)})
    ids = json.loads(out.stdout.strip().splitlines()[-1]) if out.returncode == 0 and out.stdout.strip() else []
    if not ids:
        raise ValueError(f"codex: catalogue unavailable (exit {out.returncode})")
    return {"models": ids}, now(), "chatgpt.com/backend-api/codex (account catalogue)"


DECLARED = Path(__file__).resolve().parent.parent / "config" / "declared_offers.json"


def source_declared() -> tuple[dict, datetime, str]:
    doc = json.loads(DECLARED.read_text())
    return {"offers": doc["offers"]}, now(), str(DECLARED)


SOURCES = {"aa": source_aa, "mm": source_mm, "da": source_da,
           "openrouter": source_openrouter, "kie": source_kie, "codex": source_codex,
           "declared": source_declared}


# --- parsing -------------------------------------------------------------------------------------------

def _num(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def _mm_unit_price(row: dict) -> tuple[float | None, str | None]:
    """AA list price normalised to the provider units we compare against (reference only, never 'callable')."""
    price, unit = _num(row.get("api_price_usd")), (row.get("api_price_unit") or "").strip()
    if price is None:
        return None, None
    if unit == "1k imgs":
        return price / 1000, "usd_per_image"
    if unit == "min":
        return price / 60, "usd_per_second"
    if unit == "1M chars":
        return price, "usd_per_1m_chars"
    return price, unit or None


def parse_benchmarks(kind: str, doc: dict) -> list[dict]:
    rows: list[dict] = []
    if kind == "aa":
        for r in doc["data"]:
            score = _num(r.get("intelligence_index"))
            if score is None:
                continue
            mid, variant = identity.normalize("aa", r["slug"], r.get("name"))
            rows.append(dict(benchmark="aa_intelligence", task="intelligence", external_key=r["slug"], model_id=mid,
                             variant=variant, display_name=r.get("name"), score=score, score_unit="AA Intelligence Index",
                             cost=_num(r.get("aa_cost_per_task_intelligence_usd")), cost_unit="usd_per_aa_task",
                             released=None, extra={}))
    elif kind == "mm":
        for module in doc["modules"].values():
            for task_key, task in module["tasks"].items():
                best: dict[str, dict] = {}
                for r in task.get("rows") or task.get("records") or []:
                    score = _num(r.get("quality_score"))
                    if score is None:
                        continue
                    if r["model"] in best and best[r["model"]]["score"] >= score:
                        continue
                    mid, variant = identity.normalize("mm", r["model"])
                    cost, unit = _mm_unit_price(r)
                    best[r["model"]] = dict(
                        benchmark="aa_mm", task=MM_TASKS.get(task_key, task_key), external_key=r["model"], model_id=mid,
                        variant=variant, display_name=r["model"], score=score, score_unit=r.get("quality_metric"),
                        cost=cost, cost_unit=unit, released=r.get("released"),
                        extra={"api_price_raw": r.get("api_price_raw"), "samples": r.get("samples"),
                               "provider": r.get("provider")})
                rows.extend(best.values())
    elif kind == "da":
        for section, bench in (("categories", "da_models"), ("agent_categories", "da_agents")):
            for task_key, cat in (doc.get(section) or {}).items():
                cat_rows = cat.get("rows") if isinstance(cat, dict) else cat
                seen: set[str] = set()
                for r in cat_rows or []:
                    key = r.get("model") or r.get("modelId")
                    score = _num(r.get("elo"))
                    if not key or score is None or key in seen:
                        continue
                    seen.add(key)
                    mid, variant = identity.normalize("da", key)
                    rows.append(dict(benchmark=bench, task=task_key, external_key=key, model_id=mid, variant=variant,
                                     display_name=key, score=score, score_unit="Design Arena Elo", cost=None,
                                     cost_unit=None, released=None,
                                     extra={k: r.get(k) for k in ("win_rate", "battles", "avg_generation_time_ms")}))
    return rows


def _or_interface(model: dict) -> str:
    out = model.get("architecture", {}).get("output_modalities") or ["text"]
    if "lyria" in model["id"]:
        return "music"
    for kind in ("video", "image", "audio"):
        if kind in out:
            return kind
    return "chat"


def _kie_interface(rec: dict) -> str:
    kind = rec.get("interfaceType") or "chat"
    desc = rec["modelDescription"].lower()
    if kind == "music" and any(k in desc for k in ("tts", "text to speech", "elevenlabs", "dialogue")):
        return "audio"
    return kind


OFFER_KINDS = ("openrouter", "kie", "codex", "declared")


def parse_offers(kind: str, doc: dict) -> list[dict]:
    rows: list[dict] = []
    if kind == "openrouter":
        for m in doc["data"]:
            oid = m["id"]
            if ":" in oid or oid.startswith(("openrouter/", "~")):
                continue  # batch/free duplicates, meta-routers and moving "latest" pointers
            mid, _ = identity.normalize("openrouter", oid)
            pr = m.get("pricing") or {}
            pin, pout = _num(pr.get("prompt")), _num(pr.get("completion"))
            interface = _or_interface(m)
            created = datetime.fromtimestamp(m["created"], timezone.utc) if m.get("created") else None
            media = interface != "chat"
            rows.append(dict(provider="openrouter", offer_key=oid, model_id=mid, interface=interface, access="paid",
                             # media models report 0/0 token prices in the API: that is not a price
                             price_in_1m=None if media or pin is None or pin < 0 else pin * 1e6,
                             price_out_1m=None if media or pout is None or pout < 0 else pout * 1e6,
                             unit_price=None, unit=None, provider_created=created, pricing=pr))
            for entry in m.get("_display_pricing") or []:
                if entry.get("kind") != "unit":
                    continue  # token-priced media (e.g. image output per M tokens) has no per-unit equivalent
                unit = "per " + (entry.get("unitLabel") or "").lstrip("/").strip()
                for tier in entry.get("tiers") or [{"sku_label": "", "price": entry.get("price")}]:
                    price = _num(tier.get("price"))
                    if price is None:
                        continue
                    key = " | ".join(x for x in (oid, entry.get("sku_label"), tier.get("sku_label")) if x)
                    rows.append(dict(provider="openrouter", offer_key=key, model_id=mid, interface=interface, access="paid",
                                     price_in_1m=None, price_out_1m=None, unit_price=price, unit=unit,
                                     provider_created=created, pricing={"display": entry, "tier": tier}))
    elif kind == "kie":
        chat: dict[str, dict] = {}
        for rec in doc["data"]:
            parts = [p.strip() for p in rec["modelDescription"].split(",")]
            name, interface = parts[0], _kie_interface(rec)
            mid, _ = identity.normalize("kie", name)
            price = None if "," in str(rec.get("usdPrice")) else _num(rec.get("usdPrice"))
            if interface == "chat":
                dim = parts[-1].lower()
                dim = KIE_DIMENSION_FIXES.get((name.lower(), dim), dim)
                entry = chat.setdefault(name, dict(provider="kie", offer_key=name, model_id=mid, interface="chat",
                                                   access="paid", price_in_1m=None, price_out_1m=None, unit_price=None,
                                                   unit="per million tokens", provider_created=None, pricing={}))
                entry["pricing"][parts[-1]] = rec.get("usdPrice")
                if dim == "input":
                    entry["price_in_1m"] = price
                elif dim == "output":
                    entry["price_out_1m"] = price
                continue
            rows.append(dict(provider="kie", offer_key=rec["modelDescription"], model_id=mid, interface=interface,
                             access="paid", price_in_1m=None, price_out_1m=None, unit_price=price,
                             unit=rec.get("creditUnit"), provider_created=None, pricing=rec))
        rows.extend(chat.values())
    elif kind == "declared":
        for d in doc["offers"]:
            mid, _ = identity.normalize("declared", d["model"])
            rows.append(dict(provider=d["provider"], offer_key=d["offer_key"], model_id=mid, interface=d["interface"],
                             access=d["access"], price_in_1m=None, price_out_1m=None, unit_price=None, unit=None,
                             provider_created=None, pricing={"declared": d.get("declared"), "note": d.get("note")}))
    elif kind == "codex":
        for oid in doc["models"]:
            mid, _ = identity.normalize("codex", oid)
            rows.append(dict(provider="codex", offer_key=oid, model_id=mid, interface="chat", access="subscription",
                             price_in_1m=None, price_out_1m=None, unit_price=None, unit=None, provider_created=None,
                             pricing={"subscription": "ChatGPT Plus (user-declared)"}))
    return rows


# --- storage -------------------------------------------------------------------------------------------

def _ensure_identity(conn, namespace: str, key: str, model_id: str, vendor: str | None = None) -> None:
    conn.execute("insert into models.canonical (model_id, vendor) values (%s, %s) on conflict do nothing", (model_id, vendor))
    origin = "manual" if key in identity.MANUAL.get(namespace, {}) else "auto"
    conn.execute("""insert into models.aliases (namespace, external_key, model_id, origin) values (%s, %s, %s, %s)
                    on conflict (namespace, external_key) do update set model_id = excluded.model_id, origin = excluded.origin
                    where models.aliases.origin = 'auto' or excluded.origin = 'manual'""",
                 (namespace, key, model_id, origin))


def _insert_rows(conn, sid: int, kind: str, doc: dict) -> int:
    """(Re)derive benchmarks/offers of one snapshot from its raw document with the current identity rules."""
    conn.execute("delete from models.benchmarks where snapshot_id = %s", (sid,))
    conn.execute("delete from models.offers where snapshot_id = %s", (sid,))
    rows = parse_offers(kind, doc) if kind in OFFER_KINDS else parse_benchmarks(kind, doc)
    for r in rows:
        key = r.get("external_key") or r["offer_key"]
        _ensure_identity(conn, kind, key, r["model_id"])
        if "benchmark" in r:
            conn.execute("""insert into models.benchmarks (snapshot_id, benchmark, task, external_key, model_id, variant,
                            display_name, score, score_unit, cost, cost_unit, released, extra)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) on conflict do nothing""",
                         (sid, r["benchmark"], r["task"], r["external_key"], r["model_id"], r["variant"], r["display_name"],
                          r["score"], r["score_unit"], r["cost"], r["cost_unit"], r["released"], json.dumps(r["extra"])))
        else:
            conn.execute("""insert into models.offers (snapshot_id, provider, offer_key, model_id, interface, access,
                            price_in_1m, price_out_1m, unit_price, unit, provider_created, pricing)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) on conflict do nothing""",
                         (sid, r["provider"], r["offer_key"], r["model_id"], r["interface"], r["access"], r["price_in_1m"],
                          r["price_out_1m"], r["unit_price"], r["unit"], r["provider_created"], json.dumps(r["pricing"])))
    conn.execute("update models.snapshots set row_count = %s where snapshot_id = %s", (len(rows), sid))
    return len(rows)


def store(conn, kind: str, doc: dict, fetched_at: datetime, url: str) -> tuple[int, bool]:
    """Insert the snapshot (deduplicated by content) and (re)derive its rows. Returns (snapshot_id, is_new).

    An unchanged document is re-derived anyway, so identity rule changes (aliases.json) apply immediately.
    """
    blob = json.dumps(doc, sort_keys=True, ensure_ascii=False)
    sha = hashlib.sha256(blob.encode()).hexdigest()
    found = conn.execute("select snapshot_id from models.snapshots where kind = %s and sha256 = %s", (kind, sha)).fetchone()
    if found:
        sid, new = found["snapshot_id"], False
        conn.execute("update models.snapshots set fetched_at = greatest(fetched_at, %s) where snapshot_id = %s",
                     (fetched_at, sid))
    else:
        sid, new = conn.execute("""insert into models.snapshots (kind, fetched_at, source_url, sha256, row_count, raw)
                                   values (%s, %s, %s, %s, 0, %s::jsonb) returning snapshot_id""",
                                (kind, fetched_at, url, sha, blob)).fetchone()["snapshot_id"], True
    _insert_rows(conn, sid, kind, doc)
    return sid, new


def collect_all(conn) -> dict[str, Any]:
    """Collect every source; a failing source is reported and the last good snapshot stays in use."""
    report: dict[str, Any] = {}
    for kind, fn in SOURCES.items():
        try:
            doc, fetched_at, url = fn()
            with conn.transaction():
                sid, new = store(conn, kind, doc, fetched_at, url)
            report[kind] = {"snapshot_id": sid, "new": new}
        except Exception as exc:  # noqa: BLE001 — one source must not stop the others
            report[kind] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return report


def prune(conn, keep_days: int = 30) -> int:
    """Delete snapshots older than keep_days, always keeping the latest one of each kind."""
    cur = conn.execute("""delete from models.snapshots s where fetched_at < now() - make_interval(days => %s)
                          and snapshot_id <> (select max(snapshot_id) from models.snapshots t where t.kind = s.kind)""",
                       (keep_days,))
    return cur.rowcount
