"""Sourced observations (P3, 2026-10-28): facts about the world read by Walter's agents, each with its source.

Memory stays generic (Monsieur, 2026-10-27): no domain schema. A price seen on a shop's page is a derived item of kind
`sourced_observation`, tied to the run and task that observed it, so a later run can reuse it while it is fresh and
anyone can check where it came from. Unknown values stay unknown (null), never turned into a guess or a bad score.

Observation v1 (one item):
  subject       what is observed ("All Café iced americano 16 oz", "Café Amazon iced latte")   required
  source_url    where it was read                                                                required
  values        {price: 35, currency: "THB", volume_ml: 473, sugar_g: null, …}   null = unknown
  seller        who offers it ("7-Eleven", "Café Amazon")                                         optional
  observed_at   when it was read (ISO; defaults to now)                                           optional
  source_date   the date shown by the source, when visible                                        optional
  method        how it was read: search_snippet | http | static_html | browser | api              optional
  confidence    0..1 or high / medium / low                                                       optional
  geo           the commercial zone it applies to ({zone, pays, devise})                          optional
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .db import connect

KIND = "sourced_observation"
PROCESSOR = "sourced-observation/1"
METHODS = {"search_snippet", "http", "static_html", "browser", "api", "manual"}
CONFIDENCE = {"high": 0.9, "medium": 0.6, "low": 0.3}


class ObservationError(ValueError):
    pass


def _confidence(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, str):
        if v.lower() in CONFIDENCE:
            return CONFIDENCE[v.lower()]
        v = float(v)
    if not 0 <= float(v) <= 1:
        raise ObservationError("confidence must be in [0, 1] or high/medium/low")
    return float(v)


def _value(v):
    """Unknown stays unknown: 'inconnu', 'unknown', '', '?' → None."""
    if isinstance(v, str) and v.strip().lower() in {"", "?", "inconnu", "unknown", "n/a", "na", "none", "null"}:
        return None
    return v


def normalize(item: dict) -> dict:
    if not isinstance(item, dict):
        raise ObservationError("an observation is an object")
    subject = str(item.get("subject") or item.get("produit") or item.get("product") or "").strip()
    url = str(item.get("source_url") or item.get("url_source") or item.get("url") or "").strip()
    if not subject:
        raise ObservationError("subject required")
    if not url.startswith(("http://", "https://")):
        raise ObservationError("source_url required (http/https)")
    values = {k: _value(v) for k, v in (item.get("values") or {}).items()}
    for k in ("price", "prix", "prix_thb", "currency", "volume", "volume_ml"):      # flat answers from sub-agents
        if k in item and k not in values:
            values[{"prix": "price", "prix_thb": "price"}.get(k, k)] = _value(item[k])
    if "prix_thb" in item and "currency" not in values:
        values["currency"] = "THB"
    method = item.get("method") or "http"
    if method not in METHODS:
        raise ObservationError(f"method must be one of {sorted(METHODS)}")
    observed = item.get("observed_at")
    observed = datetime.fromisoformat(observed) if isinstance(observed, str) else (observed or datetime.now(timezone.utc))
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return {"subject": subject[:300], "source_url": url[:1000], "values": values, "seller": item.get("seller"),
            "observed_at": observed, "source_date": item.get("source_date") or item.get("date"),
            "method": method, "confidence": _confidence(item.get("confidence")), "geo": item.get("geo")}


def record(items: list[dict], *, run_id: str | None = None, task_id: str | None = None,
           geo: dict | None = None) -> dict:
    """Store observations (idempotent per run, subject, source and values). Returns {stored, skipped, errors}."""
    stored, skipped, errors = [], 0, []
    with connect() as conn:
        for i, raw in enumerate(items or []):
            try:
                o = normalize(raw)
            except (ObservationError, ValueError, TypeError) as exc:
                errors.append({"index": i, "error": str(exc)[:200]})
                continue
            o["geo"] = o["geo"] or geo
            ref = hashlib.sha256(json.dumps([run_id, o["subject"], o["source_url"], o["values"]], sort_keys=True,
                                            default=str, ensure_ascii=False).encode()).hexdigest()[:32]
            vals = ", ".join(f"{k}={v}" for k, v in o["values"].items() if v is not None) or "valeurs inconnues"
            row = conn.execute(
                """insert into core.derived_items (kind, content, attributes, status, derived_by, processor_version,
                                                   source_refs, confidence, valid_from, privacy_class)
                   values (%s, %s, %s, 'derived', 'walter-run', %s, %s, %s, %s, 'cloud_allowed')
                   on conflict (derived_by, (source_refs ->> 'ref')) where source_refs ? 'ref' do nothing
                   returning item_id""",
                (KIND, f"{o['subject']} — {vals} (source {o['source_url']})",
                 json.dumps({k: v for k, v in o.items() if k not in ("observed_at",)} | {"run_id": run_id,
                            "task_id": task_id}, default=str, ensure_ascii=False),
                 PROCESSOR, json.dumps({"ref": ref, "url": o["source_url"], "run_id": run_id, "task_id": task_id}),
                 o["confidence"], o["observed_at"])).fetchone()
            if not row:
                skipped += 1
                continue
            stored.append(str(row["item_id"]))
            if run_id:
                conn.execute("insert into runs.links (run_id, kind, ref) values (%s, 'observation', %s) on conflict do nothing",
                             (run_id, str(row["item_id"])))
    return {"stored": len(stored), "skipped": skipped, "errors": errors, "item_ids": stored}


def of_run(run_id: str) -> list[dict]:
    with connect() as conn:
        return conn.execute("""select item_id, content, attributes, confidence, valid_from observed_at
                               from core.derived_items where kind = %s and attributes->>'run_id' = %s
                               order by created_at""", (KIND, run_id)).fetchall()


def recent(query: str, *, max_age_hours: float = 24, limit: int = 50) -> list[dict]:
    """Fresh observations whose subject or seller matches all the words of `query` (reuse before re-reading)."""
    words = [w for w in query.lower().split() if len(w) > 2]
    sql = """select item_id, content, attributes, confidence, valid_from observed_at from core.derived_items
             where kind = %s and status = 'derived' and valid_from > now() - make_interval(secs => %s)"""
    params: list = [KIND, max_age_hours * 3600]
    for w in words:
        sql += " and lower(attributes->>'subject' || ' ' || coalesce(attributes->>'seller', '')) like %s"
        params.append(f"%{w}%")
    sql += " order by valid_from desc limit %s"
    params.append(limit)
    with connect() as conn:
        return conn.execute(sql, params).fetchall()
